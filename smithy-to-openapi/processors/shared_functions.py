# processors/shared_functions.py

import sys,html2text
import csv
from yaml.representer import SafeRepresenter
from datetime import date
from pathlib import Path
from collections import defaultdict
import yaml
import re

# Provider version constant
PROVIDER_VERSION = "v00.00.00000"

# Valid SQL verbs for validation
VALID_SQL_VERBS = {"exec", "insert", "select", "update", "replace", "delete"}

# Track all processed services for provider.yaml generation
_processed_services = []

# Cache for loaded CSV manifests (service_name -> {operationId -> row})
_csv_manifests = {}

# Path to stackql-routes directory
_ROUTES_DIR = Path("smithy-to-openapi/stackql-routes")

class LiteralStr(str): pass

def literal_str_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")

# Custom YAML Dumper that quotes strings that would be interpreted as booleans
class SafeQuoteDumper(yaml.Dumper):
    pass

def safe_str_representer(dumper, data):
    if data in ('y', 'Y', 'n', 'N', 'yes', 'Yes', 'YES', 'no', 'No', 'NO', 
                'true', 'True', 'TRUE', 'false', 'False', 'FALSE',
                'on', 'On', 'ON', 'off', 'Off', 'OFF'):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

SafeQuoteDumper.add_representer(str, safe_str_representer)
SafeQuoteDumper.add_representer(LiteralStr, literal_str_representer)

def html_to_md(html_str: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = sys.maxsize  # prevent line wrapping
    h.skip_internal_links = True
    return h.handle(html_str).strip()

def to_snake_case(name: str) -> str:
    """
    Convert a string from PascalCase/camelCase to snake_case.
    Also removes illegal characters like +, -, etc.

    Examples:
    - SomethingArn -> something_arn
    - dataProtectionSettingsArn+ -> data_protection_settings_arn
    - BucketName -> bucket_name
    """
    if not name:
        return ""

    # Remove illegal characters (anything that's not alphanumeric or underscore)
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)

    # Convert from PascalCase/camelCase to snake_case
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    name = name.lower()

    return name


def derive_method_name(operation_id: str) -> str:
    """
    Derive the method name from the operationId.

    Extracts the verb/action and converts to snake_case.

    Examples:
    - DescribeAutoScalingGroups -> describe_auto_scaling_groups
    - CreateLaunchConfiguration -> create_launch_configuration
    - GetObject -> get_object
    - ListBuckets -> list_buckets
    """
    return to_snake_case(operation_id)


def load_csv_manifest(service_name: str) -> dict:
    """
    Load the CSV manifest for a service if it exists.

    Args:
        service_name: The service name (e.g., 'ec2', 's3', 'lambda')

    Returns:
        Dictionary mapping operationId to row data, or empty dict if no manifest exists.
    """
    global _csv_manifests

    # Normalize service name
    service_name = service_name.replace("-", "_")

    # Check cache first
    if service_name in _csv_manifests:
        return _csv_manifests[service_name]

    # Try to load from file
    csv_path = _ROUTES_DIR / f"{service_name}.csv"
    if not csv_path.exists():
        _csv_manifests[service_name] = {}
        return {}

    manifest = {}
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                manifest[row["operationId"]] = row
        _csv_manifests[service_name] = manifest
        print(f"  Loaded CSV manifest with {len(manifest)} operations for {service_name}")
    except Exception as e:
        print(f"  Warning: Failed to load CSV manifest for {service_name}: {e}")
        _csv_manifests[service_name] = {}

    return manifest


def get_operation_config(service_name: str, operation_id: str, http_method: str) -> dict:
    """
    Get operation configuration from CSV manifest.

    The CSV manifest's 'resource' and 'sqlVerb' columns MUST contain values
    for all operations. This function will raise an error if either is missing.

    Args:
        service_name: The service name
        operation_id: The operation ID (e.g., 'DescribeInstances')
        http_method: The HTTP method (e.g., 'GET', 'POST')

    Returns:
        Dictionary with keys: resource_name, method_name, stackql_verb, object_key,
        and optionally pagination override fields.
    
    Raises:
        SystemExit: If the operation is not found in CSV manifest or if resource/sqlVerb is missing
    """
    manifest = load_csv_manifest(service_name)

    if operation_id not in manifest:
        print(f"❌ ERROR: Operation '{operation_id}' not found in CSV manifest for service '{service_name}'")
        print(f"   Please add this operation to stackql-routes/{service_name}.csv with resource and sqlVerb defined")
        sys.exit(1)

    row = manifest[operation_id]

    # Resource name: MUST be provided in CSV
    resource_name = row.get("resource", "").strip()
    if not resource_name:
        print(f"❌ ERROR: Missing 'resource' field for operation '{operation_id}' in service '{service_name}'")
        print(f"   Please update stackql-routes/{service_name}.csv to include a resource name for this operation")
        sys.exit(1)

    # SQL verb: MUST be provided in CSV and be a valid verb
    stackql_verb = row.get("sqlVerb", "").strip()
    if not stackql_verb:
        print(f"❌ ERROR: Missing 'sqlVerb' field for operation '{operation_id}' in service '{service_name}'")
        print(f"   Please update stackql-routes/{service_name}.csv to include a sqlVerb for this operation")
        sys.exit(1)
    
    # Validate that sqlVerb is one of the allowed values
    if stackql_verb not in VALID_SQL_VERBS:
        print(f"❌ ERROR: Invalid 'sqlVerb' value '{stackql_verb}' for operation '{operation_id}' in service '{service_name}'")
        print(f"   Valid sqlVerbs are: {', '.join(sorted(VALID_SQL_VERBS))}")
        print(f"   Please update stackql-routes/{service_name}.csv to use a valid sqlVerb")
        sys.exit(1)

    config = {
        "resource_name": resource_name,
        "method_name": row.get("method", "").strip() or derive_method_name(operation_id),
        "stackql_verb": stackql_verb,
        "object_key": row.get("objectKey", "").strip(),
    }

    # Add pagination overrides if present (operation-level overrides)
    if row.get("reqPaginationKey", "").strip():
        config["req_pagination_key"] = row["reqPaginationKey"].strip()
        config["req_pagination_location"] = row.get("reqPaginationLocation", "body").strip() or "body"
    if row.get("respPaginationKey", "").strip():
        config["resp_pagination_key"] = row["respPaginationKey"].strip()
        config["resp_pagination_location"] = row.get("respPaginationLocation", "body").strip() or "body"

    return config


def clear_csv_manifests():
    """Clear the CSV manifest cache."""
    global _csv_manifests
    _csv_manifests = {}


def init_openapi_spec(service_name, service_dir, protocol, version=None, filename=None):
    info = {
        "contact": {
            "name": "StackQL Studios",
            "url": "https://stackql.io/",
            "email": "info@stackql.io"
        }
    }

    # Add GitHub deep link to model file if version and filename are provided
    if version and filename:
        info["x-aws-modelFile"] = f"https://github.com/aws/api-models-aws/tree/main/models/{service_dir}/service/{version}/{filename}"

    return {
        "openapi": "3.1.0",
        "info": info,
        "servers": [],
        "paths": {},
        "components": {
            "schemas": {},
            "x-stackQL-resources": {}
        },
        # Internal tracking for building resources (removed before output)
        "_stackql_operations": [],
        "_service_name": service_dir.replace("-", "_"),
        "_aws_service_name": service_name,
        "_aws_protocol": protocol
    }

def add_info(openapi_spec, service_shape, version=None, service_dir=None):
    # Use version from service_shape, or fall back to passed version parameter
    if "version" in service_shape:
        openapi_spec["info"]["version"] = service_shape["version"]
    elif version:
        openapi_spec["info"]["version"] = version
    openapi_spec["info"]["title"] = service_shape["traits"]["smithy.api#title"]
    openapi_spec["info"]["description"] = LiteralStr(html_to_md(service_shape["traits"]["smithy.api#documentation"]))
    # Add x-serviceName from aws.auth#sigv4.name trait
    if "aws.auth#sigv4" in service_shape.get("traits", {}):
        if "name" in service_shape["traits"]["aws.auth#sigv4"]:
            openapi_spec["info"]["x-serviceName"] = service_shape["traits"]["aws.auth#sigv4"]["name"]

def add_servers(openapi_spec, service_dir, service_shape):

    endpoint_prefix = service_dir

    if "aws.api#service" in service_shape["traits"]:
        if "endpointPrefix" in service_shape["traits"]["aws.api#service"]:
            endpoint_prefix = service_shape["traits"]["aws.api#service"]["endpointPrefix"]

    if endpoint_prefix == service_dir:
        if "aws.auth#sigv4" in service_shape["traits"]:
            if "name" in service_shape["traits"]["aws.auth#sigv4"]:
                endpoint_prefix = service_shape["traits"]["aws.auth#sigv4"]["name"]

    service_title = service_shape["traits"]["smithy.api#title"]

    global_regionless_services = ["route53", "cloudfront", "iam"]

    servers_block = [
        {
            "description": f"The {service_title} multi-region endpoint" if endpoint_prefix in global_regionless_services else f"The {service_title} regional endpoint",
            "url": f"https://{endpoint_prefix}.amazonaws.com" if endpoint_prefix in global_regionless_services else f"https://{endpoint_prefix}.{{region}}.amazonaws.com",
            "variables": {
                "region": {
                    "description": "The AWS region",
                    "enum": [
                        "us-east-1", "us-east-2", "us-west-1", "us-west-2",
                        "us-gov-west-1", "us-gov-east-1",
                        "ca-central-1", "eu-north-1", "eu-west-1", "eu-west-2", "eu-west-3",
                        "eu-central-1", "eu-south-1",
                        "af-south-1",
                        "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
                        "ap-southeast-1", "ap-southeast-2", "ap-east-1", "ap-south-1",
                        "sa-east-1", "me-south-1"
                    ],
                    "default": "us-east-1"
                }
            }
        }
    ]

    openapi_spec["servers"] = servers_block
    return openapi_spec

def add_component_schema_string(openapi_spec, shape_name, shape):
    short_name = shape_name.split("#")[-1]

    schema = {
        "type": "string"
    }

    traits = shape.get("traits", {})

    # Description
    if "smithy.api#description" in traits:
        schema["description"] = traits["smithy.api#description"]

    # Enum values
    if "smithy.api#enum" in traits:
        schema["enum"] = [entry["value"] for entry in traits["smithy.api#enum"]]

    # Pattern constraint
    if "smithy.api#pattern" in traits:
        schema["pattern"] = traits["smithy.api#pattern"]

    # Length constraints
    if "smithy.api#length" in traits:
        length = traits["smithy.api#length"]
        if "min" in length:
            schema["minLength"] = length["min"]
        if "max" in length:
            schema["maxLength"] = length["max"]

    openapi_spec["components"]["schemas"][short_name] = schema

def add_component_schema_boolean(openapi_spec, shape_name, shape):
    # Strip namespace if present
    if "#" in shape_name:
        shape_name = shape_name.split("#")[-1]

    schema = {
        "type": "boolean"
    }

    traits = shape.get("traits", {})

    # Optional default value
    if "smithy.api#default" in traits:
        schema["default"] = traits["smithy.api#default"]

    # Optional description
    if "smithy.api#documentation" in traits:
        schema["description"] = traits["smithy.api#documentation"]

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_integer(openapi_spec, shape_name, shape):
    # Remove Smithy namespace prefix
    if "#" in shape_name:
        shape_name = shape_name.split("#")[-1]

    schema = {
        "type": "integer"
    }

    traits = shape.get("traits", {})

    # Add default if present
    if "smithy.api#default" in traits:
        schema["default"] = traits["smithy.api#default"]

    # Add range (min/max)
    if "smithy.api#range" in traits:
        range_trait = traits["smithy.api#range"]
        if "min" in range_trait:
            schema["minimum"] = range_trait["min"]
        if "max" in range_trait:
            schema["maximum"] = range_trait["max"]

    # Add description
    if "smithy.api#documentation" in traits:
        schema["description"] = traits["smithy.api#documentation"]

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_timestamp(openapi_spec, shape_name, shape):
    # Strip namespace prefix
    if "#" in shape_name:
        shape_name = shape_name.split("#")[-1]

    schema = {
        "type": "string",
        "format": "date-time"  # Default to standard timestamp format
    }

    traits = shape.get("traits", {})

    # Optional override if smithy.api#timestampFormat exists and is OpenAPI-compatible
    ts_format = traits.get("smithy.api#timestampFormat")
    if ts_format in ("date-time", "date"):
        schema["format"] = ts_format

    # Optional documentation
    if "smithy.api#documentation" in traits:
        schema["description"] = traits["smithy.api#documentation"]

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_double(openapi_spec, shape_name, shape):
    # Strip namespace prefix
    if "#" in shape_name:
        shape_name = shape_name.split("#")[-1]

    schema = {
        "type": "number",
        "format": "double"
    }

    traits = shape.get("traits", {})

    # Optional documentation
    if "smithy.api#documentation" in traits:
        schema["description"] = traits["smithy.api#documentation"]

    # Optional default value
    if "smithy.api#default" in traits:
        schema["default"] = traits["smithy.api#default"]

    # Optional range
    range_trait = traits.get("smithy.api#range", {})
    if "min" in range_trait:
        schema["minimum"] = range_trait["min"]
    if "max" in range_trait:
        schema["maximum"] = range_trait["max"]

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_float(openapi_spec, shape_name, shape):
    shape_name = shape_name.split("#")[-1]  # strip Smithy prefix
    schema = {
        "type": "number",
        "format": "float"
    }

    traits = shape.get("traits", {})

    # Optional documentation
    doc = traits.get("smithy.api#documentation")
    if doc:
        schema["description"] = doc.strip()

    # Optional default
    if "smithy.api#default" in traits:
        schema["default"] = traits["smithy.api#default"]

    # Optional range
    range_trait = traits.get("smithy.api#range", {})
    if "min" in range_trait:
        schema["minimum"] = range_trait["min"]
    if "max" in range_trait:
        schema["maximum"] = range_trait["max"]

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_long(openapi_spec, shape_name, shape):
    shape_name = shape_name.split("#")[-1]  # remove Smithy prefix
    schema = {
        "type": "integer",
        "format": "int64"
    }

    traits = shape.get("traits", {})

    # Optional documentation
    doc = traits.get("smithy.api#documentation")
    if doc:
        schema["description"] = doc.strip()

    # Optional default
    if "smithy.api#default" in traits:
        schema["default"] = traits["smithy.api#default"]

    # Optional range
    range_trait = traits.get("smithy.api#range", {})
    if "min" in range_trait:
        schema["minimum"] = range_trait["min"]
    if "max" in range_trait:
        schema["maximum"] = range_trait["max"]

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_blob(openapi_spec, shape_name, shape):
    shape_name = shape_name.split("#")[-1]  # remove Smithy prefix
    schema = {
        "type": "string",
        "format": "byte"
    }

    traits = shape.get("traits", {})

    # Optional documentation
    doc = traits.get("smithy.api#documentation")
    if doc:
        schema["description"] = doc.strip()

    # Optional length constraints
    length = traits.get("smithy.api#length", {})
    if "min" in length:
        schema["minLength"] = length["min"]
    if "max" in length:
        schema["maxLength"] = length["max"]

    # Optional sensitive marker
    if "smithy.api#sensitive" in traits:
        schema["x-sensitive"] = True  # optional custom extension

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_enum(openapi_spec, shape_name, shape):
    shape_name = shape_name.split("#")[-1]  # Remove Smithy prefix
    schema = {
        "type": "string",
        "enum": []
    }

    members = shape.get("members", {})
    for name, member in members.items():
        traits = member.get("traits", {})
        enum_value = traits.get("smithy.api#enumValue", name)
        schema["enum"].append(enum_value)

    # Optional documentation for the enum
    doc = shape.get("traits", {}).get("smithy.api#documentation")
    if doc:
        schema["description"] = doc.strip()

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_map(openapi_spec, shape_name, shape):
    shape_name = shape_name.split("#")[-1]
    schema = {
        "type": "object"
    }

    # Get value type
    value_target = shape.get("value", {}).get("target", "smithy.api#String")
    value_type = value_target.split("#")[-1].lower()

    # Handle scalar types
    scalar_map = {
        "string": {"type": "string"},
        "boolean": {"type": "boolean"},
        "integer": {"type": "integer"},
        "long": {"type": "integer", "format": "int64"},
        "float": {"type": "number", "format": "float"},
        "double": {"type": "number", "format": "double"},
        "blob": {"type": "string", "format": "byte"},
        "timestamp": {"type": "string", "format": "date-time"}
    }

    if value_type in scalar_map:
        schema["additionalProperties"] = scalar_map[value_type]
    else:
        # Assume reference to another component
        schema["additionalProperties"] = {
            "$ref": f"#/components/schemas/{value_type}"
        }

    # Optional documentation
    doc = shape.get("traits", {}).get("smithy.api#documentation")
    if doc:
        schema["description"] = doc.strip()

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_document(openapi_spec, shape_name, shape):
    shape_name = shape_name.split("#")[-1]

    schema = {
        "type": "object",
        "additionalProperties": True  # allows any JSON structure
    }

    traits = shape.get("traits", {})

    # Add optional description
    if "smithy.api#documentation" in traits:
        schema["description"] = traits["smithy.api#documentation"].strip()

    # Add sensitivity marker (optional)
    if "smithy.api#sensitive" in traits:
        schema["x-sensitive"] = True

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_list(openapi_spec, shape_name, shape):
    shape_name = shape_name.split("#")[-1]

    schema = {
        "type": "array",
        "items": {}
    }

    traits = shape.get("traits", {})
    member = shape.get("member", {})
    target = member.get("target", "")

    scalar_map = {
        "smithy.api#string": "string",
        "smithy.api#integer": "integer",
        "smithy.api#boolean": "boolean",
        "smithy.api#timestamp": "string",
        "smithy.api#double": "number",
        "smithy.api#float": "number",
        "smithy.api#long": "integer",
        "smithy.api#blob": "string",
        "smithy.api#document": "object",
    }

    if target.lower() in scalar_map:
        schema["items"] = {
            "type": scalar_map[target.lower()]
        }
        if target.lower() == "smithy.api#timestamp":
            schema["items"]["format"] = "date-time"
        elif target.lower() == "smithy.api#blob":
            schema["items"]["format"] = "byte"
    else:
        ref_name = target.split("#")[-1]
        schema["items"] = {"$ref": f"#/components/schemas/{ref_name}"}

    if "smithy.api#documentation" in traits:
        schema["description"] = traits["smithy.api#documentation"].strip()

    if "smithy.api#sensitive" in traits:
        schema["x-sensitive"] = True

    openapi_spec["components"]["schemas"][shape_name] = schema

def add_component_schema_union(openapi_spec, shape_name, shape):
    # Remove Smithy namespace prefix for OpenAPI schema name
    short_name = shape_name.split("#")[-1]

    schema = {
        "allOf": []
    }

    # Optional top-level documentation
    traits = shape.get("traits", {})
    if "smithy.api#documentation" in traits:
        schema["description"] = LiteralStr(html_to_md(traits["smithy.api#documentation"]))

    # Optional sensitive trait
    if "smithy.api#sensitive" in traits:
        schema["x-sensitive"] = True

    # Each member becomes an entry in allOf
    for member_name, member_def in shape.get("members", {}).items():
        target = member_def.get("target")
        ref_name = target.split("#")[-1]

        member_schema = {
            "$ref": f"#/components/schemas/{ref_name}"
        }

        # Inline description if available
        member_traits = member_def.get("traits", {})
        if "smithy.api#documentation" in member_traits:
            member_schema["description"] = LiteralStr(html_to_md(member_traits["smithy.api#documentation"]))

        schema["allOf"].append(member_schema)

    openapi_spec["components"]["schemas"][short_name] = schema

def add_component_schema_structure(openapi_spec, shape_name, shape):
    short_name = shape_name.split("#")[-1]
    schema = {
        "type": "object",
        "properties": {},
        "required": []
    }

    traits = shape.get("traits", {})

    # Optional top-level documentation
    if "smithy.api#documentation" in traits:
        schema["description"] = html_to_md(traits["smithy.api#documentation"])

    members = shape.get("members", {})
    for member_name, member_def in members.items():
        target = member_def.get("target")
        ref_name = target.split("#")[-1]

        member_schema = {
            "$ref": f"#/components/schemas/{ref_name}"
        }

        member_traits = member_def.get("traits", {})

        # Inline documentation - OpenAPI 3.1 allows description alongside $ref
        if "smithy.api#documentation" in member_traits:
            member_schema["description"] = html_to_md(member_traits["smithy.api#documentation"])

        # Check for required trait
        if "smithy.api#required" in member_traits:
            schema["required"].append(member_name)

        schema["properties"][member_name] = member_schema

    # Clean up empty 'required' list to avoid clutter
    if not schema["required"]:
        del schema["required"]

    openapi_spec["components"]["schemas"][short_name] = schema

def add_operation(openapi_spec, shape_name, shape, shapes):
    operation_id = shape_name.split("#")[-1]
    print(f"adding operation {operation_id}")

    # process traits
    traits = shape.get("traits", {})
    http = traits.get("smithy.api#http", {})
    original_path = http.get("uri", None)
    verb = http.get("method", None)
    if verb:
        verb = verb.lower()

    if original_path is None or verb is None:
        return

    # Convert path parameters to snake_case
    # Extract param names, convert them, and rebuild the path
    path = original_path
    param_pattern = re.compile(r'\{([^}]+)\}')
    
    def convert_param(match):
        param_name = match.group(1)
        snake_param = to_snake_case(param_name)
        return f'{{{snake_param}}}'
    
    path = param_pattern.sub(convert_param, original_path)

    success_code = http.get("code", 200)

    if path not in openapi_spec["paths"]:
        openapi_spec["paths"][path] = {}
    if verb not in openapi_spec["paths"][path]:
        openapi_spec["paths"][path][verb] = {}
    openapi_spec["paths"][path][verb]["operationId"] = operation_id
    if "smithy.api#documentation" in traits:
        description = LiteralStr(html_to_md(shape["traits"]["smithy.api#documentation"]))
        openapi_spec["paths"][path][verb]["description"] = description

    # Track operation info for building StackQL resources later
    # Note: Resource name, method name, and SQL verb will be resolved from CSV manifest
    # in build_stackql_resources() using get_operation_config()
    openapi_spec["_stackql_operations"].append({
        "operation_id": operation_id,
        "path": path,
        "http_method": verb,
        "success_code": str(success_code),
        "shape_name": shape_name
    })

    input_shape_name = shape.get("input", {}).get("target")
    required_body_params = []  # Track required body parameters
    
    if input_shape_name and input_shape_name != "smithy.api#Unit":
        input_shape = shapes[input_shape_name]
        members = input_shape.get("members", {})
        parameters = []
        body_fields = {}

        for member_name, member_def in members.items():
            traits = member_def.get("traits", {})
            target = member_def["target"]
            ref_name = target.split("#")[-1]
            is_required = "smithy.api#required" in traits

            if "smithy.api#httpLabel" in traits:
                # Convert path parameter name to snake_case
                snake_param_name = to_snake_case(member_name)
                parameters.append({
                    "name": snake_param_name,
                    "in": "path",
                    "required": is_required,
                    "schema": { "$ref": f"#/components/schemas/{ref_name}" }
                })
            elif "smithy.api#httpQuery" in traits:
                param_name = traits["smithy.api#httpQuery"]
                parameters.append({
                    "name": param_name,
                    "in": "query",
                    "required": is_required,
                    "schema": { "$ref": f"#/components/schemas/{ref_name}" }
                })
            elif "smithy.api#httpHeader" in traits:
                param_name = traits["smithy.api#httpHeader"]
                parameters.append({
                    "name": param_name,
                    "in": "header",
                    "required": is_required,
                    "schema": { "$ref": f"#/components/schemas/{ref_name}" }
                })
            else:
                # default: treat as part of the body
                body_fields[member_name] = { "$ref": f"#/components/schemas/{ref_name}" }
                # Track required body parameters
                if is_required:
                    required_body_params.append(member_name)

        openapi_spec["paths"][path][verb]["parameters"] = parameters

        if body_fields:
            body_schema = {
                "type": "object",
                "properties": body_fields
            }
            # Add required array if there are required body params
            if required_body_params:
                body_schema["required"] = required_body_params
            
            openapi_spec["paths"][path][verb]["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": body_schema
                    }
                }
            }

    # process output
    openapi_spec["paths"][path][verb]["responses"] = {}

    # Handle success response with output shape
    output_shape_name = shape.get("output", {}).get("target")
    if output_shape_name and output_shape_name != "smithy.api#Unit":
        output_ref_name = output_shape_name.split("#")[-1]
        openapi_spec["paths"][path][verb]["responses"][str(success_code)] = {
            "description": "Success",
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{output_ref_name}"}
                }
            }
        }
    else:
        # No output or Unit output - empty response
        openapi_spec["paths"][path][verb]["responses"][str(success_code)] = {
            "description": "Success"
        }

    if "errors" in shape:
        for error in shape["errors"]:
            error_component_name = error["target"].split("#")[-1]
            print(f"adding error {error_component_name}")
            error_shape = shapes[error["target"]]
            if "smithy.api#httpError" in error_shape["traits"]:
                error_code = error_shape["traits"]["smithy.api#httpError"]
            else:
                error_code = 400

            openapi_spec["paths"][path][verb]["responses"][str(error_code)] = {}
            if "smithy.api#documentation" in error_shape["traits"]:
                openapi_spec["paths"][path][verb]["responses"][str(error_code)]["description"] = LiteralStr(html_to_md(error_shape["traits"]["smithy.api#documentation"]))
            openapi_spec["paths"][path][verb]["responses"][str(error_code)]["content"] = {}
            openapi_spec["paths"][path][verb]["responses"][str(error_code)]["content"]["application/json"] = {}
            openapi_spec["paths"][path][verb]["responses"][str(error_code)]["content"]["application/json"]["schema"] = {}
            openapi_spec["paths"][path][verb]["responses"][str(error_code)]["content"]["application/json"]["schema"]["$ref"] = f"#/components/schemas/{error_component_name}"

def detect_pagination_scheme(shapes, protocol):
    """
    Detect pagination scheme used across all operations in a service.
    
    Analyzes smithy.api#paginated traits to determine:
    - Request token key name (e.g., 'NextToken', 'ContinuationToken')
    - Request token location ('query', 'header', or 'body')
    - Response token key name (e.g., 'NextToken', 'ContinuationToken')
    - Response token location ('body' or 'header')
    
    Args:
        shapes: Dictionary of all shapes in the service
        protocol: The AWS protocol being used (e.g., 'aws.protocols#restJson1')
    
    Returns:
        Dictionary with pagination metadata:
        {
            'dominant_scheme': {
                'request_key': 'NextToken',
                'request_location': 'body',
                'response_key': 'NextToken',
                'response_location': 'body'
            },
            'exceptions': {
                'OperationName': {
                    'request_key': 'NextToken',
                    'request_location': 'query',
                    'response_key': 'NextToken',
                    'response_location': 'body'
                }
            }
        }
        Returns None if no pagination found.
    """
    pagination_schemes = []
    operation_details = []  # Track which operations use which schemes
    
    for shape_name, shape in shapes.items():
        if shape.get("type") != "operation":
            continue
            
        traits = shape.get("traits", {})
        pagination_trait = traits.get("smithy.api#paginated")
        
        if not pagination_trait:
            continue
        
        # Extract pagination token names from trait
        input_token = pagination_trait.get("inputToken")
        output_token = pagination_trait.get("outputToken")
        
        if not input_token or not output_token:
            continue
        
        # Determine request location based on protocol and input shape
        request_location = "body"  # Default for most AWS protocols
        response_location = "body"  # Responses are almost always in body
        
        # Check the input shape to see if the token is in query/header/body
        input_shape_name = shape.get("input", {}).get("target")
        if input_shape_name and input_shape_name in shapes:
            input_shape = shapes[input_shape_name]
            members = input_shape.get("members", {})
            
            if input_token in members:
                member_traits = members[input_token].get("traits", {})
                
                # Check for HTTP binding traits
                if "smithy.api#httpQuery" in member_traits:
                    request_location = "query"
                elif "smithy.api#httpHeader" in member_traits:
                    request_location = "header"
                # else: defaults to "body"
        
        # Response tokens are typically in the body for AWS services
        # but we should verify this
        output_shape_name = shape.get("output", {}).get("target")
        if output_shape_name and output_shape_name in shapes:
            output_shape = shapes[output_shape_name]
            members = output_shape.get("members", {})
            
            if output_token in members:
                member_traits = members[output_token].get("traits", {})
                
                # Check for HTTP binding traits (rare for responses but possible)
                if "smithy.api#httpHeader" in member_traits:
                    response_location = "header"
                # else: defaults to "body"
        
        scheme = {
            'request_key': input_token,
            'request_location': request_location,
            'response_key': output_token,
            'response_location': response_location
        }
        
        operation_name = shape_name.split("#")[-1]
        pagination_schemes.append(scheme)
        operation_details.append((operation_name, scheme, shape_name))
    
    # Check if we found any pagination
    if not pagination_schemes:
        return None
    
    # Find the dominant scheme (most common one)
    scheme_to_ops = {}
    for op_name, op_scheme, shape_name in operation_details:
        scheme_key = (op_scheme['request_key'], op_scheme['request_location'],
                     op_scheme['response_key'], op_scheme['response_location'])
        if scheme_key not in scheme_to_ops:
            scheme_to_ops[scheme_key] = []
        scheme_to_ops[scheme_key].append((op_name, shape_name))
    
    # Sort by count (descending) to find the dominant scheme
    sorted_schemes = sorted(scheme_to_ops.items(), key=lambda x: len(x[1]), reverse=True)
    dominant_scheme_key, dominant_ops = sorted_schemes[0]
    
    # Build the dominant scheme dictionary
    dominant_scheme = {
        'request_key': dominant_scheme_key[0],
        'request_location': dominant_scheme_key[1],
        'response_key': dominant_scheme_key[2],
        'response_location': dominant_scheme_key[3]
    }
    
    # Find exceptions (operations that differ from dominant scheme)
    exceptions = {}
    for scheme_key, ops in sorted_schemes[1:]:
        exception_scheme = {
            'request_key': scheme_key[0],
            'request_location': scheme_key[1],
            'response_key': scheme_key[2],
            'response_location': scheme_key[3]
        }
        for op_name, shape_name in ops:
            exceptions[shape_name] = exception_scheme
    
    return {
        'dominant_scheme': dominant_scheme,
        'exceptions': exceptions
    }

def add_pagination_to_info(openapi_spec, pagination_data):
    """
    Store pagination data in the spec for later use when building StackQL config.

    Args:
        openapi_spec: The OpenAPI specification dictionary
        pagination_data: Dictionary with dominant_scheme and exceptions from detect_pagination_scheme
    """
    if not pagination_data:
        openapi_spec["_pagination_data"] = None
        return

    openapi_spec["_pagination_data"] = pagination_data

def add_pagination_to_operation(openapi_spec, shape_name, operation_spec):
    """
    No longer adds operation-level pagination metadata directly.
    This is now handled during resource building in build_stackql_resources.
    Kept for backwards compatibility with processor calls.
    """
    pass

def _escape_path_for_ref(path: str) -> str:
    """Escape a path string for use in JSON pointer ($ref)."""
    # JSON pointer requires ~ to be encoded as ~0, / as ~1
    return path.replace("~", "~0").replace("/", "~1")

def _count_required_params(openapi_spec, path, http_method):
    """
    Count required parameters for an operation (path + non-X-Amz query + body params).
    Used for sorting methods by specificity.
    
    Returns:
        Integer count of required parameters
    """
    path_def = openapi_spec.get("paths", {}).get(path, {})
    method_def = path_def.get(http_method, {})
    
    count = 0
    
    # Count required path and query parameters (excluding X-Amz headers)
    for param in method_def.get("parameters", []):
        if param.get("required", False):
            param_in = param.get("in", "")
            param_name = param.get("name", "")
            
            # Count path params
            if param_in == "path":
                count += 1
            # Count query params that don't start with X-Amz
            elif param_in == "query" and not param_name.startswith("X-Amz"):
                count += 1
            # Skip header params per requirement
    
    # Count required body parameters
    request_body = method_def.get("requestBody", {})
    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    required_body = schema.get("required", [])
    count += len(required_body)
    
    return count


def _get_media_types_from_path(openapi_spec, path, http_method, success_code):
    """
    Extract the actual request and response mediaTypes from the path definition.

    Returns:
        Tuple of (request_media_type, response_media_type) where request_media_type
        may be None if no requestBody exists.
    """
    request_media_type = None
    response_media_type = "application/json"  # Default fallback

    path_def = openapi_spec.get("paths", {}).get(path, {})
    method_def = path_def.get(http_method, {})

    # Get request mediaType from requestBody if it exists
    request_body = method_def.get("requestBody", {})
    content = request_body.get("content", {})
    if content:
        # Get the first (and typically only) content type key
        request_media_type = next(iter(content.keys()), None)

    # Get response mediaType from the success response
    responses = method_def.get("responses", {})
    success_response = responses.get(success_code, responses.get(str(success_code), {}))
    response_content = success_response.get("content", {})
    if response_content:
        # Get the first (and typically only) content type key
        response_media_type = next(iter(response_content.keys()), "application/json")

    return request_media_type, response_media_type


def build_stackql_resources(openapi_spec):
    """
    Build the x-stackQL-resources section from tracked operations.

    Groups operations by resource name (from CSV manifest), creates methods
    referencing paths, and builds sqlVerbs mappings.

    Pagination overrides at the operation level are added to method definitions
    when they differ from the service-level pagination configuration.
    """
    service_name = openapi_spec.get("_service_name", "unknown")
    operations = openapi_spec.get("_stackql_operations", [])
    pagination_data = openapi_spec.get("_pagination_data")

    # Get service-level pagination scheme for comparison
    service_pagination = pagination_data.get("dominant_scheme") if pagination_data else None

    # Group operations by resource name
    resources = defaultdict(lambda: {
        "methods": {},
        "sqlVerbs": {
            "select": [],
            "insert": [],
            "update": [],
            "delete": []
        }
    })

    for op in operations:
        # Get operation config from CSV manifest (includes resource_name, method_name, pagination overrides)
        operation_id = op.get("operation_id", "").replace("GET_", "").replace("POST_", "")
        op_config = get_operation_config(service_name, operation_id, op["http_method"].upper())

        # Use CSV manifest values (with fallbacks already handled in get_operation_config)
        resource_name = op_config["resource_name"]
        method_name = op_config["method_name"]
        stackql_verb = op_config["stackql_verb"]
        object_key = op_config.get("object_key", "")

        path = op["path"]
        http_method = op["http_method"]
        success_code = op["success_code"]

        # Get actual mediaTypes from the path definition
        request_media_type, response_media_type = _get_media_types_from_path(
            openapi_spec, path, http_method, success_code
        )

        # Build the path reference for the operation
        escaped_path = _escape_path_for_ref(path)
        operation_ref = f"#/paths/{escaped_path}/{http_method}"

        # Build method definition
        method_def = {
            "operation": {
                "$ref": operation_ref
            },
            "response": {
                "mediaType": response_media_type,
                "openAPIDocKey": success_code
            }
        }

        # Add objectKey if specified in CSV manifest
        if object_key:
            method_def["response"]["objectKey"] = object_key

        # Add request mediaType if the operation has a requestBody
        if request_media_type:
            method_def["request"] = {
                "mediaType": request_media_type
            }
            
            # Extract required body parameters from the path definition
            path_def = openapi_spec.get("paths", {}).get(path, {})
            method_path_def = path_def.get(http_method, {})
            request_body = method_path_def.get("requestBody", {})
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema", {})
            required_body = schema.get("required", [])
            
            if required_body:
                method_def["request"]["required"] = required_body

        # Add operation-level pagination override if it differs from service-level
        if "req_pagination_key" in op_config or "resp_pagination_key" in op_config:
            # Check if this differs from service-level pagination
            needs_override = False
            if service_pagination:
                req_key = op_config.get("req_pagination_key", "")
                req_loc = op_config.get("req_pagination_location", "body")
                resp_key = op_config.get("resp_pagination_key", "")
                resp_loc = op_config.get("resp_pagination_location", "body")

                if (req_key != service_pagination.get("request_key", "") or
                    req_loc != service_pagination.get("request_location", "body") or
                    resp_key != service_pagination.get("response_key", "") or
                    resp_loc != service_pagination.get("response_location", "body")):
                    needs_override = True
            else:
                # No service-level pagination, so any operation-level pagination is an override
                needs_override = True

            if needs_override:
                pagination_override = {}
                if op_config.get("req_pagination_key"):
                    pagination_override["requestToken"] = {
                        "key": op_config["req_pagination_key"],
                        "location": op_config.get("req_pagination_location", "body")
                    }
                if op_config.get("resp_pagination_key"):
                    pagination_override["responseToken"] = {
                        "key": op_config["resp_pagination_key"],
                        "location": op_config.get("resp_pagination_location", "body")
                    }
                if pagination_override:
                    method_def["pagination"] = pagination_override

        resources[resource_name]["methods"][method_name] = method_def

        # Add to appropriate sqlVerb list (exec operations don't get added to sqlVerbs)
        if stackql_verb in resources[resource_name]["sqlVerbs"]:
            method_ref = f"#/components/x-stackQL-resources/{resource_name}/methods/{method_name}"
            # Track the required parameter count for sorting
            required_count = _count_required_params(openapi_spec, path, http_method)
            resources[resource_name]["sqlVerbs"][stackql_verb].append({
                "$ref": method_ref,
                "_required_count": required_count  # Temporary field for sorting
            })

    # Build final resource definitions
    stackql_resources = {}
    for resource_name, resource_data in sorted(resources.items()):
        # Sort each sqlVerb's methods by required parameter count (descending)
        # Most specific (most required params) come first
        sorted_sql_verbs = {}
        for verb, methods in resource_data["sqlVerbs"].items():
            # Sort by required count (descending), then remove the temporary field
            sorted_methods = sorted(methods, key=lambda m: m.get("_required_count", 0), reverse=True)
            # Remove temporary sorting field
            sorted_sql_verbs[verb] = [{"$ref": m["$ref"]} for m in sorted_methods]
        
        stackql_resources[resource_name] = {
            "id": f"aws.{service_name}.{resource_name}",
            "name": resource_name,
            "title": resource_name.replace("_", " ").title(),
            "methods": resource_data["methods"],
            "sqlVerbs": sorted_sql_verbs
        }

    openapi_spec["components"]["x-stackQL-resources"] = stackql_resources

def build_stackql_config(openapi_spec):
    """
    Build the x-stackQL-config section with AWS authentication and pagination.
    """
    service_name = openapi_spec.get("_service_name", "unknown")
    pagination_data = openapi_spec.get("_pagination_data")

    config = {
        "auth": {
            "type": "aws_signing_v4",
            "credentialsenvvar": "AWS_SECRET_ACCESS_KEY",
            "keyIDenvvar": "AWS_ACCESS_KEY_ID"
        }
    }

    # Add pagination config if detected
    if pagination_data and pagination_data.get("dominant_scheme"):
        scheme = pagination_data["dominant_scheme"]
        config["pagination"] = {
            "requestToken": {
                "key": scheme["request_key"],
                "location": scheme["request_location"]
            },
            "responseToken": {
                "key": scheme["response_key"],
                "location": scheme["response_location"]
            }
        }

    openapi_spec["x-stackQL-config"] = config

def resolve_orphaned_schemas(openapi_spec):
    """
    Resolve orphaned schema references by ensuring all $ref targets exist in components/schemas.
    
    This function:
    1. Collects all $ref references throughout the OpenAPI spec (paths, components, etc.)
    2. Identifies schemas that are referenced but not defined in components/schemas
    3. Creates placeholder definitions for orphaned schemas
    
    Common orphaned schemas include:
    - smithy.api#Unit (empty response/request type)
    - Other Smithy built-in types that weren't converted to components
    - Service-specific types that were missed during conversion
    
    Args:
        openapi_spec: The OpenAPI specification dictionary to validate and fix
    """
    import re
    import json
    
    # Get existing schema names
    existing_schemas = set(openapi_spec.get("components", {}).get("schemas", {}).keys())
    
    # Collect all referenced schema names
    referenced_schemas = set()
    
    def extract_refs(obj):
        """Recursively extract all $ref values from a nested object."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "$ref" and isinstance(value, str):
                    # Extract schema name from #/components/schemas/SchemaName
                    match = re.match(r'#/components/schemas/(.+)', value)
                    if match:
                        referenced_schemas.add(match.group(1))
                else:
                    extract_refs(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_refs(item)
    
    # Extract references from the entire spec
    extract_refs(openapi_spec)
    
    # Find orphaned schemas (referenced but not defined)
    orphaned_schemas = referenced_schemas - existing_schemas
    
    if orphaned_schemas:
        print(f"  WARNING: Found {len(orphaned_schemas)} orphaned schema(s): {', '.join(sorted(orphaned_schemas))}")
        
        # Ensure components/schemas exists
        if "components" not in openapi_spec:
            openapi_spec["components"] = {}
        if "schemas" not in openapi_spec["components"]:
            openapi_spec["components"]["schemas"] = {}
        
        # Create placeholder definitions for orphaned schemas
        for schema_name in sorted(orphaned_schemas):
            # Handle special cases
            if schema_name == "Unit":
                # Unit is Smithy's empty type - represent as empty object
                openapi_spec["components"]["schemas"][schema_name] = {
                    "type": "object",
                    "description": "Empty response (smithy.api#Unit)"
                }
            else:
                # For other orphaned schemas, create a generic object placeholder
                # This allows the OpenAPI spec to be valid while indicating something is missing
                openapi_spec["components"]["schemas"][schema_name] = {
                    "type": "object",
                    "description": f"Schema definition for {schema_name} (auto-generated placeholder)",
                    "x-orphaned": True
                }
        
        print(f"  ✓ Created placeholder definitions for orphaned schemas")

def add_protocol_to_info(openapi_spec):
    """
    Add the AWS model protocol to the info section of the OpenAPI spec.

    This adds the x-aws-modelProtocol extension to the info block, e.g.:
    info:
      x-aws-modelProtocol: aws.protocols#restJson1

    Args:
        openapi_spec: The OpenAPI specification dictionary
    """
    protocol = openapi_spec.get("_aws_protocol")
    if protocol:
        openapi_spec["info"]["x-aws-modelProtocol"] = protocol


def finalize_openapi_spec(openapi_spec):
    """
    Finalize the OpenAPI spec by building StackQL resources and config,
    then cleaning up internal tracking fields.
    """
    # Add protocol to info section
    add_protocol_to_info(openapi_spec)

    # Build StackQL resources from tracked operations
    build_stackql_resources(openapi_spec)

    # Build StackQL config with auth and pagination
    build_stackql_config(openapi_spec)

    # Clean up internal tracking fields
    internal_fields = [
        "_stackql_operations",
        "_service_name",
        "_aws_service_name",
        "_aws_protocol",
        "_pagination_data",
        "_pagination_exceptions"
    ]
    for field in internal_fields:
        if field in openapi_spec:
            del openapi_spec[field]

def write_output_yaml(openapi_spec, service_dir):
    global _processed_services

    # Finalize the spec (build resources, config, clean up)
    finalize_openapi_spec(openapi_spec)

    # Resolve any orphaned schema references
    resolve_orphaned_schemas(openapi_spec)

    # Create output directory structure
    outdir = Path(f"smithy-to-openapi/openapi/src/aws/{PROVIDER_VERSION}/services")
    outdir.mkdir(parents=True, exist_ok=True)

    service_name = service_dir.replace('-', '_')
    outfile = outdir / f"{service_name}.yaml"

    with open(outfile, "w", encoding="utf-8") as f:
        yaml.dump(openapi_spec, f, Dumper=SafeQuoteDumper, sort_keys=False, allow_unicode=True)

    print(f"  ✓ Wrote {outfile}")

    # Track this service for provider.yaml generation
    _processed_services.append({
        "name": service_name,
        "title": openapi_spec.get("info", {}).get("title", service_name),
        "description": openapi_spec.get("info", {}).get("description", ""),
        "version": openapi_spec.get("info", {}).get("version", "1.0.0")
    })

def get_processed_services():
    """Return the list of processed services."""
    global _processed_services
    return _processed_services

def reset_processed_services():
    """Reset the list of processed services (for testing)."""
    global _processed_services
    _processed_services = []

def generate_provider_yaml():
    """
    Generate the provider.yaml file that indexes all processed services.
    """
    global _processed_services

    if not _processed_services:
        print("⚠️  No services processed, skipping provider.yaml generation")
        return

    provider = {
        "id": "aws",
        "name": "aws",
        "title": "Amazon Web Services",
        "version": PROVIDER_VERSION,
        "description": "Cloud computing services from Amazon Web Services.",
        "providerServices": {}
    }

    # Add each service to providerServices
    for svc in sorted(_processed_services, key=lambda x: x["name"]):
        service_name = svc["name"]
        provider["providerServices"][service_name] = {
            "id": f"aws.{service_name}",
            "name": service_name,
            "title": svc["title"],
            "version": svc["version"],
            "description": svc.get("description", "")[:200] if svc.get("description") else "",
            "preferred": True,
            "service": {
                "$ref": f"aws/{PROVIDER_VERSION}/services/{service_name}.yaml"
            }
        }

    # Add provider-level config
    provider["config"] = {
        "auth": {
            "type": "aws_signing_v4",
            "credentialsenvvar": "AWS_SECRET_ACCESS_KEY",
            "keyIDenvvar": "AWS_ACCESS_KEY_ID"
        }
    }

    # Write provider.yaml
    outdir = Path(f"smithy-to-openapi/openapi/src/aws/{PROVIDER_VERSION}")
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "provider.yaml"

    with open(outfile, "w", encoding="utf-8") as f:
        yaml.dump(provider, f, Dumper=SafeQuoteDumper, sort_keys=False, allow_unicode=True)

    print(f"✓ Generated provider.yaml with {len(_processed_services)} services")
