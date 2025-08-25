# processors/shared_functions.py

import sys,html2text
from yaml.representer import SafeRepresenter
from datetime import date

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

def init_openapi_spec(service_name, file_name, protocol):
    return {
        "openapi": "3.1.0",
        "info": {
            "contact": {
                "name": "StackQL Studios",
                "url": "https://stackql.io/",
                "email": "info@stackql.io"
            },
            "x-stackql-serviceName": file_name.replace(".json", "").replace("-", "_"),
            "x-aws-serviceName": service_name,
            "x-aws-protocol": protocol,
            "x-dateGenerated": f"{date.today().isoformat()}"
        },
        "servers": [],
        "paths": {},
        "components": {
            "schemas": {}
        }
    }

def add_info(openapi_spec, service_shape):
    if "version" in service_shape:
        openapi_spec["info"]["version"] = service_shape["version"]
    openapi_spec["info"]["title"] = service_shape["traits"]["smithy.api#title"]
    openapi_spec["info"]["description"] = LiteralStr(html_to_md(service_shape["traits"]["smithy.api#documentation"]))

def add_servers(openapi_spec, versionless_service_name, service_shape):

    endpoint_prefix = versionless_service_name

    if "aws.api#service" in service_shape["traits"]:
        if "endpointPrefix" in service_shape["traits"]["aws.api#service"]:
            endpoint_prefix = service_shape["traits"]["aws.api#service"]["endpointPrefix"]

    if endpoint_prefix == versionless_service_name:
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
            "allOf": [
                { "$ref": f"#/components/schemas/{ref_name}" }
            ]
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

        # Inline documentation
        if "smithy.api#documentation" in member_traits:
            member_schema = {
                "allOf": [member_schema],
                "description": html_to_md(member_traits["smithy.api#documentation"])
            }

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
    openapi_spec["paths"][path][verb]["responses"][str(success_code)] = {}
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
