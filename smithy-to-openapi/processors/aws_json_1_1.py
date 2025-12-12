# processors/aws_json_1_1.py
# AWS JSON 1.1 protocol processor
# Uses X-Amz-Target header with POST requests

import json, yaml
from pathlib import Path
import sys
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
    detect_pagination_scheme,
    add_pagination_to_info,
    write_output_yaml,
    derive_resource_name,
    determine_stackql_verb,
    derive_method_name,
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

    # process the service to get the paths
    service_name2 = model_entry['servicename'].split('#')[1]

    # Sort the operations, we will need them to be in alphabetic order for creating paths
    shapes_dict["operation"].sort(key=lambda x: x["my_name"])

    # Setup the "paths" attribute
    openapi_spec["paths"] = {}

    # Detect and add pagination metadata before creating paths
    pagination_data = detect_pagination_scheme(shapes, protocol)
    add_pagination_to_info(openapi_spec, pagination_data)

    # create the path
    for operation in shapes_dict["operation"]:
        operation_id = operation["my_name"].split('#')[1]
        key_string = "/#X-Amz-Target=" + service_name2 + "." + operation_id
        path_spec = create_path(operation, service_name2, openapi_spec)
        openapi_spec["paths"][key_string] = path_spec

    # Write output YAML
    write_output_yaml(openapi_spec, service_dir)

def create_path(operation, service_name2, openapi_spec):
    result = {}
    operation_id = operation["my_name"].split('#')[1]
    path_key = "/#X-Amz-Target=" + service_name2 + "." + operation_id

    result["post"] = {}
    result_post = result["post"]

    result_post["operationId"] = operation_id
    result_post["description"] = LiteralStr(html_to_md(operation["traits"].get("smithy.api#documentation", "")))

    result_post["requestBody"] = {}
    result_request_body = result_post["requestBody"]
    result_request_body["required"] = True
    result_request_body["content"] = {}
    result_request_body["content"]["application/json"] = {}
    result_request_body["content"]["application/json"]["schema"] = {}
    result_request_body["content"]["application/json"]["schema"]["$ref"] = "#/components/schemas/" + operation["input"]["target"].split("#")[1]

    result_post["parameters"] = [{
        "name": "X-Amz-Target",
        "in": "header",
        "required": True,
        "schema": {
            "type": "string",
            "enum": [service_name2 + "." + operation_id]
        }
    }]

    # Static Information
    result["parameters"] = []
    result["parameters"].append({'$ref': '#/components/parameters/X-Amz-Content-Sha256'})
    result["parameters"].append({'$ref': '#/components/parameters/X-Amz-Date'})
    result["parameters"].append({'$ref': '#/components/parameters/X-Amz-Algorithm'})
    result["parameters"].append({'$ref': '#/components/parameters/X-Amz-Credential'})
    result["parameters"].append({'$ref': '#/components/parameters/X-Amz-Security-Token'})
    result["parameters"].append({'$ref': '#/components/parameters/X-Amz-Signature'})
    result["parameters"].append({'$ref': '#/components/parameters/X-Amz-SignedHeaders'})

    result_post["responses"] = {}
    result_responses = result_post["responses"]
    # 200 response
    result_responses["200"] = {}
    result_responses["200"]["description"] = "Success"
    result_responses["200"]["content"] = {}
    result_responses["200"]["content"]["application/json"] = {}
    result_responses["200"]["content"]["application/json"]["schema"] = {"$ref": ('#/components/schemas/' + operation["output"]["target"].split('#')[1])}

    error_code = 480

    if operation.get("errors", False) is not False:
        for error in operation["errors"]:
            error_string = str(error_code)
            error_name = error["target"].split('#')[1]

            result_responses[error_string] = {}
            result_responses[error_string]["description"] = error_name
            result_responses[error_string]["content"] = {}
            result_responses[error_string]["content"]["application/json"] = {}
            result_responses[error_string]["content"]["application/json"]["schema"] = {"$ref": ('#/components/schemas/' + error_name)}

            error_code += 1

    # Track operation for StackQL resource building
    resource_name = derive_resource_name(operation_id)
    stackql_verb = determine_stackql_verb("POST", operation_id)
    method_name = derive_method_name(operation_id)

    openapi_spec["_stackql_operations"].append({
        "operation_id": operation_id,
        "resource_name": resource_name,
        "stackql_verb": stackql_verb,
        "method_name": method_name,
        "path": path_key,
        "http_method": "post",
        "success_code": "200",
        "shape_name": operation["my_name"]
    })

    return result
