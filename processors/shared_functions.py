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
    