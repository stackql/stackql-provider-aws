import json
import csv
from pathlib import Path


def extract_services(input_dir: Path):
    service_entries = []
    for model_file in input_dir.glob("*.json"):
        try:
            with open(model_file, "r") as f:
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

    services = extract_services(Path("models"))
    write_csv(Path("model_inventory.csv"), services)
    print(f"✅ Done! {len(services)} services found.")
