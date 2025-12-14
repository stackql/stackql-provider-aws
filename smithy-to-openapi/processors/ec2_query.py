# processors/ec2_query.py
# EC2 Query protocol processor
# Similar to AWS Query but specific to EC2
# Uses Action and Version query parameters
# Response content type is XML

import json, yaml
from pathlib import Path
from processors.shared_functions import (
    LiteralStr,
    literal_str_representer,
    html_to_md,
    init_openapi_spec,
    add_info,
    add_servers,
    add_component_schema_string,
    add_component_schema_boolean,
    add_component_schema_integer,
    add_component_schema_timestamp,
    add_component_schema_double,
    add_component_schema_float,
    add_component_schema_long,
    add_component_schema_blob,
    add_component_schema_enum,
    add_component_schema_map,
    add_component_schema_document,
    add_component_schema_list,
    add_component_schema_union,
    add_component_schema_structure,
    write_output_yaml,
    detect_pagination_scheme,
    add_pagination_to_info,
)

yaml.add_representer(LiteralStr, literal_str_representer)

def process(model_entry):

    services_to_skip = []
    service_dir = model_entry['servicedir']
    if service_dir in services_to_skip:
        print(f"skipping {service_dir}")
        return

    protocol = model_entry['protocol']
    service_name = model_entry['servicename'].split('#')[0].split('com.amazonaws.')[1]
    version = model_entry['version']
    filename = model_entry['filename']
    print(f"processing {service_name} with protocol {protocol}")

    model_path = Path(model_entry['filepath'])

    with open(model_path, "r", encoding="utf-8") as f:
        model_data = json.load(f)

    # Basic OpenAPI structure
    openapi_spec = init_openapi_spec(service_name, service_dir, protocol, version, filename)

    # Add common AWS signature parameters
    openapi_spec["components"]["parameters"] = {
        "X-Amz-Content-Sha256": {
            "name": "X-Amz-Content-Sha256",
            "in": "header",
            "required": False,
            "schema": {"type": "string"}
        },
        "X-Amz-Date": {
            "name": "X-Amz-Date",
            "in": "header",
            "required": False,
            "schema": {"type": "string"}
        },
        "X-Amz-Algorithm": {
            "name": "X-Amz-Algorithm",
            "in": "header",
            "required": False,
            "schema": {"type": "string"}
        },
        "X-Amz-Credential": {
            "name": "X-Amz-Credential",
            "in": "header",
            "required": False,
            "schema": {"type": "string"}
        },
        "X-Amz-Security-Token": {
            "name": "X-Amz-Security-Token",
            "in": "header",
            "required": False,
            "schema": {"type": "string"}
        },
        "X-Amz-Signature": {
            "name": "X-Amz-Signature",
            "in": "header",
            "required": False,
            "schema": {"type": "string"}
        },
        "X-Amz-SignedHeaders": {
            "name": "X-Amz-SignedHeaders",
            "in": "header",
            "required": False,
            "schema": {"type": "string"}
        }
    }

    shapes = model_data.get("shapes", model_data)

    shapes_dict = {
        "service": None,
        "operation": []
    }

    # Get API version from service shape
    api_version = None

    for shape_name, shape in shapes.items():
        if shape.get("type") == "service":
            add_info(openapi_spec, shape, version)
            add_servers(openapi_spec, service_dir, shape)
            shapes_dict["service"] = shape
            api_version = shape.get("version", "")
        elif shape.get("type") == "string":
            add_component_schema_string(openapi_spec, shape_name, shape)
        elif shape.get("type") == "boolean":
            add_component_schema_boolean(openapi_spec, shape_name, shape)
        elif shape.get("type") == "integer":
            add_component_schema_integer(openapi_spec, shape_name, shape)
        elif shape.get("type") == "timestamp":
            add_component_schema_timestamp(openapi_spec, shape_name, shape)
        elif shape.get("type") == "double":
            add_component_schema_double(openapi_spec, shape_name, shape)
        elif shape.get("type") == "float":
            add_component_schema_float(openapi_spec, shape_name, shape)
        elif shape.get("type") == "long":
            add_component_schema_long(openapi_spec, shape_name, shape)
        elif shape.get("type") == "blob":
            add_component_schema_blob(openapi_spec, shape_name, shape)
        elif shape.get("type") == "enum":
            add_component_schema_enum(openapi_spec, shape_name, shape)
        elif shape.get("type") == "map":
            add_component_schema_map(openapi_spec, shape_name, shape)
        elif shape.get("type") == "document":
            add_component_schema_document(openapi_spec, shape_name, shape)
        elif shape.get("type") == "list":
            add_component_schema_list(openapi_spec, shape_name, shape)
        elif shape.get("type") == "union":
            add_component_schema_union(openapi_spec, shape_name, shape)
        elif shape.get("type") == "structure":
            add_component_schema_structure(openapi_spec, shape_name, shape)
        elif shape.get("type") == "operation":
            shape["my_name"] = shape_name
            shapes_dict["operation"].append(shape)

    # Sort operations alphabetically
    shapes_dict["operation"].sort(key=lambda x: x["my_name"])

    # Setup paths
    openapi_spec["paths"] = {}

    # Detect and add pagination metadata before creating paths
    pagination_data = detect_pagination_scheme(shapes, protocol)
    add_pagination_to_info(openapi_spec, pagination_data)

    # Create path for each operation
    for operation in shapes_dict["operation"]:
        operation_name = operation["my_name"].split('#')[1]
        key_string = f"/#Action={operation_name}"
        path_spec = create_path(operation, api_version, shapes, openapi_spec)
        openapi_spec["paths"][key_string] = path_spec

    # Write output YAML
    write_output_yaml(openapi_spec, service_dir)


def create_path(operation, api_version, shapes, openapi_spec):
    result = {}
    operation_name = operation["my_name"].split('#')[1]
    path_key = f"/#Action={operation_name}"

    # GET method - parameters in query string
    result["get"] = create_get_operation(operation, operation_name, api_version, shapes, openapi_spec, path_key)

    # AWS signature parameters at path level
    result["parameters"] = [
        {'$ref': '#/components/parameters/X-Amz-Content-Sha256'},
        {'$ref': '#/components/parameters/X-Amz-Date'},
        {'$ref': '#/components/parameters/X-Amz-Algorithm'},
        {'$ref': '#/components/parameters/X-Amz-Credential'},
        {'$ref': '#/components/parameters/X-Amz-Security-Token'},
        {'$ref': '#/components/parameters/X-Amz-Signature'},
        {'$ref': '#/components/parameters/X-Amz-SignedHeaders'}
    ]

    # POST method - parameters in body
    result["post"] = create_post_operation(operation, operation_name, api_version, shapes)

    return result


def create_get_operation(operation, operation_name, api_version, shapes, openapi_spec, path_key):
    op = {}

    op["operationId"] = f"GET_{operation_name}"
    op["description"] = LiteralStr(html_to_md(operation["traits"].get("smithy.api#documentation", "")))

    # Response first (following the example order)
    op["responses"] = create_responses(operation, shapes)

    # Build parameters list
    parameters = []

    # Add input parameters from the input shape
    input_target = operation.get("input", {}).get("target")
    if input_target and input_target != "smithy.api#Unit":
        input_shape = shapes.get(input_target, {})
        members = input_shape.get("members", {})

        for member_name, member_def in members.items():
            member_traits = member_def.get("traits", {})
            target = member_def["target"]
            ref_name = target.split("#")[-1]

            # Check for xmlName trait for parameter name (EC2 uses this)
            param_name = member_traits.get("smithy.api#xmlName", member_name)

            # Get the target shape to check if it's a list
            target_shape = shapes.get(target, {})
            target_type = target_shape.get("type", "")

            param = {
                "name": param_name,
                "in": "query",
                "required": "smithy.api#required" in member_traits,
            }

            # Handle list types specially for EC2 query format
            if target_type == "list":
                list_item_target = target_shape.get("member", {}).get("target", "")
                list_item_ref = list_item_target.split("#")[-1] if list_item_target else "string"
                param["schema"] = {
                    "type": "array",
                    "items": {
                        "allOf": [
                            {"$ref": f"#/components/schemas/{list_item_ref}"},
                            {"xml": {"name": "item"}}
                        ]
                    }
                }
            else:
                param["schema"] = {"$ref": f"#/components/schemas/{ref_name}"}

            if "smithy.api#documentation" in member_traits:
                param["description"] = html_to_md(member_traits["smithy.api#documentation"])

            parameters.append(param)

    # Action parameter
    parameters.append({
        "name": "Action",
        "in": "query",
        "required": True,
        "schema": {
            "type": "string",
            "enum": [operation_name]
        }
    })

    # Version parameter
    parameters.append({
        "name": "Version",
        "in": "query",
        "required": True,
        "schema": {
            "type": "string",
            "enum": [api_version]
        }
    })

    op["parameters"] = parameters

    # Track operation for StackQL resource building (GET version)
    # Note: Resource name, method name, and SQL verb will be resolved from CSV manifest
    # in build_stackql_resources() using get_operation_config()
    openapi_spec["_stackql_operations"].append({
        "operation_id": operation_name,
        "path": path_key,
        "http_method": "get",
        "success_code": "200",
        "shape_name": operation["my_name"]
    })

    return op


def create_post_operation(operation, operation_name, api_version, shapes):
    op = {}

    op["operationId"] = f"POST_{operation_name}"
    op["description"] = LiteralStr(html_to_md(operation["traits"].get("smithy.api#documentation", "")))

    # Response first
    op["responses"] = create_responses(operation, shapes)

    # Request body with XML schema reference
    if "input" in operation and operation["input"]["target"] != "smithy.api#Unit":
        input_ref = operation["input"]["target"].split("#")[1]
        op["requestBody"] = {
            "content": {
                "text/xml": {
                    "schema": {"$ref": f"#/components/schemas/{input_ref}"}
                }
            }
        }

    # Parameters (Action and Version in query string for POST)
    op["parameters"] = [
        {
            "name": "Action",
            "in": "query",
            "required": True,
            "schema": {
                "type": "string",
                "enum": [operation_name]
            }
        },
        {
            "name": "Version",
            "in": "query",
            "required": True,
            "schema": {
                "type": "string",
                "enum": [api_version]
            }
        }
    ]

    return op


def create_responses(operation, shapes):
    responses = {}

    # 200 success response
    output_target = operation.get("output", {}).get("target")
    if output_target and output_target != "smithy.api#Unit":
        output_ref_name = output_target.split("#")[-1]
        responses["200"] = {
            "description": "Success",
            "content": {
                "text/xml": {
                    "schema": {"$ref": f"#/components/schemas/{output_ref_name}"}
                }
            }
        }
    else:
        responses["200"] = {
            "description": "Success"
        }

    # EC2 errors are typically not enumerated in the same way
    # but we can still add them if present
    error_code = 480
    if operation.get("errors"):
        for error in operation["errors"]:
            error_name = error["target"].split('#')[1]
            error_shape = shapes.get(error["target"], {})
            error_traits = error_shape.get("traits", {}) if error_shape else {}

            responses[str(error_code)] = {
                "description": error_name,
                "content": {
                    "text/xml": {
                        "schema": {"$ref": f"#/components/schemas/{error_name}"}
                    }
                }
            }
            error_code += 1

    return responses
