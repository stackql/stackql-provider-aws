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

