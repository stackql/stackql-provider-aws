# StackQL Provider Generation

This document describes the workflow for generating StackQL-compatible OpenAPI specifications from AWS Smithy models.

## Overview

The generation process converts AWS Smithy IDL models into OpenAPI specifications with StackQL extensions (`x-stackQL-resources` and `x-stackQL-config`). This is a two-step process:

1. **Analyze** - Generate CSV manifests with inferred resource mappings
2. **Process** - Generate OpenAPI specs using CSV manifests for lookups

## Prerequisites

Install required Python packages:

```bash
pip install html2text inflect pyyaml
```

Ensure the `models` directory contains AWS Smithy models (from [aws/api-models-aws](https://github.com/aws/api-models-aws)).

## Workflow

### Step 1: Analyze Routes

Run the analysis script to generate CSV manifests:

```bash
cd smithy-to-openapi
python analyze_stackql_routes.py
```

This creates/updates CSV files in `stackql-routes/{service}.csv` with one row per operation.

### Step 2: Review and Modify CSV Manifests

Review the generated CSV files. Each file contains:

| Column | Description |
|--------|-------------|
| `operationId` | The AWS operation ID (e.g., `DescribeInstances`) |
| `path` | The API path |
| `verb` | HTTP method (GET, POST, etc.) |
| `description` | Truncated operation description |
| `resource` | Inferred StackQL resource name (e.g., `instances`) |
| `method` | Inferred method name (e.g., `describe_instances`) |
| `sqlVerb` | StackQL SQL verb (`select`, `insert`, `update`, `delete`, `exec`) |
| `objectKey` | Response object key for data extraction (optional) |
| `reqPaginationKey` | Request pagination token key (only if overriding service default) |
| `reqPaginationLocation` | Request token location (`query`, `header`, `body`) |
| `respPaginationKey` | Response pagination token key (only if overriding service default) |
| `respPaginationLocation` | Response token location (`body`, `header`) |

**Important**: Existing CSV entries are preserved when re-running the analysis. This allows you to:
- Override inferred values with correct ones
- Maintain human-reviewed mappings across regenerations
- Only new operations are appended to existing CSVs

### Step 3: Generate OpenAPI Specs

Run the processing script:

```bash
python process_models.py [--clean]
```

Options:
- `--clean`: Remove existing output before processing

Output is written to: `openapi/src/aws/v00.00.00000/services/`

This also generates `provider.yaml` which indexes all services.

## CSV Manifest Rules

### Resource Names

Resource names should be:
- Plural (e.g., `instances` not `instance`)
- Snake_case (e.g., `auto_scaling_groups`)
- Descriptive of the resource being operated on

### SQL Verb Mapping

| Pattern | SQL Verb |
|---------|----------|
| `Describe*`, `Get*`, `List*`, `Query*` | `select` |
| `Create*`, `Put*`, `Add*` | `insert` |
| `Update*`, `Modify*`, `Set*` | `update` |
| `Delete*`, `Remove*`, `Terminate*` | `delete` |
| Other | `exec` |

### Object Keys

The `objectKey` field specifies where to find the actual data in the response. For example:
- S3 ListBuckets: `$.Buckets`
- EC2 DescribeInstances: `$.Reservations[*].Instances[*]`

### Pagination Overrides

Pagination fields are only populated when an operation uses different pagination than the service default. The service-level pagination is detected automatically and applied via `x-stackQL-config`.

## Directory Structure

```
smithy-to-openapi/
├── analyze_stackql_routes.py  # Step 1: Analyze and generate CSVs
├── process_models.py          # Step 2: Generate OpenAPI specs
├── processors/
│   ├── shared_functions.py    # Shared utilities
│   ├── rest_json1.py          # restJson1 protocol handler
│   ├── rest_xml.py            # restXml protocol handler
│   ├── aws_json_1_0.py        # awsJson1_0 protocol handler
│   ├── aws_json_1_1.py        # awsJson1_1 protocol handler
│   ├── aws_query.py           # awsQuery protocol handler
│   └── ec2_query.py           # ec2Query protocol handler
├── stackql-routes/            # CSV manifests per service
│   ├── ec2.csv
│   ├── s3.csv
│   └── ...
└── openapi/
    └── src/aws/v00.00.00000/
        ├── provider.yaml      # Provider index
        └── services/
            ├── ec2.yaml
            ├── s3.yaml
            └── ...
```

## Examples

### Correcting a Resource Name

If `DescribeAutoScalingGroups` is incorrectly mapped to `groups`, edit `autoscaling.csv`:

```csv
operationId,path,verb,description,resource,method,sqlVerb,objectKey,...
DescribeAutoScalingGroups,/#Action=DescribeAutoScalingGroups,GET,...,auto_scaling_groups,describe_auto_scaling_groups,select,$.AutoScalingGroups,...
```

### Adding Object Keys

To extract data from nested responses:

```csv
operationId,path,verb,description,resource,method,sqlVerb,objectKey,...
ListBuckets,/,GET,...,buckets,list_buckets,select,$.Buckets,...
```

## Regenerating After Model Updates

When AWS models are updated:

1. Run `python analyze_stackql_routes.py` - New operations are appended, existing entries preserved
2. Review new entries in CSV files
3. Run `python process_models.py --clean` to regenerate all specs
