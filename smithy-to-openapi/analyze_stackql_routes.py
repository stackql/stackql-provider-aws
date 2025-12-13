#!/usr/bin/env python3
"""
Analyze StackQL Routes

This script analyzes all AWS service models and generates CSV manifest files
for each service. These manifests contain inferred resource names, method names,
SQL verbs, and pagination configurations that can be reviewed and overridden
by humans before being used by process_models.py.

Usage:
    cd smithy-to-openapi
    python analyze_stackql_routes.py

Output:
    stackql-routes/{service}.csv - One CSV per service with operation mappings

CSV Format:
    operationId,path,verb,description,resource,method,sqlVerb,objectKey,
    reqPaginationKey,reqPaginationLocation,respPaginationKey,respPaginationLocation
"""

import csv
import json
import sys
import re
from pathlib import Path
from collections import defaultdict

# Import shared functions for deriving resource names, etc.
from processors.shared_functions import (
    derive_resource_name,
    derive_method_name,
    determine_stackql_verb,
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
        resource = derive_resource_name(operation_id)
        method = derive_method_name(operation_id)
        sql_verb = determine_stackql_verb(verb, operation_id)

        # Determine pagination overrides (only populated if different from service-level)
        req_pagination_key = ""
        req_pagination_location = ""
        resp_pagination_key = ""
        resp_pagination_location = ""

        # Check if this operation has pagination that differs from dominant scheme
        paginated_trait = traits.get("smithy.api#paginated")
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

        yield {
            "operationId": operation_id,
            "path": path,
            "verb": verb,
            "description": truncate_description(description),
            "resource": resource,
            "method": method,
            "sqlVerb": sql_verb,
            "objectKey": "",  # To be filled in by human review if needed
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
        final_rows = []
        new_count = 0
        preserved_count = 0

        for op in operations:
            op_id = op["operationId"]
            if op_id in existing_ops:
                # Preserve existing entry (may have human overrides)
                final_rows.append(existing_ops[op_id])
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
