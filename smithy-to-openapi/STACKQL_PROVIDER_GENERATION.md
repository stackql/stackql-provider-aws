
# StackQL Provider Generation

This document describes the workflow for generating StackQL-compatible OpenAPI specifications from AWS Smithy models.

## Overview

The generation process converts AWS Smithy IDL models into OpenAPI specifications with StackQL extensions (`x-stackQL-resources` and `x-stackQL-config`). This is a two-step process:

1. **Analyze** - Generate CSV manifests with inferred resource mappings
2. **Process** - Generate OpenAPI specs using CSV manifests for lookups

## Prerequisites

### Python Env Setup

Install required Python packages:

```bash
python3 -m venv .ven
source .venv/bin/activate
pip install -r smithy-to-openapi/requirements.txt
```

Ensure the `models` directory contains AWS Smithy models (from [aws/api-models-aws](https://github.com/aws/api-models-aws)).

### Node Env setup

The `@stackql/pgwire-lite` and `@stackql/provider-utils` node libraries are used to generate docs and to test the provider, install these using `npm i`.

## Workflow

### Step 1: Analyze Routes

Run the analysis script to generate CSV manifests:

```bash
python smithy-to-openapi/analyze_stackql_routes.py
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
| `resource` | TODO Update with the appropriate StackQL resource name |
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

### Step 3: Generate OpenAPI Specs and StackQL Provider

Run the processing script:

```bash
python smithy-to-openapi/process_models.py --clean
```

Options:
- `--clean`: Remove existing output before processing

Output is written to: `openapi/src/aws/v00.00.00000/services/`

This also generates `provider.yaml` which indexes all services.

### Step 4: Test StackQL Provider

#### Starting the StackQL Server

Before running tests, start a StackQL server with your provider:

```bash
PROVIDER_REGISTRY_ROOT_DIR="$(pwd)/smithy-to-openapi/openapi"
npm run start-server -- --provider aws --registry $PROVIDER_REGISTRY_ROOT_DIR
```

#### Test Meta Routes

Test all metadata routes (services, resources, methods) in the provider:

```bash
npm run test-meta-routes -- aws --verbose
```

When you're done testing, stop the StackQL server:

```bash
npm run stop-server
```

Use this command to view the server status:

```bash
npm run server-status
```

#### Run test queries

Run some test queries against the provider using the `stackql shell`:

```bash
PROVIDER_REGISTRY_ROOT_DIR="$(pwd)/smithy-to-openapi/openapi"
REG_STR='{"url": "file://'${PROVIDER_REGISTRY_ROOT_DIR}'", "localDocRoot": "'${PROVIDER_REGISTRY_ROOT_DIR}'", "verifyConfig": {"nopVerify": true}}'
./stackql shell --registry="${REG_STR}"
```

Example queries to try:

```sql
-- List all zones
SELECT 
  id,
  name,
  status,
  plan.name as plan_name
FROM 
  cloudflare.zones.zones;

-- List all DNS records for a specific zone
SELECT 
  id,
  name,
  type,
  content,
  proxied
FROM 
  cloudflare.dns.records
WHERE 
  zone_id = 'your-zone-id';

-- List all Worker scripts
SELECT 
  id,
  script_name,
  created_on,
  modified_on
FROM 
  cloudflare.workers.scripts;
```