import json
import sys
import shutil
import argparse
from pathlib import Path
from processors import (
    rest_json1, rest_xml, aws_json_1_0, aws_json_1_1, aws_query, ec2_query
)
from processors.shared_functions import (
    reset_processed_services,
    generate_provider_yaml,
    PROVIDER_VERSION
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
    # Iterate through service directories
    for service_dir in sorted(input_dir.iterdir()):
        if not service_dir.is_dir():
            continue
            
        service_name = service_dir.name
        print(f"processing service {service_name}...")
        
        # Check for service subdirectory
        service_subdir = service_dir / "service"
        if not service_subdir.exists() or not service_subdir.is_dir():
            continue
        
        # Get version directories
        version_dirs = [d for d in service_subdir.iterdir() if d.is_dir()]
        
        # Error if more than one version
        if len(version_dirs) > 1:
            print(f"❌ ERROR: Service '{service_name}' has {len(version_dirs)} versions, only 1 is allowed")
            print(f"   Versions found: {', '.join([d.name for d in version_dirs])}")
            sys.exit(1)
        
        if len(version_dirs) == 0:
            continue
            
        version_dir = version_dirs[0]
        version_name = version_dir.name
        print(f"  processing version {version_name}...")
        
        # Process JSON files in the version directory
        for model_file in version_dir.glob("*.json"):
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
                            "servicedir": service_name,
                            "version": version_name,
                            "protocol": protocol
                        }

            except Exception as e:
                print(f"❌ Error processing {model_file.name}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process AWS service models and generate OpenAPI specs")
    parser.add_argument("--clean", action="store_true", help="Clean the output directory before processing")
    args = parser.parse_args()

    if not Path("models").exists():
        print("❌ ERROR: 'models' directory not found. Please run this script from the project root.")
        sys.exit(1)

    # Clean output directory if requested
    if args.clean:
        output_dir = Path(f"smithy-to-openapi/openapi/src/aws/{PROVIDER_VERSION}")
        if output_dir.exists():
            print(f"🧹 Cleaning output directory: {output_dir}")
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Reset the processed services list
    reset_processed_services()

    # Process all services
    for svc in extract_services(Path("models")):
        protocol = svc["protocol"]
        if protocol in PROTOCOL_DISPATCH:
            PROTOCOL_DISPATCH[protocol](svc)
        else:
            print(f"❓ Skipping {svc['servicename']} — unknown protocol: {protocol}")

    # Generate the provider.yaml index file
    generate_provider_yaml()
