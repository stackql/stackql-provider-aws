# StackQL Provider Generation

This repository is a fork of [__`aws/api-models-aws`__](https://github.com/aws/api-models-aws), it uses the [smithy models]() from the upstream repository to generate the [__`stackql`__](https://github.com/stackql/stackql) provider for AWS.  Steps to generate the __`aws`__ provider for __`stackql`__ are provided below:

## 1. Generate OpenAPI Specs from Smithy Models for AWS Services

**[OPTIONAL]** If you want to analyze the different aws services available and their protocols, you can execute : `python3 smithy-to-openapi/model_inventory.py`.  

**a. prepare a virtual environment:**  

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r smithy-to-openapi/requirements.txt
```

**b. convert models to base OpenAPI specs:**  

```bash
python3 smithy-to-openapi/process_models.py --clean
deactivate # optional
```

This will convert each smithy model (for each AWS service) into a corresponding OpenAPI specification in `smithy-to-openapi/openapi` using the appropriate processor (e.g. `rest_json1`, `ec2_query`, etc).

## 2. Generate StackQL Provider

## 3. Generate StackQL Provider Docs for `aws`