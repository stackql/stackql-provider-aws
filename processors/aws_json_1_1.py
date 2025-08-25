# processors/rest_json1.py

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
    add_operation,
)

yaml.add_representer(LiteralStr, literal_str_representer)

def process(model_entry):

    services_to_skip = []
    file_name = model_entry['filename']
    if file_name in services_to_skip:
        print(f"skipping {file_name}")
        return

    protocol = model_entry['protocol']
    service_name = model_entry['servicename'].split('#')[0].split('com.amazonaws.')[1]
    print(f"processing {service_name} with protocol {protocol}")

    model_path = Path(model_entry['filepath'])

    with open(model_path, "r", encoding="utf-8") as f:
        model_data = json.load(f)

    # Basic OpenAPI structure
    openapi_spec = init_openapi_spec(service_name, file_name, protocol)

    shapes = model_data.get("shapes", model_data)

    shapes_dict = {
        "service": [],
        "operation": []
    }

    for shape_name, shape in shapes.items():
        if shape.get("type") == "service": 
            add_info(openapi_spec, shape)
            add_servers(openapi_spec, file_name, shape)
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
            add_operation(openapi_spec, shape_name, shape, shapes)
            shape["my_name"] = shape_name
            shapes_dict["operation"].append(shape)

    # process the service to get the paths
    service_name2 = model_entry['servicename'].split('#')[1]
    
    # Sort the operations, we will need them to be in alphabetic order for creating paths
    shapes_dict["operation"].sort(key=lambda x: x["my_name"])

    # Setup the "paths" attribute
    openapi_spec["paths"] = {}

    # create the path
    for operation in shapes_dict["operation"]:
        key_string = "/#X-Amz-Target=" + service_name2 + "." + operation["my_name"].split('#')[1]
        openapi_spec["paths"][key_string] = create_path(operation, service_name2)

    # Write output YAML
    outdir = Path("testdir")
    outdir.mkdir(exist_ok=True)
    outfile = outdir / f"{service_name}.yaml"
    with open(outfile, "w", encoding="utf-8") as f:
        yaml.dump(openapi_spec, f, sort_keys=False, allow_unicode=True)

def create_path(operation, service_name2):
    result = {}
    result["post"] = {}
    result_post = result["post"]
    
    result_post["operationId"] = operation["my_name"].split('#')[1]
    result_post["description"] = LiteralStr(html_to_md(operation["traits"].get("smithy.api#documentation", "")))
    
    result_post["requestBody"] = {}
    result_request_body = result_post["requestBody"]
    result_request_body["required"] = True
    result_request_body["content"] = {}
    result_request_body["content"]["application/json"] = {}
    result_request_body["content"]["application/json"]["schema"] = {}    
    result_request_body["content"]["application/json"]["schema"]["$ref"] = "#/components/schemas/" + operation["input"]["target"].split("#")[1]

    result_post["parameters"] = {}
    result_parameters_inside = result_post["parameters"]
    result_parameters_inside["name"] = "X-Amz-Target"
    result_parameters_inside["in"] = "header"
    result_parameters_inside["required"] = True
    result_parameters_inside["schema"] = {}
    result_parameters_inside["schema"]["type"] = "string"
    result_parameters_inside["schema"]["enum"] = [service_name2 + "." + operation["my_name"].split('#')[1]]

    # Static Information
    result["parameters"] = []
    result["parameters"].append({ '$ref': '#/components/parameters/X-Amz-Content-Sha256'})
    result["parameters"].append({ '$ref': '#/components/parameters/X-Amz-Date'})
    result["parameters"].append({ '$ref': '#/components/parameters/X-Amz-Algorithm'})
    result["parameters"].append({ '$ref': '#/components/parameters/X-Amz-Credential'})
    result["parameters"].append({ '$ref': '#/components/parameters/X-Amz-Security-Token'})
    result["parameters"].append({ '$ref': '#/components/parameters/X-Amz-Signature'})
    result["parameters"].append({ '$ref': '#/components/parameters/X-Amz-SignedHeaders'})

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

    return result
