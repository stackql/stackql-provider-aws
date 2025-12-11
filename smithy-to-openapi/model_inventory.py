import json
import csv
import sys
from pathlib import Path


def extract_services(input_dir: Path):
    service_entries = []
    
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
                        for key in traits.keys():
                            if key.startswith("aws.protocols#"):
                                protocol = key
                                break

                        service_entries.append({
                            "filename": model_file.name,
                            "servicename": shape_name,
                            "protocol": protocol
                        })
            except json.JSONDecodeError as e:
                service_entries.append({
                    "filename": model_file.name,
                    "servicename": "ERROR",
                    "protocol": f"JSON decode error: {e}"
                })
            except UnicodeDecodeError as e:
                service_entries.append({
                    "filename": model_file.name,
                    "servicename": "ERROR",
                    "protocol": f"Encoding error: {e}"
                })
            except Exception as e:
                service_entries.append({
                    "filename": model_file.name,
                    "servicename": "ERROR",
                    "protocol": str(e)
                })
    
    return service_entries


def write_csv(output_file: Path, rows):
    with open(output_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["filename", "servicename", "protocol"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    if not Path("models").exists():
        print("❌ ERROR: 'models' directory not found. Please run this script from the project root.")
        sys.exit(1)
    services = extract_services(Path("models"))
    write_csv(Path("smithy-to-openapi/model_inventory.csv"), services)
    print(f"✅ Done! {len(services)} services found.")
