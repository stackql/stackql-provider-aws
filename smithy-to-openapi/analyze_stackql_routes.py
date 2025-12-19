#!/usr/bin/env python3
"""
Analyze StackQL Routes

This script analyzes all AWS service models and generates CSV manifest files
for each service. These manifests contain operation mappings with method names,
SQL verbs, and pagination configurations that can be reviewed and overridden
by humans (or AI) before being used by process_models.py.

Usage:
    cd smithy-to-openapi
    python analyze_stackql_routes.py

Output:
    stackql-routes/{service}.csv - One CSV per service with operation mappings

CSV Format:
    operationId,path,verb,requiredPathParams,requiredHeaderParams,requiredQueryParams,
    requiredReqBodyParams,description,resource,method,sqlVerb,objectKey,
    reqPaginationKey,reqPaginationLocation,respPaginationKey,respPaginationLocation

Note: The 'resource' column is left empty for users or AI to fill before running
process_models.py. Existing operations are preserved as-is to maintain human overrides.

sqlVerb derivation rules (simplified):
    - DELETE HTTP method always maps to 'delete'
    - operationId starting with 'Delete...' -> 'delete'
    - operationId starting with 'Create...' -> 'insert'
    - operationId starting with 'Get...', 'Describe...', 'List...' -> 'select' (unless empty response)
    - operationId starting with 'Update...' or 'Patch...' -> 'update'
    - operationId starting with 'Replace...' or 'Put...' -> 'replace'
    - Otherwise left blank for manual assignment

Note: HTTP verb prefixes in operationId (e.g., GET_CompleteLifecycleAction) are stripped
before applying these rules.
"""

import csv
import json
import sys
import re
from pathlib import Path
from collections import defaultdict
from typing import Set

# Import shared functions
from processors.shared_functions import (
    derive_method_name,
    html_to_md,
    detect_pagination_scheme,
)


def truncate_description(description: str, max_len: int = 50) -> str:
    """Truncate description to max_len characters, removing newlines."""
    if not description:
        return ""
    # Remove newlines and extra whitespace
    description = " ".join(description.split())
    if len(description) > max_len:
        return description[:max_len - 3] + "..."
    return description


def extract_required_params(shapes: dict, operation_shape: dict, protocol: str, visited: Set[str] = None) -> tuple:
    """
    Extract required parameters from a Smithy operation shape.
    
    Returns a tuple of:
    (required_path_params, required_header_params, required_query_params, required_body_params)
    Each is a comma-separated string of parameter names.
    
    Excludes X-Amz-* headers (AWS signing/metadata headers).
    Extracts actual required field names from request body schemas.
    """
    if visited is None:
        visited = set()
    
    required_path: Set[str] = set()
    required_header: Set[str] = set()
    required_query: Set[str] = set()
    required_body: Set[str] = set()
    
    # Get the input shape
    input_ref = operation_shape.get("input", {}).get("target")
    if not input_ref or input_ref in visited:
        return ('', '', '', '')
    
    visited.add(input_ref)
    input_shape = shapes.get(input_ref)
    if not input_shape or input_shape.get("type") != "structure":
        return ('', '', '', '')
    
    members = input_shape.get("members", {})
    required_members = input_shape.get("traits", {}).get("smithy.api#required", [])
    
    # For JSON protocols, all required members go to body
    if protocol in ("aws.protocols#awsJson1_0", "aws.protocols#awsJson1_1"):
        for member_name, member_def in members.items():
            member_traits = member_def.get("traits", {})
            is_required = "smithy.api#required" in member_traits
            
            if is_required:
                required_body.add(member_name)
    else:
        # For other protocols, check member traits for location
        for member_name, member_def in members.items():
            member_traits = member_def.get("traits", {})
            is_required = "smithy.api#required" in member_traits
            
            if not is_required:
                continue
            
            # Determine location from traits
            if "smithy.api#httpLabel" in member_traits:
                # Path parameter
                required_path.add(member_name)
            elif "smithy.api#httpQuery" in member_traits:
                # Query parameter
                query_name = member_traits.get("smithy.api#httpQuery")
                if isinstance(query_name, str):
                    required_query.add(query_name)
                else:
                    required_query.add(member_name)
            elif "smithy.api#httpHeader" in member_traits:
                # Header parameter - exclude X-Amz-* headers
                header_name = member_traits.get("smithy.api#httpHeader")
                if isinstance(header_name, str):
                    if not header_name.startswith("X-Amz-"):
                        required_header.add(header_name)
                else:
                    if not member_name.startswith("X-Amz-"):
                        required_header.add(member_name)
            else:
                # Body parameter (no location trait means it goes in body/payload)
                required_body.add(member_name)
    
    # Convert sets to sorted comma-separated strings
    return (
        ','.join(sorted(required_path)),
        ','.join(sorted(required_header)),
        ','.join(sorted(required_query)),
        ','.join(sorted(required_body))
    )


def _has_empty_or_map_response(shapes: dict, operation_shape: dict) -> bool:
    """
    Check if the operation's response has empty properties or is a map/additionalProperties.

    This is used to determine if a 'select' operation should instead be 'exec'
    because it won't return any useful columns.

    Returns True if:
    - No output defined
    - Output is smithy.api#Unit (empty response)
    - Response schema has empty 'properties' dict
    - Response schema is a map type (has additionalProperties)
    """
    output_ref = operation_shape.get("output", {}).get("target")
    if not output_ref:
        return True  # No output means empty response

    if output_ref == "smithy.api#Unit":
        return True  # Unit type means empty response

    output_shape = shapes.get(output_ref)
    if not output_shape:
        return True  # Shape not found, treat as empty

    # Check if it's a structure with empty properties
    if output_shape.get("type") == "structure":
        members = output_shape.get("members", {})
        if not members:
            return True  # Empty properties

    # Check if it's a map type
    if output_shape.get("type") == "map":
        return True

    return False


def determine_sql_verb_simplified(http_method: str, operation_id: str, shapes: dict, operation_shape: dict) -> str:
    """
    Determine the appropriate StackQL verb based on simplified rules.

    Rules (in order):
    1. HTTP DELETE method MUST ALWAYS map to 'delete' (guardrail)
    2. operationId starting with 'Delete...' -> 'delete'
    3. operationId starting with 'Create...' -> 'insert'
    4. operationId starting with 'Get...', 'Describe...', or 'List...' -> 'select'
       (but override to 'exec' if response is empty or map)
    5. operationId starting with 'Update...' or 'Patch...' -> 'update'
    6. operationId starting with 'Replace...' or 'Put...' -> 'replace'
    7. Otherwise leave as `exec`

    Note: HTTP verb prefixes in operationId (e.g., GET_CompleteLifecycleAction)
    are stripped before applying these rules.
    """
    http_method = http_method.upper()

    # Strip prefix before and including '_' (e.g., GET_CompleteLifecycleAction -> CompleteLifecycleAction)
    clean_op_id = operation_id
    if '_' in operation_id:
        clean_op_id = operation_id.split('_', 1)[1]

    # Rule 1: HTTP DELETE must always be 'delete' (guardrail - never anything else)
    if http_method == 'DELETE':
        return 'delete'

    # Rule 2: Delete... -> 'delete'
    if clean_op_id.startswith('Delete'):
        return 'delete'

    # Rule 3: Create... -> 'insert'
    if clean_op_id.startswith('Create'):
        return 'insert'

    # Rule 4: Get..., Describe..., List... -> 'select' (but check response)
    if clean_op_id.startswith(('Get', 'Describe', 'List')):
        # Check if response has empty properties or is a map
        if _has_empty_or_map_response(shapes, operation_shape):
            return 'exec'
        return 'select'

    # Rule 5: Update..., Patch... -> 'update'
    if clean_op_id.startswith(('Update', 'Patch')):
        return 'update'

    # Rule 6: Replace..., Put... -> 'replace'
    if clean_op_id.startswith(('Replace', 'Put')):
        return 'replace'

    # Rule 7: Otherwise leave blank for manual assignment
    return 'exec'


def extract_operations_from_model(model_path: Path, service_name: str, protocol: str):
    """
    Extract all operations from a Smithy model file.

    Yields dictionaries with operation details for each operation found.
    """
    with open(model_path, "r", encoding="utf-8") as f:
        model_data = json.load(f)

    shapes = model_data.get("shapes", model_data)

    # Detect pagination scheme for this service
    pagination_data = detect_pagination_scheme(shapes, protocol)
    dominant_scheme = pagination_data.get("dominant_scheme") if pagination_data else None
    pagination_exceptions = pagination_data.get("exceptions", {}) if pagination_data else {}

    # Get service name for JSON protocols (X-Amz-Target)
    service_name_for_target = None
    for shape_name, shape in shapes.items():
        if shape.get("type") == "service":
            service_name_for_target = shape_name.split('#')[1]
            break

    for shape_name, shape in shapes.items():
        if shape.get("type") != "operation":
            continue

        operation_id = shape_name.split("#")[-1]
        traits = shape.get("traits", {})

        # Get HTTP info based on protocol
        http = traits.get("smithy.api#http", {})
        path = http.get("uri")
        verb = http.get("method")

        # For Query/JSON protocols, path and verb are derived differently
        if protocol in ("aws.protocols#awsQuery", "aws.protocols#ec2Query"):
            path = f"/#Action={operation_id}"
            verb = "GET"  # Primary method for query operations
        elif protocol in ("aws.protocols#awsJson1_0", "aws.protocols#awsJson1_1"):
            if service_name_for_target:
                path = f"/#X-Amz-Target={service_name_for_target}.{operation_id}"
            else:
                path = f"/#X-Amz-Target=.{operation_id}"
            verb = "POST"

        if not path or not verb:
            continue

        verb = verb.upper()

        # Get description
        description = ""
        if "smithy.api#documentation" in traits:
            description = html_to_md(traits["smithy.api#documentation"])

        # Derive StackQL mappings
        method = derive_method_name(operation_id)
        sql_verb = determine_sql_verb_simplified(verb, operation_id, shapes, shape)

        # Determine pagination overrides (only populated if different from service-level)
        req_pagination_key = ""
        req_pagination_location = ""
        resp_pagination_key = ""
        resp_pagination_location = ""

        # Determine objectKey for paginated responses
        # The smithy.api#paginated trait's 'items' field specifies the response field containing the list
        object_key = ""
        paginated_trait = traits.get("smithy.api#paginated")
        if paginated_trait:
            items_field = paginated_trait.get("items")
            if items_field:
                object_key = f"$.{items_field}"

        # Check if this operation has pagination that differs from dominant scheme
        if paginated_trait and dominant_scheme:
            input_token = paginated_trait.get("inputToken", "")
            output_token = paginated_trait.get("outputToken", "")

            # Determine actual locations for this operation
            op_req_location = "body"
            op_resp_location = "body"

            # Check input shape for location
            input_shape_name = shape.get("input", {}).get("target")
            if input_shape_name and input_shape_name in shapes:
                input_shape = shapes[input_shape_name]
                members = input_shape.get("members", {})
                if input_token in members:
                    member_traits = members[input_token].get("traits", {})
                    if "smithy.api#httpQuery" in member_traits:
                        op_req_location = "query"
                    elif "smithy.api#httpHeader" in member_traits:
                        op_req_location = "header"

            # Check if this differs from dominant scheme
            if (input_token != dominant_scheme.get("request_key") or
                op_req_location != dominant_scheme.get("request_location") or
                output_token != dominant_scheme.get("response_key") or
                op_resp_location != dominant_scheme.get("response_location")):

                req_pagination_key = input_token
                req_pagination_location = op_req_location
                resp_pagination_key = output_token
                resp_pagination_location = op_resp_location

        # Extract required parameters
        req_path, req_header, req_query, req_body = extract_required_params(shapes, shape, protocol)

        yield {
            "operationId": operation_id,
            "path": path,
            "verb": verb,
            "requiredPathParams": req_path,
            "requiredHeaderParams": req_header,
            "requiredQueryParams": req_query,
            "requiredReqBodyParams": req_body,
            "description": truncate_description(description),
            "resource": "",  # Left empty for users or AI to fill before running process_models.py
            "method": method,
            "sqlVerb": sql_verb,
            "objectKey": object_key,  # Auto-derived from smithy.api#paginated 'items' field
            "reqPaginationKey": req_pagination_key,
            "reqPaginationLocation": req_pagination_location,
            "respPaginationKey": resp_pagination_key,
            "respPaginationLocation": resp_pagination_location,
        }


def load_existing_csv(csv_path: Path) -> dict:
    """
    Load existing CSV file and return a dictionary keyed by operationId.

    Returns empty dict if file doesn't exist.
    """
    if not csv_path.exists():
        return {}

    existing = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing[row["operationId"]] = row

    return existing


def write_csv(csv_path: Path, rows: list, fieldnames: list):
    """Write rows to CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def extract_services(input_dir: Path):
    """
    Iterate through all service directories and yield model info.
    """
    for service_dir in sorted(input_dir.iterdir()):
        if not service_dir.is_dir():
            continue

        service_name = service_dir.name
        service_subdir = service_dir / "service"

        if not service_subdir.exists() or not service_subdir.is_dir():
            continue

        version_dirs = [d for d in service_subdir.iterdir() if d.is_dir()]

        if len(version_dirs) != 1:
            continue

        version_dir = version_dirs[0]
        version_name = version_dir.name

        for model_file in version_dir.glob("*.json"):
            try:
                with open(model_file, "r", encoding="utf-8") as f:
                    model_data = json.load(f)

                shapes = model_data.get("shapes", model_data)
                for shape_name, shape in shapes.items():
                    if shape.get("type") == "service":
                        traits = shape.get("traits", {})
                        protocol = "unknown"
                        for key in traits:
                            if key.startswith("aws.protocols#"):
                                protocol = key
                                break

                        yield {
                            "filename": model_file.name,
                            "filepath": model_file,
                            "servicename": shape_name,
                            "servicedir": service_name,
                            "version": version_name,
                            "protocol": protocol
                        }
            except Exception as e:
                print(f"Error processing {model_file.name}: {e}")


def main():
    """Main entry point."""
    # Check we're in the right directory
    models_dir = Path("models")
    if not models_dir.exists():
        # Try parent directory
        models_dir = Path("../models")
        if not models_dir.exists():
            print("ERROR: 'models' directory not found. Run from project root or smithy-to-openapi directory.")
            sys.exit(1)

    # Output directory for CSV files
    output_dir = Path("smithy-to-openapi/stackql-routes")
    if not output_dir.parent.exists():
        # We're in smithy-to-openapi directory
        output_dir = Path("stackql-routes")

    output_dir.mkdir(parents=True, exist_ok=True)

    # CSV field names
    fieldnames = [
        "operationId",
        "path",
        "verb",
        "requiredPathParams",
        "requiredHeaderParams",
        "requiredQueryParams",
        "requiredReqBodyParams",
        "description",
        "resource",
        "method",
        "sqlVerb",
        "objectKey",
        "reqPaginationKey",
        "reqPaginationLocation",
        "respPaginationKey",
        "respPaginationLocation",
    ]

    # Statistics
    total_services = 0
    total_operations = 0
    new_operations = 0
    preserved_operations = 0

    print("Analyzing StackQL routes...")
    print("=" * 60)

    # Process each service
    for svc in extract_services(models_dir):
        service_name = svc["servicedir"].replace("-", "_")
        csv_path = output_dir / f"{service_name}.csv"

        # Load existing CSV if it exists
        existing_ops = load_existing_csv(csv_path)

        # Extract operations from model
        operations = list(extract_operations_from_model(
            svc["filepath"],
            svc["servicedir"],
            svc["protocol"]
        ))

        if not operations:
            continue

        total_services += 1

        # Merge: keep existing entries, add new ones
        # Also update objectKey for existing entries if it's empty and we have a derived value
        final_rows = []
        new_count = 0
        preserved_count = 0
        updated_count = 0

        for op in operations:
            op_id = op["operationId"]
            if op_id in existing_ops:
                # Preserve existing entry (may have human overrides)
                existing_row = existing_ops[op_id]
                
                # Ensure new columns exist in existing row (for backward compatibility)
                for col in ["requiredPathParams", "requiredHeaderParams", "requiredQueryParams", "requiredReqBodyParams"]:
                    if col not in existing_row:
                        existing_row[col] = op.get(col, "")
                
                # Update objectKey if existing is empty and we have a derived value
                if not existing_row.get("objectKey", "").strip() and op.get("objectKey", "").strip():
                    existing_row["objectKey"] = op["objectKey"]
                    updated_count += 1
                
                final_rows.append(existing_row)
                preserved_count += 1
            else:
                # Add new entry with inferred values
                final_rows.append(op)
                new_count += 1

        # Sort by operationId for consistency
        final_rows.sort(key=lambda x: x["operationId"])

        # Write CSV
        write_csv(csv_path, final_rows, fieldnames)

        total_operations += len(final_rows)
        new_operations += new_count
        preserved_operations += preserved_count

        status = ""
        if preserved_count > 0:
            if updated_count > 0:
                status = f"({new_count} new, {preserved_count} preserved, {updated_count} objectKey updated)"
            else:
                status = f"({new_count} new, {preserved_count} preserved)"
        else:
            status = f"({new_count} operations)"

        print(f"  {service_name}: {len(final_rows)} operations {status}")

    print("=" * 60)
    print(f"Total: {total_services} services, {total_operations} operations")
    print(f"  New: {new_operations}, Preserved: {preserved_operations}")
    print(f"\nCSV files written to: {output_dir.resolve()}")
    print("\nNext steps:")
    print("  1. Review and modify CSV files as needed")
    print("  2. Run: python process_models.py")


if __name__ == "__main__":
    main()
