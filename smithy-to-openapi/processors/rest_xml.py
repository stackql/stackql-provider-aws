# processors/rest_xml.py
# REST XML protocol processor
# Similar to restJson1 but with XML request/response bodies

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

    shapes = model_data.get("shapes", model_data)

    # Detect and add pagination metadata before processing operations
    pagination_data = detect_pagination_scheme(shapes, protocol)
    add_pagination_to_info(openapi_spec, pagination_data)

    for shape_name, shape in shapes.items():
        if shape.get("type") == "service":
            add_info(openapi_spec, shape, version)
            add_servers(openapi_spec, service_dir, shape)
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
            add_operation_xml(openapi_spec, shape_name, shape, shapes)

    # Write output YAML (this also finalizes StackQL resources and resolves orphaned schemas)
    write_output_yaml(openapi_spec, service_dir)


def add_operation_xml(openapi_spec, shape_name, shape, shapes):
    """Add an operation for REST XML protocol - uses HTTP traits like restJson1 but with XML content type"""
    operation_id = shape_name.split("#")[-1]
    print(f"adding operation {operation_id}")

    # Process traits
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

    # Track operation for StackQL resource building
    # Note: Resource name, method name, and SQL verb will be resolved from CSV manifest
    # in build_stackql_resources() using get_operation_config()
    openapi_spec["_stackql_operations"].append({
        "operation_id": operation_id,
        "path": path,
        "http_method": verb,
        "success_code": str(success_code),
        "shape_name": shape_name
    })

    if "smithy.api#documentation" in traits:
        description = LiteralStr(html_to_md(shape["traits"]["smithy.api#documentation"]))
        openapi_spec["paths"][path][verb]["description"] = description

    # Process input shape
    input_shape_name = shape.get("input", {}).get("target")
    if input_shape_name and input_shape_name != "smithy.api#Unit":
        input_shape = shapes.get(input_shape_name, {})
        members = input_shape.get("members", {})
        parameters = []
        body_fields = {}

        for member_name, member_def in members.items():
            member_traits = member_def.get("traits", {})
            target = member_def["target"]
            ref_name = target.split("#")[-1]

            if "smithy.api#httpLabel" in member_traits:
                parameters.append({
                    "name": member_name,
                    "in": "path",
                    "required": True,  # Path parameters are always required
                    "schema": {"$ref": f"#/components/schemas/{ref_name}"}
                })
            elif "smithy.api#httpQuery" in member_traits:
                param_name = member_traits["smithy.api#httpQuery"]
                parameters.append({
                    "name": param_name,
                    "in": "query",
                    "required": "smithy.api#required" in member_traits,
                    "schema": {"$ref": f"#/components/schemas/{ref_name}"}
                })
            elif "smithy.api#httpHeader" in member_traits:
                param_name = member_traits["smithy.api#httpHeader"]
                parameters.append({
                    "name": param_name,
                    "in": "header",
                    "required": "smithy.api#required" in member_traits,
                    "schema": {"$ref": f"#/components/schemas/{ref_name}"}
                })
            elif "smithy.api#httpPrefixHeaders" in member_traits:
                # Prefix headers are handled dynamically, skip for OpenAPI
                pass
            elif "smithy.api#httpPayload" in member_traits:
                # Direct payload binding - the entire body is this member
                body_fields["__payload__"] = {"$ref": f"#/components/schemas/{ref_name}"}
            else:
                # Default: treat as part of the body
                body_fields[member_name] = {"$ref": f"#/components/schemas/{ref_name}"}

        if parameters:
            openapi_spec["paths"][path][verb]["parameters"] = parameters

        if body_fields:
            if "__payload__" in body_fields:
                # Direct payload binding
                openapi_spec["paths"][path][verb]["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/xml": {
                            "schema": body_fields["__payload__"]
                        }
                    }
                }
            else:
                openapi_spec["paths"][path][verb]["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/xml": {
                            "schema": {
                                "type": "object",
                                "properties": body_fields
                            }
                        }
                    }
                }

    # Process output/responses
    openapi_spec["paths"][path][verb]["responses"] = {}
    responses = openapi_spec["paths"][path][verb]["responses"]

    # Success response
    output_target = shape.get("output", {}).get("target")
    if output_target and output_target != "smithy.api#Unit":
        output_ref_name = output_target.split("#")[-1]
        responses[str(success_code)] = {
            "description": "Success",
            "content": {
                "text/xml": {
                    "schema": {"$ref": f"#/components/schemas/{output_ref_name}"}
                }
            }
        }
    else:
        responses[str(success_code)] = {
            "description": "Success"
        }

    # Error responses
    if "errors" in shape:
        for error in shape["errors"]:
            error_component_name = error["target"].split("#")[-1]
            error_shape = shapes.get(error["target"], {})
            error_traits = error_shape.get("traits", {})

            if "smithy.api#httpError" in error_traits:
                error_code = error_traits["smithy.api#httpError"]
            else:
                error_code = 400

            responses[str(error_code)] = {
                "content": {
                    "text/xml": {
                        "schema": {"$ref": f"#/components/schemas/{error_component_name}"}
                    }
                }
            }

            if "smithy.api#documentation" in error_traits:
                responses[str(error_code)]["description"] = LiteralStr(html_to_md(error_traits["smithy.api#documentation"]))
            else:
                responses[str(error_code)]["description"] = error_component_name
