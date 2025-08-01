# processors/rest_json1.py

import json, yaml
from pathlib import Path
from processors.shared_functions import (
    LiteralStr,
    literal_str_representer,
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

    for shape_name, shape in shapes.items():
        if shape.get("type") == "service": 
            add_info(openapi_spec, shape)
            add_servers(openapi_spec, file_name, shape)
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


    # Write output YAML
    outdir = Path("testdir")
    outdir.mkdir(exist_ok=True)
    outfile = outdir / f"{service_name}.yaml"
    with open(outfile, "w", encoding="utf-8") as f:
        yaml.dump(openapi_spec, f, sort_keys=False, allow_unicode=True)



# def process(model_entry):
#     service_name = model_entry['servicename'].split('#')[0].split('com.amazonaws.')[1]
#     print(f"processing {service_name} with protocol {model_entry['protocol']}")
