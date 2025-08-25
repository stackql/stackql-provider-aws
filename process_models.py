import json
from pathlib import Path
from processors import (
    rest_json1, rest_xml, aws_json_1_0, aws_json_1_1, aws_query, ec2_query
)

PROTOCOL_DISPATCH = {
    "aws.protocols#restJson1": rest_json1.process,
    "aws.protocols#restXml": rest_xml.process,
    "aws.protocols#awsJson1_0": aws_json_1_0.process,
    "aws.protocols#awsJson1_1": aws_json_1_1.process,
    "aws.protocols#awsQuery": aws_query.process,
    "aws.protocols#ec2Query": ec2_query.process,
}

def extract_services(input_dir: Path):
    for model_file in input_dir.glob("*.json"):
        try:
            with open(model_file, "r", encoding="utf-8") as f:
                model_data = json.load(f)

            shapes = model_data.get("shapes", model_data)
            for shape_name, shape in shapes.items():
                if shape.get("type") == "service":
                    traits = shape.get("traits", {})
                    protocol = "unknown"
                    for key in traits:
                        if key.startswith("aws.protocols#"):
                            protocol = key
                            break

                    yield {
                        "filename": model_file.name,
                        "filepath": str(model_file.resolve()),
                        "servicename": shape_name,
                        "protocol": protocol
                    }

        except Exception as e:
            print(f"❌ Error processing {model_file.name}: {e}")


if __name__ == "__main__":

    for svc in extract_services(Path("models")):
        protocol = svc["protocol"]
        if protocol in PROTOCOL_DISPATCH:
            PROTOCOL_DISPATCH[protocol](svc)
        else:
            print(f"❓ Skipping {svc['servicename']} — unknown protocol: {protocol}")
