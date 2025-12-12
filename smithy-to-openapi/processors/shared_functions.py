# processors/shared_functions.py

import sys,html2text
from yaml.representer import SafeRepresenter
from datetime import date
from pathlib import Path
import yaml
import inflect

# Initialize inflect engine for pluralization
_inflect_engine = inflect.engine()

class LiteralStr(str): pass

def literal_str_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")

def html_to_md(html_str: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = sys.maxsize  # prevent line wrapping
    h.skip_internal_links = True
    return h.handle(html_str).strip()

def derive_resource_name(operation_id: str) -> str:
    """
    Derive the resource name from the operationId.
    Resources are always plural by convention.
    
    Extracts the resource name by removing the first PascalCase token (the verb/action).
    
    Examples:
    - DescribeAutoScalingGroups -> auto_scaling_groups
    - CreateLaunchConfiguration -> launch_configurations
    - DescribeAttachments -> attachments
    - CreateAttachment -> attachments
    - AttachLoadBalancerTargetGroups -> load_balancer_target_groups
    - GetObject -> objects
    - ListBuckets -> buckets
    """
    import re
    
    if not operation_id:
        return ""
    
    # Match the first PascalCase token (verb) and capture the rest (noun/resource)
    # Pattern: ^([A-Z][a-z]+)(.*)
    # This captures:
    #   Group 1: First token starting with capital letter followed by lowercase letters (the verb)
    #   Group 2: Everything after (the resource name in PascalCase)
    match = re.match(r'^([A-Z][a-z]+)(.*)', operation_id)
    
    if match:
        # verb = match.group(1)  # We'll use this later for verb determination
        resource_name = match.group(2)  # The rest is the resource name
    else:
        # Fallback: if no match (shouldn't happen with valid AWS operations), use the whole thing
        resource_name = operation_id
    
    # Handle empty resource name (e.g., just "Get" with nothing after)
    if not resource_name:
        resource_name = operation_id.lower()
    
    # Convert from PascalCase to snake_case
    # Insert underscore before uppercase letters
    resource_name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', resource_name)
    resource_name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', resource_name)
    resource_name = resource_name.lower()
    
    # Ensure resource name is plural (StackQL convention)
    resource_name = _pluralize_resource(resource_name)
    
    return resource_name

def _pluralize_resource(resource_name: str) -> str:
    """
    Convert resource name to plural form following StackQL conventions.
    Uses inflect library for proper English pluralization.
    """
    if not resource_name:
        return resource_name
    
    # Special cases that should not be pluralized (uncountable nouns)
    unchanging = {
        'data', 'metadata', 'information', 'software', 'hardware',
        'feedback', 'equipment', 'traffic', 'analytics', 'metrics',
        'statistics', 'access', 'progress', 'status', 'news', 'series'
    }
    
    # Check if the resource name itself or its last component (after underscore) should not be pluralized
    if resource_name in unchanging:
        return resource_name
    
    # For compound names (with underscores), only pluralize the last word
    if '_' in resource_name:
        parts = resource_name.split('_')
        last_word = parts[-1]
        
        # Don't pluralize if last word is unchanging
        if last_word in unchanging:
            return resource_name
        
        # Check if already plural using singular_noun
        # If singular_noun returns a value, the word is plural
        if _inflect_engine.singular_noun(last_word):
            # Already plural, keep as is
            return resource_name
        
        # Not plural yet, pluralize it
        parts[-1] = _inflect_engine.plural_noun(last_word)
        return '_'.join(parts)
    
    # Single word - check if already plural
    if _inflect_engine.singular_noun(resource_name):
        # Already plural
        return resource_name
    
    # Not plural yet, pluralize it
    return _inflect_engine.plural_noun(resource_name)

def determine_stackql_verb(http_method: str, operation_id: str) -> str:
    """
    Determine the appropriate StackQL verb based on HTTP method and operation semantics.
    
    StackQL verbs:
    - select: Read operations (GET, or POST operations that retrieve data like Describe, List, Get)
    - insert: Create operations
    - update: Update/modify operations
    - delete: Delete operations
    - exec: Other operations that don't fit the CRUD pattern
    
    GUARDRAIL: HTTP DELETE method MUST ALWAYS map to 'delete' verb, regardless of operation name.
    
    Note: POST operations that retrieve data (Describe*, List*, Get*) are treated as 'select'
    """
    http_method = http_method.upper()
    
    # CRITICAL GUARDRAIL: HTTP DELETE must ALWAYS be 'delete'
    # This ensures we never have select/insert/update operations using DELETE
    if http_method == 'DELETE':
        return 'delete'
    
    # Patterns for select operations (data retrieval)
    select_patterns = ['Describe', 'Get', 'List', 'Query', 'Search', 'Lookup', 'Find', 'Retrieve', 'Read', 'Show', 'Scan']
    
    # Patterns for insert operations
    insert_patterns = ['Create', 'Put', 'Add', 'Register', 'Enable', 'Batch']
    
    # Patterns for update operations
    update_patterns = ['Update', 'Modify', 'Set', 'Change', 'Replace', 'Edit', 'Apply', 'Attach', 'Detach']
    
    # Patterns for delete operations
    delete_patterns = ['Delete', 'Remove', 'Terminate', 'Deregister', 'Disable', 'Cancel']
    
    # Check operation ID patterns first (more specific than HTTP method)
    for pattern in select_patterns:
        if operation_id.startswith(pattern):
            return 'select'
    
    for pattern in insert_patterns:
        if operation_id.startswith(pattern):
            return 'insert'
    
    for pattern in update_patterns:
        if operation_id.startswith(pattern):
            return 'update'
    
    for pattern in delete_patterns:
        if operation_id.startswith(pattern):
            return 'delete'
    
    # Fall back to HTTP method mapping
    if http_method == 'GET':
        return 'select'
    elif http_method == 'POST':
        # POST without a clear pattern defaults to exec
        return 'exec'
    elif http_method == 'PUT':
        return 'update'
    elif http_method == 'PATCH':
        return 'update'
    else:
        return 'exec'

def init_openapi_spec(service_name, service_dir, protocol, version=None, filename=None):
    info = {
        "contact": {
            "name": "StackQL Studios",
            "url": "https://stackql.io/",
            "email": "info@stackql.io"
        },
        "x-stackql-serviceName": service_dir.replace("-", "_"),
        "x-aws-serviceName": service_name,
        "x-aws-protocol": protocol,
        "x-dateGenerated": f"{date.today().isoformat()}"
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
            "schemas": {}
        }
    }

def add_info(openapi_spec, service_shape, version=None):
    # Use version from service_shape, or fall back to passed version parameter
    if "version" in service_shape:
        openapi_spec["info"]["version"] = service_shape["version"]
    elif version:
        openapi_spec["info"]["version"] = version
    openapi_spec["info"]["title"] = service_shape["traits"]["smithy.api#title"]
    openapi_spec["info"]["description"] = LiteralStr(html_to_md(service_shape["traits"]["smithy.api#documentation"]))

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
    path = http.get("uri", None)
    verb = http.get("method", None)
    if verb:
        verb = verb.lower()

    if path is None or verb is None:
        return

    success_code = http.get("code", 200)

    if path not in openapi_spec["paths"]:
        openapi_spec["paths"][path] = {}
    if verb not in openapi_spec["paths"][path]:
        openapi_spec["paths"][path][verb] = {}
    openapi_spec["paths"][path][verb]["operationId"] = operation_id
    if "smithy.api#documentation" in traits:
        description = LiteralStr(html_to_md(shape["traits"]["smithy.api#documentation"]))
        openapi_spec["paths"][path][verb]["description"] = description
    
    # Add StackQL-specific fields
    resource_name = derive_resource_name(operation_id)
    stackql_verb = determine_stackql_verb(verb, operation_id)
    
    openapi_spec["paths"][path][verb]["x-stackql-resource"] = resource_name
    openapi_spec["paths"][path][verb]["x-stackql-verb"] = stackql_verb
    
    # Add operation-level pagination metadata if this operation differs from dominant scheme
    add_pagination_to_operation(openapi_spec, shape_name, openapi_spec["paths"][path][verb])
    
    input_shape_name = shape.get("input", {}).get("target")
    if input_shape_name and input_shape_name != "smithy.api#Unit":
        input_shape = shapes[input_shape_name]
        members = input_shape.get("members", {})
        parameters = []
        body_fields = {}

        for member_name, member_def in members.items():
            traits = member_def.get("traits", {})
            target = member_def["target"]
            ref_name = target.split("#")[-1]

            if "smithy.api#httpLabel" in traits:
                parameters.append({
                    "name": member_name,
                    "in": "path",
                    "required": "smithy.api#required" in traits,
                    "schema": { "$ref": f"#/components/schemas/{ref_name}" }
                })
            elif "smithy.api#httpQuery" in traits:
                param_name = traits["smithy.api#httpQuery"]
                parameters.append({
                    "name": param_name,
                    "in": "query",
                    "required": "smithy.api#required" in traits,
                    "schema": { "$ref": f"#/components/schemas/{ref_name}" }
                })
            elif "smithy.api#httpHeader" in traits:
                param_name = traits["smithy.api#httpHeader"]
                parameters.append({
                    "name": param_name,
                    "in": "header",
                    "required": "smithy.api#required" in traits,
                    "schema": { "$ref": f"#/components/schemas/{ref_name}" }
                })
            else:
                # default: treat as part of the body
                body_fields[member_name] = { "$ref": f"#/components/schemas/{ref_name}" }

        openapi_spec["paths"][path][verb]["parameters"] = parameters

        if body_fields:
            openapi_spec["paths"][path][verb]["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": body_fields
                        }
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
    Add pagination metadata to the OpenAPI spec's info section.
    Uses the dominant scheme for service-level metadata.
    
    Args:
        openapi_spec: The OpenAPI specification dictionary
        pagination_data: Dictionary with dominant_scheme and exceptions from detect_pagination_scheme
    """
    if not pagination_data:
        return
    
    dominant_scheme = pagination_data['dominant_scheme']
    
    openapi_spec["info"]["x-pagination-request-key"] = dominant_scheme['request_key']
    openapi_spec["info"]["x-pagination-request-location"] = dominant_scheme['request_location']
    openapi_spec["info"]["x-pagination-response-key"] = dominant_scheme['response_key']
    openapi_spec["info"]["x-pagination-response-location"] = dominant_scheme['response_location']
    
    # Store exceptions for later use when adding operations
    openapi_spec["_pagination_exceptions"] = pagination_data['exceptions']

def add_pagination_to_operation(openapi_spec, shape_name, operation_spec):
    """
    Add operation-level pagination metadata if this operation differs from the dominant scheme.
    
    Args:
        openapi_spec: The OpenAPI specification dictionary
        shape_name: The full shape name (e.g., 'com.amazonaws.service#OperationName')
        operation_spec: The operation specification dictionary to potentially add pagination to
    """
    pagination_exceptions = openapi_spec.get("_pagination_exceptions", {})
    
    if shape_name in pagination_exceptions:
        exception_scheme = pagination_exceptions[shape_name]
        operation_spec["x-pagination-request-key"] = exception_scheme['request_key']
        operation_spec["x-pagination-request-location"] = exception_scheme['request_location']
        operation_spec["x-pagination-response-key"] = exception_scheme['response_key']
        operation_spec["x-pagination-response-location"] = exception_scheme['response_location']

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
        print(f"  ⚠️  Found {len(orphaned_schemas)} orphaned schema(s): {', '.join(sorted(orphaned_schemas))}")
        
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

def write_output_yaml(openapi_spec, service_dir):
    # Clean up temporary pagination exceptions storage
    if "_pagination_exceptions" in openapi_spec:
        del openapi_spec["_pagination_exceptions"]
    
    outdir = Path("smithy-to-openapi/openapi")
    outdir.mkdir(exist_ok=True)
    outfile = outdir / f"{service_dir.replace('-', '_')}.yaml"
    with open(outfile, "w", encoding="utf-8") as f:
        yaml.dump(openapi_spec, f, sort_keys=False, allow_unicode=True)
