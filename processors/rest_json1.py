# processors/rest_json1.py

import json, yaml
from pathlib import Path
from processors.shared_functions import LiteralStr, add_info, literal_str_representer, add_servers, init_openapi_spec, add_component_schema_string, add_component_schema_boolean, add_component_schema_integer

yaml.add_representer(LiteralStr, literal_str_representer)

def process(model_entry):

    services_to_skip = ["cloudfront-keyvaluestore", "codecatalyst"]
    file_name = model_entry['filename']
    if file_name in services_to_skip:
        print(f"skipping {file_name}")
        return

    protocol = model_entry['protocol']
    service_name = model_entry['servicename'].split('#')[0].split('com.amazonaws.')[1]
    print(f"processing {service_name} with protocol {protocol}")

    model_path = Path(model_entry['filepath'])

    with open(model_path, "r") as f:
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

        # elif shape.get("type") == "structure":
        #     add_component(openapi_spec, shape_name, shape, shapes)


    # Write output YAML
    outdir = Path("openapi")
    outdir.mkdir(exist_ok=True)
    outfile = outdir / f"{service_name}.yaml"
    with open(outfile, "w") as f:
        yaml.dump(openapi_spec, f, sort_keys=False, allow_unicode=True)
