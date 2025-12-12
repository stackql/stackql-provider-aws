# StackQL Provider Development Skill

This skill provides comprehensive guidance for developing StackQL providers using the `any-sdk` library. StackQL providers are OpenAPI 3.0 specifications augmented with custom `x-stackQL-*` extensions that enable SQL-like semantics for REST APIs.

## Overview

StackQL providers follow a hierarchical structure:
```
Provider -> ProviderService -> Resource -> Method -> Operation
```

Each level can contain configuration that cascades down to child elements.

---

## Provider Document Structure

### Provider Definition (`provider.yaml`)

```yaml
id: string                    # Required: Unique provider identifier
name: string                  # Required: Provider name (e.g., "google", "aws", "azure")
title: string                 # Required: Human-readable title
version: string               # Required: Provider version
description: string           # Optional: Provider description
protocolType: string          # Optional: "http" (default) or "local_templated"

providerServices:             # Required: Map of service names to service definitions
  <serviceName>:
    id: string
    name: string
    title: string
    version: string
    description: string
    preferred: boolean        # Optional: Mark as preferred service version
    service:                  # Reference to service document
      $ref: "path/to/service.yaml"
    resources:                # Optional: Reference to resources document
      $ref: "path/to/resources.yaml"

config:                       # Optional: Provider-level StackQL config
  auth: {...}
  pagination: {...}
  # ...other config options

responseKeys:                 # Optional: Default response extraction keys
  selectItemsKey: "items"     # Default key to extract list items
  deleteItemsKey: "id"        # Default key for delete operations
```

### Service Document Structure

```yaml
openapi: 3.0.0
info:
  title: Service Title
  version: "1.0.0"

servers:
  - url: https://api.example.com
    variables:
      region:
        default: us-east-1
        enum: [us-east-1, us-west-2]

components:
  x-stackQL-resources:        # StackQL resource definitions
    <resourceName>:
      id: provider.service.resource
      name: resource_name
      title: Resource Title
      description: Optional description
      methods:
        <methodName>:
          operation:
            $ref: '#/paths/~1path~1to~1endpoint/get'
          response:
            mediaType: application/json
            openAPIDocKey: '200'
            objectKey: $.items
      sqlVerbs:
        select: [...]
        insert: [...]
        update: [...]
        delete: [...]
      config: {...}           # Optional: Resource-level config

  schemas: {...}              # OpenAPI schemas
  parameters: {...}           # Reusable parameters
  securitySchemes: {...}      # Authentication schemes

paths:
  /path/to/endpoint:
    get:
      operationId: provider.service.operation_name
      # ...standard OpenAPI operation definition

x-stackQL-config: {...}       # Optional: Service-level config
```

---

## OpenAPI Extensions Reference

### Document/Service Level Extensions

#### `x-stackQL-resources`
**Location:** `components.x-stackQL-resources`

Defines resources and their SQL verb mappings.

```yaml
components:
  x-stackQL-resources:
    instances:
      id: google.compute.instances
      name: instances
      title: Compute Instances
      description: Virtual machine instances
      methods:
        list:
          operation:
            $ref: '#/paths/~1projects~1{project}~1zones~1{zone}~1instances/get'
          response:
            mediaType: application/json
            openAPIDocKey: '200'
            objectKey: $.items
        get:
          operation:
            $ref: '#/paths/~1projects~1{project}~1zones~1{zone}~1instances~1{instance}/get'
          response:
            mediaType: application/json
            openAPIDocKey: '200'
        insert:
          operation:
            $ref: '#/paths/~1projects~1{project}~1zones~1{zone}~1instances/post'
          request:
            mediaType: application/json
          response:
            mediaType: application/json
            openAPIDocKey: '200'
        delete:
          operation:
            $ref: '#/paths/~1projects~1{project}~1zones~1{zone}~1instances~1{instance}/delete'
          response:
            mediaType: application/json
            openAPIDocKey: '200'
      sqlVerbs:
        select:
          - $ref: '#/components/x-stackQL-resources/instances/methods/list'
          - $ref: '#/components/x-stackQL-resources/instances/methods/get'
        insert:
          - $ref: '#/components/x-stackQL-resources/instances/methods/insert'
        update: []
        delete:
          - $ref: '#/components/x-stackQL-resources/instances/methods/delete'
```

**SQL Verb Ordering:** Methods under the same SQL verb should be ordered by ascending selectivity (number of required parameters). The first matching method based on provided parameters will be used.

#### `x-stackQL-config`
**Location:** `components.x-stackQL-config` or inline at resource/method level

Provider/service/resource configuration.

```yaml
x-stackQL-config:
  auth:
    type: service_account
    credentialsenvvar: GOOGLE_CREDENTIALS
    scopes:
      - https://www.googleapis.com/auth/cloud-platform

  pagination:
    requestToken:
      key: pageToken
      location: query
    responseToken:
      key: nextPageToken
      location: body

  queryParamTranspose:
    algorithm: default

  requestTranslate:
    algorithm: default

  requestBodyTranslate:
    algorithm: naive

  variations:
    isObjectSchemaImplicitlyUnioned: false

  views:
    select:
      predicate: 'sqlDialect == "stackql"'
      ddl: |
        SELECT id, name, status
        FROM google.compute.instances
        WHERE project = '{{ .project }}'
      fallback:
        predicate: 'sqlDialect == "postgres"'
        ddl: |
          SELECT id, name, status FROM instances

  sqlExternalTables:
    external_data:
      catalogName: external
      schemaName: public
      name: data
      columns:
        - name: id
          type: string
        - name: value
          type: integer
```

#### `x-stackQL-provider`
**Location:** `info` section (for embedded provider metadata)

```yaml
info:
  x-stackQL-provider:
    name: myprovider
    version: v0.1.0
```

### Operation Level Extensions

#### `x-stackQL-resource`
Associates an operation with a specific resource.

```yaml
paths:
  /instances:
    get:
      operationId: listInstances
      x-stackQL-resource: instances
```

#### `x-stackQL-method`
Specifies the method name for an operation.

```yaml
paths:
  /instances:
    get:
      operationId: listInstances
      x-stackQL-method: list
```

#### `x-stackQL-verb`
Maps operation to SQL verb.

```yaml
paths:
  /instances:
    get:
      x-stackQL-verb: select
    post:
      x-stackQL-verb: insert
    delete:
      x-stackQL-verb: delete
```

**Valid SQL verbs:** `select`, `insert`, `update`, `delete`, `exec`

#### `x-stackQL-objectKey`
JSONPath selector to extract items from response.

```yaml
response:
  mediaType: application/json
  openAPIDocKey: '200'
  objectKey: $.items
```

**Formats:**
- JSONPath: `$.items`, `$.data.results`
- XPath (for XML): `/Response/Items/Item`

### Schema Level Extensions

#### `x-stackQL-stringOnly`
Marks a schema property as string-only (serialized as string even if typed differently).

```yaml
components:
  schemas:
    Resource:
      properties:
        metadata:
          type: object
          x-stackQL-stringOnly: true
```

#### `x-stackQL-alias`
Property aliasing for response flattening.

```yaml
components:
  schemas:
    Resource:
      properties:
        resourceId:
          type: string
          x-stackQL-alias: id
```

#### `x-alwaysRequired`
Marks a parameter as always required.

```yaml
components:
  parameters:
    projectId:
      name: project
      in: path
      required: true
      x-alwaysRequired: true
```

### GraphQL Extension

#### `x-stackQL-graphQL`
Configures GraphQL operations.

```yaml
x-stackQL-graphQL:
  id: queryUsers
  query: |
    query GetUsers($first: Int, $after: String) {
      users(first: $first, after: $after) {
        nodes { id name email }
        pageInfo { hasNextPage endCursor }
      }
    }
  url: https://api.example.com/graphql
  httpVerb: POST
  cursor:
    jsonPath: $.data.users.pageInfo.endCursor
  responseSelection:
    jsonPath: $.data.users.nodes
```

---

## Configuration Reference

### Authentication (`auth`)

```yaml
auth:
  type: string              # Required: Auth type (see below)
  name: string              # Optional: Header/param name
  location: string          # Optional: "header" or "query"
  valuePrefix: string       # Optional: Prefix for auth value (e.g., "Bearer ")
  scopes: [string]          # Optional: OAuth scopes

  # Service Account (Google-style)
  credentialsfilepath: string         # Path to credentials file
  credentialsfilepathenvvar: string   # Env var with file path
  credentialsenvvar: string           # Env var with credentials JSON
  keyID: string
  keyIDenvvar: string
  sub: string                         # Subject for impersonation

  # API Key
  api_key: string
  api_key_var: string                 # Env var for API key
  api_secret: string
  api_secret_var: string

  # Basic Auth
  username: string
  password: string
  username_var: string
  password_var: string

  # OAuth2 Client Credentials
  client_id: string
  client_secret: string
  client_id_env_var: string
  client_secret_env_var: string
  token_url: string
  grant_type: string                  # e.g., "client_credentials"
  auth_style: integer                 # 0=auto, 1=params, 2=header
  values: {...}                       # Additional token request params

  # AWS Signature
  account_id: string
  account_id_env_var: string

  successor:                          # Chained auth (fallback)
    type: ...
```

**Authentication Types:**
- `service_account` - Google service account
- `api_key` - API key in header or query
- `basic` - HTTP Basic authentication
- `bearer` - Bearer token
- `oauth2` - OAuth 2.0 client credentials
- `aws_signing_v4` - AWS Signature Version 4
- `azure_default` - Azure default credentials
- `custom` - Custom authentication

### Pagination (`pagination`)

```yaml
pagination:
  requestToken:
    key: string             # Parameter name (e.g., "pageToken", "page")
    location: string        # "query", "header", or "body"
    algorithm: string       # Optional: Custom parsing algorithm
    args:                   # Optional: Algorithm arguments
      regex: string
  responseToken:
    key: string             # Response field containing next token
    location: string        # "body" or "header"
    algorithm: string
```

**Common Patterns:**

```yaml
# Token-based (Google, Azure)
pagination:
  requestToken:
    key: pageToken
    location: query
  responseToken:
    key: nextPageToken
    location: body

# Link header (GitHub)
pagination:
  requestToken:
    key: page
    location: query
  responseToken:
    key: Link
    location: header

# Offset-based
pagination:
  requestToken:
    key: offset
    location: query
  responseToken:
    key: next_offset
    location: body
```

### Transform (`queryParamTranspose`, `requestTranslate`, `requestBodyTranslate`)

```yaml
queryParamTranspose:
  algorithm: string         # "default" or "naive"
  type: string              # Optional: Template type
  body: string              # Optional: Template body

requestTranslate:
  algorithm: string         # Transform algorithm

requestBodyTranslate:
  algorithm: string         # "default" or "naive_<path>"
```

**Algorithms:**
- `default` - Standard parameter/body transformation with `data__` prefix
- `naive` - Direct mapping without prefix
- `naive_<path>` - Naive transformation at specified JSON path
- `AWSCanonical` - AWS canonical request format
- `get_query_to_post_form_utf_8` - Convert GET query params to POST form

### Variations (`variations`)

```yaml
variations:
  isObjectSchemaImplicitlyUnioned: boolean  # Handle Azure-style allOf schemas
```

### Views (`views`)

```yaml
views:
  <viewName>:
    predicate: string       # Condition expression (e.g., 'sqlDialect == "stackql"')
    ddl: string             # SQL view definition
    fallback:               # Optional: Fallback view for different dialects
      predicate: string
      ddl: string
```

**Predicate Variables:**
- `sqlDialect` - Target SQL dialect ("stackql", "postgres", etc.)
- `requiredParams` - Array check for required parameters

```yaml
views:
  select:
    predicate: 'sqlDialect == "stackql" && requiredParams == ["project", "region"]'
    ddl: |
      SELECT * FROM google.compute.instances WHERE project = '{{ .project }}'
```

### External Tables (`sqlExternalTables`)

```yaml
sqlExternalTables:
  <tableName>:
    catalogName: string
    schemaName: string
    name: string
    columns:
      - name: string
        type: string        # SQL type
        oid: integer        # PostgreSQL OID
        width: integer
        precision: integer
```

### Query Parameter Pushdown (`queryParamPushdown`)

Enables SQL clause pushdown to API query parameters. Supports OData and custom API dialects for filter, projection, ordering, and limit operations.

**Location:** Can be set at **provider, providerService, service, resource, or method level**. Config inherits from higher levels, with lower levels overriding higher levels:

```
Method -> Resource -> Service -> ProviderService -> Provider
```

This allows you to set a default OData config at the service level and have all resources/methods inherit it, while still allowing specific methods to override with custom settings.

```yaml
x-stackQL-config:
  queryParamPushdown:
    # Column projection (SELECT clause pushdown)
    select:
      dialect: odata | custom    # "custom" is default; "odata" applies OData defaults
      paramName: "$select"       # Not required for OData (default: "$select")
      delimiter: ","             # Not required for OData (default: ",")
      supportedColumns:          # Optional, omit or ["*"] for all columns
        - "id"
        - "name"
        - "status"

    # Row filtering (WHERE clause pushdown)
    filter:
      dialect: odata | custom    # "custom" is default; "odata" applies OData defaults
      paramName: "$filter"       # Not required for OData (default: "$filter")
      syntax: odata              # Not required for OData (default: "odata")
      supportedOperators:        # Required - which operators can be pushed down
        - "eq"
        - "ne"
        - "gt"
        - "lt"
        - "ge"
        - "le"
        - "contains"
        - "startswith"
      supportedColumns:          # Optional, omit or ["*"] for all columns
        - "displayName"
        - "status"
        - "createdDate"

    # Ordering (ORDER BY clause pushdown)
    orderBy:
      dialect: odata | custom    # "custom" is default; "odata" applies OData defaults
      paramName: "$orderby"      # Not required for OData (default: "$orderby")
      syntax: odata              # Not required for OData (default: "odata")
      supportedColumns:          # Optional, omit or ["*"] for all columns
        - "name"
        - "createdDate"

    # Row limit (LIMIT clause pushdown)
    top:
      dialect: odata | custom    # "custom" is default; "odata" applies OData defaults
      paramName: "$top"          # Not required for OData (default: "$top")
      maxValue: 1000             # Optional, cap on pushdown value

    # Count (SELECT COUNT(*) pushdown)
    count:
      dialect: odata | custom    # "custom" is default; "odata" applies OData defaults
      paramName: "$count"        # Not required for OData (default: "$count")
      paramValue: "true"         # Not required for OData (default: "true")
      responseKey: "@odata.count"# Not required for OData (default: "@odata.count")
```

**Minimal OData Configuration:**

When using OData dialect, defaults are applied automatically:

```yaml
x-stackQL-config:
  queryParamPushdown:
    select: {}
    filter:
      dialect: odata
      supportedOperators: ["eq", "ne", "gt", "lt", "contains"]
    orderBy:
      dialect: odata
    top:
      dialect: odata
    count:
      dialect: odata
```

**Custom API Configuration:**

For APIs with custom query parameter names:

```yaml
x-stackQL-config:
  queryParamPushdown:
    select:
      paramName: "fields"
      delimiter: ","
    filter:
      paramName: "filter"
      syntax: "key_value"        # filter[status]=active&filter[region]=us-east-1
      supportedOperators:
        - "eq"
      supportedColumns:
        - "status"
        - "region"
    orderBy:
      paramName: "sort"
      syntax: "prefix"           # sort=-createdAt (prefix - for desc)
      supportedColumns:
        - "createdAt"
        - "name"
    top:
      paramName: "limit"
      maxValue: 100
    count:
      paramName: "include_count"
      paramValue: "1"
      responseKey: "meta.total"
```

**Supported Filter Syntaxes:**

| Syntax | Example Output | Use Case |
|--------|---------------|----------|
| `odata` | `$filter=status eq 'active' and region eq 'us-east-1'` | OData APIs |
| `key_value` | `filter[status]=active&filter[region]=us-east-1` | Rails-style APIs |
| `simple` | `status=active&region=us-east-1` | Basic query params |

**Supported OrderBy Syntaxes:**

| Syntax | Example | Notes |
|--------|---------|-------|
| `odata` | `$orderby=name desc,date asc` | Space-separated direction |
| `prefix` | `sort=-name,+date` | `-` for desc, `+` or none for asc |
| `suffix` | `sort=name:desc,date:asc` | Colon-separated direction |

**Column/Operator Support Logic:**

| Value | Behavior |
|-------|----------|
| omitted / `null` | All items allowed |
| `["*"]` | Explicit "all items" (same as omitted) |
| `["col1", "col2"]` | Only these items supported |
| `[]` | No items supported (effectively disabled) |

**OData Example with Inheritance (TripPin Reference Service):**

Set a default config at service level, then override at resource or method level as needed:

```yaml
# Service-level config - inherited by all resources/methods
x-stackQL-config:
  queryParamPushdown:
    select:
      dialect: odata
    filter:
      dialect: odata
      supportedOperators:
        - "eq"
        - "ne"
    orderBy:
      dialect: odata
    top:
      dialect: odata
    count:
      dialect: odata

components:
  x-stackQL-resources:
    # Inherits service-level config (no override needed)
    airlines:
      id: odata.trippin.airlines
      name: airlines
      methods:
        list:
          operation:
            $ref: '#/paths/~1Airlines/get'
          # No config - inherits from service level
      sqlVerbs:
        select:
          - $ref: '#/components/x-stackQL-resources/airlines/methods/list'

    # Resource-level override with full operator support
    people:
      id: odata.trippin.people
      name: people
      config:
        queryParamPushdown:
          filter:
            dialect: odata
            supportedOperators:
              - "eq"
              - "ne"
              - "gt"
              - "lt"
              - "contains"
              - "startswith"
      methods:
        list:
          operation:
            $ref: '#/paths/~1People/get'
      sqlVerbs:
        select:
          - $ref: '#/components/x-stackQL-resources/people/methods/list'

    # Method-level override with restricted columns
    airports:
      id: odata.trippin.airports
      name: airports
      methods:
        list:
          operation:
            $ref: '#/paths/~1Airports/get'
          config:
            queryParamPushdown:
              select:
                dialect: odata
                supportedColumns:
                  - "Name"
                  - "IcaoCode"
              filter:
                dialect: odata
                supportedColumns:
                  - "Name"
                  - "IcaoCode"
              top:
                dialect: odata
                maxValue: 100
      sqlVerbs:
        select:
          - $ref: '#/components/x-stackQL-resources/airports/methods/list'
```

---

## Method Definition

### Complete Method Structure

```yaml
methods:
  methodName:
    operation:
      $ref: '#/paths/~1endpoint/get'

    request:
      mediaType: application/json
      default: '{"key": "default_value"}'  # Default request body
      base: '{"always": "included"}'        # Base request body
      required: [field1, field2]            # Required body fields
      projection_map:                       # Request field projections
        alias: actualFieldName
      xmlDeclaration: '<?xml version="1.0"?>'
      xmlTransform: unescape
      xmlRootAnnotation: '<root xmlns="...">'

    response:
      mediaType: application/json
      openAPIDocKey: '200'
      objectKey: $.items
      overrideMediaType: application/json   # Override response parsing
      schema_override:                      # Custom response schema
        $ref: '#/components/schemas/CustomSchema'
      async_schema_override:                # Async operation schema
        $ref: '#/components/schemas/AsyncSchema'
      asyncOverrideMediaType: application/json
      projection_map:                       # Response field projections
        alias: actualFieldName
      transform:                            # Response transformation
        type: golang_template_mxj_v0.1.0
        body: |
          {"processed": {{.field}}}

    servers:                                # Operation-specific servers
      - url: https://custom-api.example.com

    inverse:                                # Rollback operation
      sqlVerb:
        $ref: '#/components/x-stackQL-resources/resource/methods/delete'
      tokens:
        id:
          key: id
          location: body

    config:                                 # Method-level config
      pagination: {...}
      auth: {...}

    apiMethod: GET                          # HTTP method override
    serviceName: custom_service             # Service name override
```

### Inverse Operations (Rollback Support)

```yaml
methods:
  insert:
    operation:
      $ref: '#/paths/~1resources/post'
    inverse:
      sqlVerb:
        $ref: '#/components/x-stackQL-resources/resources/methods/delete'
      tokens:
        resourceId:
          key: $.id
          location: body
          algorithm: jsonpath
```

---

## SQL Verb Mapping

### Method Selection Algorithm

When a SQL query is executed, StackQL selects methods based on:

1. **SQL Verb Mapping:** Match query type (SELECT, INSERT, UPDATE, DELETE) to `sqlVerbs`
2. **Parameter Matching:** Find methods where provided parameters satisfy required parameters
3. **Selectivity Ordering:** Methods are tried in order of ascending required parameter count

### Example SQL Verb Definitions

```yaml
sqlVerbs:
  select:
    # List operation (fewer required params, tried first for broad queries)
    - $ref: '#/components/x-stackQL-resources/instances/methods/list'
    # Get operation (more required params, used when instance ID provided)
    - $ref: '#/components/x-stackQL-resources/instances/methods/get'
  insert:
    - $ref: '#/components/x-stackQL-resources/instances/methods/insert'
  update:
    - $ref: '#/components/x-stackQL-resources/instances/methods/update'
    - $ref: '#/components/x-stackQL-resources/instances/methods/patch'
  delete:
    - $ref: '#/components/x-stackQL-resources/instances/methods/delete'
```

---

## Protocol Types

### HTTP Protocol (Default)

Standard REST API over HTTP/HTTPS.

```yaml
protocolType: http
```

### Local Templated Protocol

For local command execution with templated inputs.

```yaml
protocolType: local_templated
```

Used with templated services for executing local commands (e.g., openssl, kubectl).

---

## Response Processing

### Object Key Extraction

**JSONPath Examples:**
```yaml
objectKey: $.items              # Simple array extraction
objectKey: $.data.results       # Nested path
objectKey: $[*]                 # Root array
objectKey: $.response.items[*]  # Array within nested object
```

**XPath Examples (for XML):**
```yaml
objectKey: /Response/Items/Item
objectKey: //Volume
objectKey: /DescribeVolumesResponse/volumeSet/item
```

### Response Transformation

```yaml
response:
  transform:
    type: golang_template_mxj_v0.1.0
    body: |
      {
        "items": [
          {{- range $i, $item := .data.items }}
          {{- if $i}},{{end}}
          {
            "id": {{printf "%q" $item.id}},
            "name": {{printf "%q" $item.name}},
            "count": {{toInt $item.count}},
            "enabled": {{toBool $item.enabled}}
          }
          {{- end }}
        ]
      }
```

**Template Functions:**
- `printf "%q"` - Quote string
- `toInt` - Convert to integer
- `toBool` - Convert to boolean
- `with`/`else` - Conditional handling

---

## Complete Provider Example

```yaml
# provider.yaml
id: example
name: example
title: Example Provider
version: v1.0.0
description: Example StackQL provider

providerServices:
  api:
    id: example.api
    name: api
    title: Example API
    version: v1
    service:
      $ref: services/api.yaml

config:
  auth:
    type: api_key
    name: X-API-Key
    location: header
    api_key_var: EXAMPLE_API_KEY
  pagination:
    requestToken:
      key: page
      location: query
    responseToken:
      key: nextPage
      location: body
```

```yaml
# services/api.yaml
openapi: 3.0.0
info:
  title: Example API
  version: "1.0.0"

servers:
  - url: https://api.example.com/v1

components:
  x-stackQL-resources:
    users:
      id: example.api.users
      name: users
      title: Users
      methods:
        list:
          operation:
            $ref: '#/paths/~1users/get'
          response:
            mediaType: application/json
            openAPIDocKey: '200'
            objectKey: $.users
        get:
          operation:
            $ref: '#/paths/~1users~1{userId}/get'
          response:
            mediaType: application/json
            openAPIDocKey: '200'
        create:
          operation:
            $ref: '#/paths/~1users/post'
          request:
            mediaType: application/json
          response:
            mediaType: application/json
            openAPIDocKey: '201'
        delete:
          operation:
            $ref: '#/paths/~1users~1{userId}/delete'
          response:
            mediaType: application/json
            openAPIDocKey: '204'
      sqlVerbs:
        select:
          - $ref: '#/components/x-stackQL-resources/users/methods/list'
          - $ref: '#/components/x-stackQL-resources/users/methods/get'
        insert:
          - $ref: '#/components/x-stackQL-resources/users/methods/create'
        update: []
        delete:
          - $ref: '#/components/x-stackQL-resources/users/methods/delete'

paths:
  /users:
    get:
      operationId: listUsers
      parameters:
        - name: page
          in: query
          schema:
            type: integer
        - name: limit
          in: query
          schema:
            type: integer
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UserList'
    post:
      operationId: createUser
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateUserRequest'
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/User'

  /users/{userId}:
    get:
      operationId: getUser
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/User'
    delete:
      operationId: deleteUser
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
      responses:
        '204':
          description: Deleted

  schemas:
    User:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        email:
          type: string
    UserList:
      type: object
      properties:
        users:
          type: array
          items:
            $ref: '#/components/schemas/User'
        nextPage:
          type: integer
    CreateUserRequest:
      type: object
      required:
        - name
        - email
      properties:
        name:
          type: string
        email:
          type: string
```

---

## Best Practices

1. **Resource Naming:** Use plural, snake_case names (e.g., `instances`, `storage_accounts`)

2. **Method Naming:** Use descriptive names matching the operation (e.g., `list`, `get`, `create`, `delete`)

3. **SQL Verb Ordering:** Order methods by ascending parameter count for correct matching

4. **Object Keys:** Use JSONPath for consistent response extraction

5. **Schema Reuse:** Define schemas in `components/schemas` and reference them

6. **Configuration Inheritance:** Place common config at higher levels (provider/service) for inheritance

7. **Error Handling:** Include appropriate response codes in OpenAPI definitions

8. **Parameter Validation:** Use OpenAPI schema validation for parameters

9. **Documentation:** Include descriptions for resources, methods, and parameters
