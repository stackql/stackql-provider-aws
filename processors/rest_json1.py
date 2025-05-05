# processors/rest_json1.py

import json, yaml
from pathlib import Path
from processors.shared_functions import LiteralStr, add_info, literal_str_representer, add_servers, init_openapi_spec

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

            # does it have resources?
            resources = shape.get("resources", [])
            if resources:
                print(f"resources: {len(resources)}")
            else:
                operations = shape.get("operations", [])
                print(f"operations: {len(operations)}")



        # elif shape.get("type") == "operation":


# traits		  
				
#                 "smithy.api#paginated": {
#                     "inputToken": "nextToken",
#                     "outputToken": "nextToken",
#                     "pageSize": "maxResults"
#                 },


    # Write output YAML
    outdir = Path("openapi")
    outdir.mkdir(exist_ok=True)
    outfile = outdir / f"{service_name}.yaml"
    with open(outfile, "w") as f:
        yaml.dump(openapi_spec, f, sort_keys=False, allow_unicode=True)
