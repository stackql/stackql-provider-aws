# processors/aws_json_1_0.py
# AWS JSON 1.0 protocol processor
# Very similar to awsJson1_1 - uses X-Amz-Target header with POST requests

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
        "service": [],
        "operation": []
    }

    for shape_name, shape in shapes.items():
        if shape.get("type") == "service":
            add_info(openapi_spec, shape, version)
            add_servers(openapi_spec, service_dir, shape)
            shape["my_name"] = shape_name
            shapes_dict["service"].append(shape)
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

    # Get the service name for X-Amz-Target
    service_name2 = model_entry['servicename'].split('#')[1]

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
        key_string = "/#X-Amz-Target=" + service_name2 + "." + operation_name
        path_spec = create_path(operation, service_name2, openapi_spec)
        openapi_spec["paths"][key_string] = path_spec

    # Write output YAML
    write_output_yaml(openapi_spec, service_dir)

def create_path(operation, service_name2, openapi_spec):
    result = {}
    operation_name = operation["my_name"].split('#')[1]
    path_key = "/#X-Amz-Target=" + service_name2 + "." + operation_name

    result["post"] = {}
    result_post = result["post"]

    result_post["operationId"] = operation_name
    result_post["description"] = LiteralStr(html_to_md(operation["traits"].get("smithy.api#documentation", "")))

    # Request body with JSON content
    result_post["requestBody"] = {}
    result_request_body = result_post["requestBody"]
    result_request_body["required"] = True
    result_request_body["content"] = {}
    result_request_body["content"]["application/x-amz-json-1.0"] = {}
    result_request_body["content"]["application/x-amz-json-1.0"]["schema"] = {}

    if "input" in operation and operation["input"]["target"] != "smithy.api#Unit":
        result_request_body["content"]["application/x-amz-json-1.0"]["schema"]["$ref"] = "#/components/schemas/" + operation["input"]["target"].split("#")[1]
    else:
        result_request_body["content"]["application/x-amz-json-1.0"]["schema"]["type"] = "object"

    # X-Amz-Target header parameter
    result_post["parameters"] = [
        {
            "name": "X-Amz-Target",
            "in": "header",
            "required": True,
            "schema": {
                "type": "string",
                "enum": [service_name2 + "." + operation_name]
            }
        }
    ]

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

    # Responses
    result_post["responses"] = {}
    result_responses = result_post["responses"]

    # 200 success response
    result_responses["200"] = {
        "description": "Success",
        "content": {
            "application/json": {
                "schema": {}
            }
        }
    }

    if "output" in operation and operation["output"]["target"] != "smithy.api#Unit":
        result_responses["200"]["content"]["application/json"]["schema"]["$ref"] = "#/components/schemas/" + operation["output"]["target"].split('#')[1]
    else:
        result_responses["200"]["content"]["application/json"]["schema"]["type"] = "object"

    # Error responses
    error_code = 480
    if operation.get("errors"):
        for error in operation["errors"]:
            error_string = str(error_code)
            error_name = error["target"].split('#')[1]

            result_responses[error_string] = {
                "description": error_name,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{error_name}"}
                    }
                }
            }
            error_code += 1

    # Track operation for StackQL resource building
    # Note: Resource name, method name, and SQL verb will be resolved from CSV manifest
    # in build_stackql_resources() using get_operation_config()
    openapi_spec["_stackql_operations"].append({
        "operation_id": operation_name,
        "path": path_key,
        "http_method": "post",
        "success_code": "200",
        "shape_name": operation["my_name"]
    })

    return result
