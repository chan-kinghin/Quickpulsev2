# QuickPulse V2 API Reference

Base URL: `https://fltpulse.szfluent.cn` (production) or `https://dev.fltpulse.szfluent.cn` (development)

All `/api/*` responses include the header `X-API-Version: 1`.

---

## Table of Contents

1. [Authentication](#authentication)
2. [MTO Endpoints](#mto-endpoints)
3. [Search](#search)
4. [Export](#export)
5. [Sync Management](#sync-management)
6. [Cache Management](#cache-management)
7. [Chat (AI Assistant)](#chat-ai-assistant)
8. [Health](#health)
9. [Error Handling](#error-handling)
10. [Rate Limits](#rate-limits)
11. [CORS Configuration](#cors-configuration)

---

## Authentication

QuickPulse uses **OAuth2 password flow**. Obtain a JWT token, then pass it as a Bearer token on all protected endpoints.

### POST /api/auth/token

Obtain an access token.

**Rate limit:** 5 requests/minute

**Request** (form-encoded):

```bash
curl -X POST https://fltpulse.szfluent.cn/api/auth/token \
  -d "username=admin&password=YOUR_PASSWORD"
```

| Field      | Type   | Required | Description                                         |
|------------|--------|----------|-----------------------------------------------------|
| `username` | string | yes      | Any username (stored in the token `sub` claim)       |
| `password` | string | yes      | Must match the `AUTH_PASSWORD` environment variable   |

**Response** `200 OK`:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Response** `401 Unauthorized`:

```json
{
  "detail": "Incorrect username or password",
  "error_code": "unauthorized"
}
```

**Configuration** (environment variables):

| Variable                    | Default                              | Description                        |
|-----------------------------|--------------------------------------|------------------------------------|
| `AUTH_PASSWORD`             | `quickpulse`                         | Password required for token grant  |
| `AUTH_SECRET_KEY`           | `your-secret-key-change-in-production` | JWT signing secret               |
| `AUTH_TOKEN_EXPIRE_MINUTES` | `1440` (24 hours)                    | Token lifetime in minutes          |

### GET /api/auth/verify

Verify that a token is still valid.

**Headers:** `Authorization: Bearer <token>`

**Response** `200 OK`:

```json
{
  "valid": true,
  "username": "admin"
}
```

**Response** `401 Unauthorized` (expired or invalid token):

```json
{
  "detail": "Could not validate credentials",
  "error_code": "unauthorized"
}
```

### Using the token

All endpoints below (except `/health` and `/api/chat/status`) require the token:

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  https://fltpulse.szfluent.cn/api/mto/AK2510034
```

---

## MTO Endpoints

### GET /api/mto/{mto_number}

Retrieve the full MTO status including parent order info, child BOM items, and semantic metrics.

**Rate limit:** 30 requests/minute

**Path parameters:**

| Parameter    | Type   | Validation                         | Description          |
|--------------|--------|------------------------------------|----------------------|
| `mto_number` | string | Alphanumeric + hyphens, 2-50 chars | The MTO tracking number |

**Query parameters:**

| Parameter   | Type | Default | Description                                        |
|-------------|------|---------|----------------------------------------------------|
| `use_cache` | bool | `true`  | Use cached data if available and fresh (< 1 hour)  |

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/mto/AK2510034?use_cache=true"
```

**Response** `200 OK`:

```json
{
  "mto_number": "AK2510034",
  "parent_item": {
    "mto_number": "AK2510034",
    "customer_name": "Example Corp",
    "delivery_date": "2026-03-15"
  },
  "child_items": [
    {
      "material_code": "07.01.001",
      "material_name": "Product A",
      "specification": "100x200mm",
      "aux_attributes": "",
      "bom_short_name": "BOM-A",
      "material_type_code": 1,
      "material_type": "自制",
      "sales_order_qty": 100,
      "prod_instock_must_qty": 100,
      "purchase_order_qty": 0,
      "pick_actual_qty": 80,
      "prod_instock_real_qty": 95,
      "purchase_stock_in_qty": 0,
      "metrics": {
        "fulfillment_rate": {
          "value": 0.95,
          "label": "Fulfillment Rate",
          "format": "percent",
          "status": "in_progress"
        }
      }
    }
  ],
  "query_time": "2026-02-12T10:30:00",
  "data_source": "cache",
  "cache_age_seconds": 1200
}
```

**Response** `404 Not Found`:

```json
{
  "detail": "MTO number AK0000000 not found",
  "error_code": "not_found"
}
```

### GET /api/mto/{mto_number}/related-orders

Get all related order bill numbers for a given MTO number, organized by order type.

**Rate limit:** 30 requests/minute

**Path parameters:** Same validation as above.

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/mto/AK2510034/related-orders"
```

**Response** `200 OK`:

```json
{
  "mto_number": "AK2510034",
  "orders": {
    "production_orders": [
      { "bill_no": "SCDD001234", "label": "Production Order" }
    ],
    "purchase_orders": [
      { "bill_no": "CGDD005678", "label": "Purchase Order" }
    ]
  },
  "documents": {
    "production_receipts": [
      { "bill_no": "SCRKD001", "label": "Production Receipt", "linked_order": "SCDD001234" }
    ]
  },
  "query_time": "2026-02-12T10:30:00",
  "data_source": "live"
}
```

---

## Search

### GET /api/search

Search for MTO numbers or material names in the cached data. Supports pagination.

**Rate limit:** 60 requests/minute

**Query parameters:**

| Parameter | Type   | Default | Validation | Description                              |
|-----------|--------|---------|------------|------------------------------------------|
| `q`       | string | (required) | min 2 chars | Search term (matches MTO number or material name) |
| `limit`   | int    | `20`    | 1-100      | Maximum results per page                 |
| `offset`  | int    | `0`     | >= 0       | Number of results to skip                |

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/search?q=AK25&limit=10&offset=0"
```

**Response** `200 OK`:

The `X-Total-Count` response header contains the total number of matching records (for building pagination UI).

```
X-Total-Count: 42
```

```json
[
  {
    "mto_number": "AK2510034",
    "material_name": "Product A",
    "order_qty": 100,
    "status": "cached"
  },
  {
    "mto_number": "AK2510035",
    "material_name": "Product B",
    "order_qty": 50,
    "status": "cached"
  }
]
```

---

## Export

### GET /api/export/mto/{mto_number}

Export MTO status data as a CSV file.

**Rate limit:** 20 requests/minute

**Path parameters:**

| Parameter    | Type   | Description            |
|--------------|--------|------------------------|
| `mto_number` | string | The MTO tracking number |

**Query parameters:**

| Parameter   | Type | Default | Description                                     |
|-------------|------|---------|-------------------------------------------------|
| `use_cache` | bool | `false` | Use cached data (default false for accuracy)     |

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  -o "MTO_AK2510034.csv" \
  "https://fltpulse.szfluent.cn/api/export/mto/AK2510034"
```

**Response** `200 OK`: CSV file download with `Content-Disposition` header. The CSV columns are:

| Column               | Description               |
|----------------------|---------------------------|
| 物料编码             | Material code             |
| 物料名称             | Material name             |
| 规格型号             | Specification             |
| BOM简称              | BOM short name            |
| 辅助属性             | Auxiliary attributes      |
| 物料类型             | Material type name        |
| 销售订单.数量        | Sales order quantity      |
| 生产入库单.应收数量  | Production receipt expected qty |
| 采购订单.数量        | Purchase order quantity   |
| 生产领料单.实发数量  | Material picking actual qty |
| 生产入库单.实收数量  | Production receipt actual qty |
| 采购订单.累计入库数量 | Purchase cumulative instock qty |

---

## Sync Management

All sync endpoints require authentication.

### POST /api/sync/trigger

Start a data synchronization from Kingdee K3Cloud.

**Rate limit:** 2 requests/minute

**Request body** (JSON):

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"days_back": 90}' \
  "https://fltpulse.szfluent.cn/api/sync/trigger"
```

| Field        | Type | Default | Validation | Description                    |
|--------------|------|---------|------------|--------------------------------|
| `days_back`  | int  | `90`    | 1-365      | Number of days to sync         |
| `chunk_days` | int  | `7`     | 1-30       | Processing chunk size in days  |
| `force_full` | bool | `false` | --         | Force full refresh (alias: `force`) |

**Response** `200 OK`:

```json
{
  "status": "sync_started",
  "days_back": 90
}
```

**Response** `409 Conflict`:

```json
{
  "detail": "Sync task already running",
  "error_code": "conflict"
}
```

### GET /api/sync/status

Get current sync progress.

**Rate limit:** 30 requests/minute

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/sync/status"
```

**Response** `200 OK`:

```json
{
  "is_running": false,
  "progress": 100,
  "current_task": "Sync completed",
  "last_sync": "2026-02-12T07:00:00",
  "records_synced": 935000,
  "status": "completed",
  "phase": "done",
  "message": "Sync completed successfully",
  "started_at": "2026-02-12T06:48:00",
  "finished_at": "2026-02-12T07:00:00",
  "days_back": 365,
  "error": null
}
```

### GET /api/sync/config

Get current sync configuration.

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/sync/config"
```

**Response** `200 OK`:

```json
{
  "auto_sync_enabled": true,
  "auto_sync_schedule": ["07:00", "12:00", "16:00", "18:00"],
  "auto_sync_days": 90,
  "manual_sync_default_days": 90
}
```

### PUT /api/sync/config

Update sync configuration. All fields are optional; only provided fields are updated.

**Request:**

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"auto_sync_days": 180}' \
  "https://fltpulse.szfluent.cn/api/sync/config"
```

| Field                     | Type | Validation | Description                    |
|---------------------------|------|------------|--------------------------------|
| `auto_sync_enabled`       | bool | --         | Enable/disable auto sync       |
| `auto_sync_days`          | int  | 1-365      | Days to sync on auto schedule  |
| `manual_sync_default_days`| int  | 1-365      | Default days for manual sync   |

**Response** `200 OK`:

```json
{
  "status": "config_updated"
}
```

### GET /api/sync/history

Get recent sync history.

**Query parameters:**

| Parameter | Type | Default | Description                    |
|-----------|------|---------|--------------------------------|
| `limit`   | int  | `10`    | Number of history entries       |

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/sync/history?limit=5"
```

**Response** `200 OK`:

```json
[
  {
    "started_at": "2026-02-12T07:00:00",
    "finished_at": "2026-02-12T07:12:00",
    "status": "completed",
    "days_back": 365,
    "records_synced": 935000,
    "error_message": null
  }
]
```

---

## Cache Management

All cache endpoints require authentication.

### GET /api/cache/stats

Get cache statistics including hit rates, sizes, and query frequency data.

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/cache/stats"
```

**Response** `200 OK`:

```json
{
  "memory_cache": {
    "enabled": true,
    "size": 42,
    "max_size": 200,
    "hits": 150,
    "misses": 30,
    "hit_rate": 0.833
  },
  "query_stats": {
    "total_queries": 180,
    "total_unique_mtos": 42
  }
}
```

### POST /api/cache/clear

Clear the in-memory cache. Does not affect the SQLite cache.

**Rate limit:** 10 requests/minute

**Request:**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/cache/clear"
```

**Response** `200 OK`:

```json
{
  "status": "cleared",
  "entries_cleared": 42
}
```

### POST /api/cache/warm

Pre-load MTO data into the memory cache.

**Rate limit:** 5 requests/minute

**Query parameters:**

| Parameter  | Type | Default | Validation | Description                                  |
|------------|------|---------|------------|----------------------------------------------|
| `count`    | int  | `100`   | 1-500      | Number of MTOs to warm                       |
| `use_hot`  | bool | `false` | --         | Use query history (true) or recent synced (false) |

**Request:**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/cache/warm?count=50&use_hot=true"
```

**Response** `200 OK`:

```json
{
  "status": "completed",
  "warmed": 48,
  "failed": 2,
  "source": "query_history",
  "requested": 50
}
```

### DELETE /api/cache/{mto_number}

Invalidate a specific MTO from the memory cache.

**Request:**

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/cache/AK2510034"
```

**Response** `200 OK`:

```json
{
  "status": "invalidated",
  "mto_number": "AK2510034"
}
```

If the MTO was not in cache:

```json
{
  "status": "not_found",
  "mto_number": "AK2510034"
}
```

### POST /api/cache/reset-stats

Reset cache statistics counters.

**Request:**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/cache/reset-stats"
```

**Response** `200 OK`:

```json
{
  "status": "stats_reset"
}
```

### GET /api/cache/hot-mtos

Get the most frequently queried MTOs.

**Query parameters:**

| Parameter | Type | Default | Validation | Description                      |
|-----------|------|---------|------------|----------------------------------|
| `top_n`   | int  | `20`    | 1-100      | Number of hot MTOs to return     |

**Request:**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/cache/hot-mtos?top_n=10"
```

**Response** `200 OK`:

```json
{
  "hot_mtos": ["AK2510034", "AK2510035", "AK2510036"],
  "total_unique_mtos": 42,
  "total_queries": 180
}
```

---

## Chat (AI Assistant)

The chat feature uses DeepSeek LLM for conversational queries about MTO data and analytics.

### GET /api/chat/status

Check whether the chat feature is available. **No authentication required.**

**Request:**

```bash
curl "https://fltpulse.szfluent.cn/api/chat/status"
```

**Response** `200 OK` (enabled):

```json
{
  "available": true,
  "model": "deepseek-chat"
}
```

**Response** `200 OK` (disabled):

```json
{
  "available": false,
  "model": null
}
```

### POST /api/chat/stream

Stream a chat response using Server-Sent Events (SSE).

**Rate limit:** 20 requests/minute

**Request body** (JSON):

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "messages": [
      {"role": "user", "content": "AK2510034 fulfillment summary"}
    ],
    "mode": "mto",
    "mto_context": {"mto_number": "AK2510034", "children": [...]}
  }' \
  "https://fltpulse.szfluent.cn/api/chat/stream"
```

| Field         | Type   | Default | Validation       | Description                                  |
|---------------|--------|---------|------------------|----------------------------------------------|
| `messages`    | array  | (required) | --            | Chat message history (`role` + `content`)    |
| `mode`        | string | `"mto"` | `mto` or `analytics` | Chat mode                              |
| `mto_context` | object | `null`  | --               | Current MTO data for context (mto mode only) |

**SSE event types:**

| Event type   | Fields                        | Description                          |
|--------------|-------------------------------|--------------------------------------|
| `token`      | `content`                     | Streaming text token                 |
| `sql`        | `query`                       | Generated SQL (analytics mode)       |
| `sql_result` | `columns`, `rows`, `total_rows` | Query results (analytics mode)     |
| `error`      | `message`                     | Error message                        |
| `done`       | --                            | Stream complete                      |

**Example SSE stream:**

```
data: {"type": "token", "content": "The"}

data: {"type": "token", "content": " fulfillment"}

data: {"type": "token", "content": " rate is 95%."}

data: {"type": "done"}
```

**Response** `503 Service Unavailable`:

```json
{
  "detail": "Chat service not configured",
  "error_code": "service_unavailable"
}
```

---

## Health

### GET /health

Basic health check. **No authentication required.**

**Request:**

```bash
curl "https://fltpulse.szfluent.cn/health"
```

**Response** `200 OK`:

```json
{
  "status": "healthy"
}
```

---

## Error Handling

All API errors return a consistent JSON structure:

```json
{
  "detail": "Human-readable error message",
  "error_code": "MACHINE_READABLE_CODE"
}
```

### HTTP Status Codes

| Code | Meaning               | Typical cause                              |
|------|-----------------------|--------------------------------------------|
| 400  | Bad Request           | Invalid input, validation failure          |
| 401  | Unauthorized          | Missing or invalid Bearer token            |
| 404  | Not Found             | MTO number not found                       |
| 409  | Conflict              | Sync already running                       |
| 422  | Unprocessable Entity  | Request body validation error (FastAPI)     |
| 429  | Too Many Requests     | Rate limit exceeded                        |
| 500  | Internal Server Error | Unexpected server error                    |
| 503  | Service Unavailable   | Chat service not configured                |

### Error Codes

| Error Code             | HTTP Status | Description                         |
|------------------------|-------------|-------------------------------------|
| `unauthorized`         | 401         | Missing, expired, or invalid token  |
| `not_found`            | 404         | MTO number not found                |
| `bad_request`          | 400         | Invalid request                     |
| `validation_error`     | 422         | Input validation failure            |
| `conflict`             | 409         | Sync already in progress            |
| `rate_limited`         | 429         | Too many requests                   |
| `internal_error`       | 500         | Unexpected server error             |
| `erp_unavailable`      | 502         | Kingdee ERP connection failed       |
| `service_unavailable`  | 503         | Chat/DeepSeek not configured        |

### Validation Errors (422)

FastAPI returns detailed validation errors for request body/query issues:

```json
{
  "detail": [
    {
      "loc": ["body", "days_back"],
      "msg": "ensure this value is less than or equal to 365",
      "type": "value_error.number.not_le"
    }
  ],
  "error_code": "validation_error"
}
```

---

## Rate Limits

Rate limits are enforced per client IP address. When exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header.

| Endpoint                  | Limit           |
|---------------------------|-----------------|
| `POST /api/auth/token`    | 5/minute        |
| `GET /api/mto/{mto}`      | 30/minute       |
| `GET /api/mto/{mto}/related-orders` | 30/minute |
| `GET /api/search`         | 60/minute       |
| `GET /api/export/mto/{mto}` | 20/minute     |
| `POST /api/sync/trigger`  | 2/minute        |
| `GET /api/sync/status`    | 30/minute       |
| `POST /api/cache/clear`   | 10/minute       |
| `POST /api/cache/warm`    | 5/minute        |
| `POST /api/chat/stream`   | 20/minute       |

---

## CORS Configuration

Cross-Origin Resource Sharing is controlled by the `CORS_ALLOWED_ORIGINS` environment variable.

| Variable               | Default        | Description                                        |
|------------------------|----------------|----------------------------------------------------|
| `CORS_ALLOWED_ORIGINS` | (empty)        | Comma-separated list of allowed origins             |

**Examples:**

```bash
# Allow specific origins
CORS_ALLOWED_ORIGINS=https://example.com,https://app.example.com

# Empty value (default) = same-origin only (no CORS headers added)
CORS_ALLOWED_ORIGINS=
```

When configured, the server adds standard CORS headers (`Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`) to responses for the specified origins.

---

## Quick Start

Complete workflow from authentication to querying:

```bash
# 1. Get a token
TOKEN=$(curl -s -X POST https://fltpulse.szfluent.cn/api/auth/token \
  -d "username=admin&password=YOUR_PASSWORD" | jq -r '.access_token')

# 2. Search for an MTO
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/search?q=AK25&limit=5"

# 3. Get full MTO status
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/mto/AK2510034"

# 4. Export to CSV
curl -H "Authorization: Bearer $TOKEN" \
  -o "MTO_AK2510034.csv" \
  "https://fltpulse.szfluent.cn/api/export/mto/AK2510034"

# 5. Check sync status
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://fltpulse.szfluent.cn/api/sync/status"

# 6. Trigger a sync (90 days)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"days_back": 90}' \
  "https://fltpulse.szfluent.cn/api/sync/trigger"
```
