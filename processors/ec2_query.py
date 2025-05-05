def process(model_entry):
    service_name = model_entry['servicename'].split('#')[0].split('com.amazonaws.')[1]
    print(f"processing {service_name} with protocol {model_entry['protocol']}")
