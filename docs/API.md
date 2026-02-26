# Redline – REST API Reference

**Base URL:** `{APP_BASE_URL}/api/v1`
**Format:** `application/json`
**Authentication:** HTTP Basic Auth (dedicated `api_user` account required)
**Version:** 0.1b
**Interactive Docs:** `{APP_BASE_URL}/api/docs` (Swagger UI)

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [HTTP Status Codes](#2-http-status-codes)
3. [Rate Limiting](#3-rate-limiting)
4. [Error Format](#4-error-format)
5. [Devices](#5-devices)
6. [Defects](#6-defects)
7. [Events](#7-events)
8. [curl Examples](#8-curl-examples)

---

## 1. Authentication

All endpoints require **HTTP Basic Auth** with a dedicated **`api_user`** account.

```
Authorization: Basic <base64(username:password)>
```

> **Important:** Web-UI accounts (`admin`, `disponent`, `werkstatt`, `team_login`) are
> **not permitted** to use the API. They will receive `403 Forbidden`.
> Only accounts with `is_api_user=True` may authenticate.

| User | Type | Permissions |
|------|------|-------------|
| `api` | api_user | Full access to all endpoints |

**Default credentials** (change before going live!):

```bash
# List all devices
curl -u api:api2025 https://srv/api/v1/devices
```

> **Production note:** Always use HTTPS. Basic Auth credentials are only
> Base64-encoded, not encrypted at the transport level.
> Manage API users via **Admin → Benutzerverwaltung** → "API-Zugriff" checkbox.

Unauthenticated requests receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Redline API"
Content-Type: application/json

{"error": "Authentication required."}
```

Web-UI accounts receive:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"error": "API access requires a dedicated api_user account. Web-UI accounts (admin, disponent, werkstatt) cannot authenticate to the API."}
```

---

## 2. HTTP Status Codes

| Code | Meaning | Typical situation |
|------|---------|-------------------|
| `200` | OK | Successful GET / PATCH |
| `201` | Created | Successful POST |
| `204` | No Content | Successful DELETE (empty body) |
| `400` | Bad Request | Missing / invalid fields |
| `401` | Unauthorized | Missing or wrong credentials |
| `403` | Forbidden | Non-api_user account used; or non-admin on admin-only endpoint |
| `404` | Not Found | Unknown `device_id`, `defect_id`, etc. |
| `409` | Conflict | Duplicate `device_id`; defect already resolved |
| `429` | Too Many Requests | Rate limit exceeded |

---

## 3. Rate Limiting

| Scope | Limit |
|-------|-------|
| Login page (`POST /auth/login`) | 10 req / minute per IP |
| API (global default) | 200 req / hour, 50 req / minute per IP |

When exceeded the server returns `429 Too Many Requests` with an error body.

---

## 4. Error Format

All error responses use a consistent JSON envelope:

```json
{ "error": "Human-readable message." }
```

Validation errors (HTTP 400) additionally include per-field details:

```json
{
  "error": "Validation failed.",
  "fields": {
    "category":    "Required.",
    "description": "Required."
  }
}
```

---

## 5. Devices

### `GET /devices`

List all devices, optionally filtered by status.

#### Query Parameters

| Name | Type | Required | Values |
|------|------|----------|--------|
| `status` | string | No | `Verfügbar` · `Wartung` |

#### Response `200`

```json
[
  {
    "device_id":         "CAM-001",
    "name":              "Kamera Sony A7 IV",
    "description":       "Vollformatkamera, Body + 24-70 mm",
    "status":            "Verfügbar",
    "open_defect_count": 0,
    "created_at":        "2025-06-01T08:00:00.000000"
  }
]
```

---

### `POST /devices` _(admin only)_

Create a new device.

#### Request Body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `device_id` | string | **Yes** | Unique identifier, e.g. `CAM-001` |
| `name` | string | **Yes** | Human-readable label |
| `description` | string | No | Optional free text |

```json
{
  "device_id":   "CAM-001",
  "name":        "Kamera Sony A7 IV",
  "description": "Vollformatkamera, Body + 24-70 mm"
}
```

#### Responses

| Code | Reason |
|------|--------|
| `201` | Device created – returns device object |
| `400` | `device_id` or `name` missing |
| `409` | `device_id` already exists |

---

### `GET /devices/{device_id}`

Fetch a single device.

#### Responses

| Code | Reason |
|------|--------|
| `200` | Returns device object |
| `404` | Device not found |

---

### `PATCH /devices/{device_id}` _(admin only)_

Partial update – only included fields are changed.

#### Request Body (all optional)

| Field | Allowed Values |
|-------|----------------|
| `name` | Any non-empty string |
| `description` | Any string |
| `status` | `Verfügbar` · `Wartung` |

```json
{ "status": "Wartung" }
```

#### Responses

| Code | Reason |
|------|--------|
| `200` | Returns updated device object |
| `400` | Invalid `status` value |
| `404` | Device not found |

---

### `DELETE /devices/{device_id}` _(admin only)_

Delete a device **and cascade-delete all its defect records**.

#### Responses

| Code | Reason |
|------|--------|
| `204` | Deleted – empty body |
| `404` | Device not found |

---

### `GET /devices/{device_id}/qr` _(admin only)_

Download the QR-code PNG. The code encodes
`{APP_BASE_URL}/report/{device_id}`.

#### Response `200`

```
Content-Type: image/png
Content-Disposition: attachment; filename="qr_CAM-001.png"
<binary PNG data>
```

---

## 6. Defects

### `GET /defects`

List defects with filters and pagination.

#### Query Parameters

| Name | Type | Default | Notes |
|------|------|---------|-------|
| `status` | string | – | `Offen` · `Behoben` |
| `device_id` | string | – | Exact match on `device_id` |
| `event_name` | string | – | Case-insensitive partial match |
| `project_number` | string | – | Case-insensitive partial match |
| `page` | integer | `1` | Page number |
| `per_page` | integer | `50` | Items per page (max `200`) |

#### Response `200`

```json
{
  "items": [
    {
      "id":               42,
      "device_id":        "CAM-001",
      "device_name":      "Kamera Sony A7 IV",
      "category":         "Gehäuseschaden",
      "description":      "Linker Griff gebrochen.",
      "event_name":       "Sommerfestival 2025",
      "project_number":   "PRJ-2025-042",
      "status":           "Offen",
      "reporter":         "team_login",
      "created_at":       "2025-06-01T14:30:00.000000",
      "resolved_at":      null,
      "resolution_notes": ""
    }
  ],
  "total":    1,
  "page":     1,
  "per_page": 50,
  "pages":    1
}
```

---

### `POST /defects`

Report a new defect.

**Side-effects (all non-blocking):**
- Device `status` → `Wartung`
- Defect synced to FileMaker (`Defekte` layout)
- Email notification sent to workshop

#### Request Body

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `device_id` | string | **Yes** | Must exist |
| `category` | string | **Yes** | Must be a configured category |
| `description` | string | **Yes** | Free text |
| `event_name` | string | **Yes** | Free text |
| `project_number` | string | **Yes** | Free text |

**Default valid categories:**
`Mechanischer Schaden`, `Elektrischer Fehler`, `Softwareproblem`,
`Gehäuseschaden`, `Kabelproblem`, `Displayschaden`, `Akkuproblem`,
`Wasserschaden`, `Sonstiges`

```json
{
  "device_id":      "CAM-001",
  "category":       "Gehäuseschaden",
  "description":    "Linker Griff gebrochen, Kamera funktioniert.",
  "event_name":     "Sommerfestival 2025",
  "project_number": "PRJ-2025-042"
}
```

#### Responses

| Code | Reason |
|------|--------|
| `201` | Defect created – returns defect object |
| `400` | Validation error with `fields` map |
| `404` | Device not found |

---

### `GET /defects/{defect_id}`

Fetch a single defect by numeric ID.

#### Responses

| Code | Reason |
|------|--------|
| `200` | Returns defect object |
| `404` | Defect not found |

---

### `PATCH /defects/{defect_id}/resolve` _(admin only)_

Mark a defect as resolved.

**Side-effects:**
- `status` → `Behoben`, `resolved_at` timestamp set
- If **no open defects remain** for the device → device `status` → `Verfügbar`
- FileMaker device status updated

#### Request Body (optional)

| Field | Type | Notes |
|-------|------|-------|
| `resolution_notes` | string | How it was fixed |

```json
{ "resolution_notes": "Griff ersetzt und getestet – OK." }
```

#### Responses

| Code | Reason |
|------|--------|
| `200` | Returns updated defect object |
| `403` | Admin required |
| `404` | Defect not found |
| `409` | Defect already resolved |

---

## 7. Events

### `GET /events`

Return all distinct `(event_name, project_number)` pairs.

#### Response `200`

```json
[
  { "event_name": "Sommerfestival 2025", "project_number": "PRJ-2025-042" },
  { "event_name": "Wintergala 2025",     "project_number": "PRJ-2025-099" }
]
```

---

### `GET /events/{project_number}`

Return all defects for a project number.

#### Query Parameters

| Name | Type | Notes |
|------|------|-------|
| `event_name` | string | Optional exact filter |

#### Response `200`

```json
{
  "project_number": "PRJ-2025-042",
  "event_name":     "Sommerfestival 2025",
  "defect_count":   3,
  "defects":        [ ... ]
}
```

#### Responses

| Code | Reason |
|------|--------|
| `200` | Returns event defects object |
| `404` | No defects for this project number |

---

## 8. curl Examples

```bash
# All examples use the dedicated api_user account (api:api2025).
# Replace "api2025" with your production password.

# List all devices
curl -u api:api2025 https://srv/api/v1/devices

# List devices in maintenance
curl -u api:api2025 "https://srv/api/v1/devices?status=Wartung"

# Create a device
curl -u api:api2025 -X POST https://srv/api/v1/devices \
  -H "Content-Type: application/json" \
  -d '{"device_id":"CAM-001","name":"Kamera Sony A7 IV"}'

# Report a defect
curl -u api:api2025 -X POST https://srv/api/v1/defects \
  -H "Content-Type: application/json" \
  -d '{
    "device_id":"CAM-001",
    "category":"Gehäuseschaden",
    "description":"Linker Griff gebrochen.",
    "event_name":"Sommerfestival 2025",
    "project_number":"PRJ-2025-042"
  }'

# List open defects for an event
curl -u api:api2025 \
  "https://srv/api/v1/defects?status=Offen&project_number=PRJ-2025-042"

# Resolve defect
curl -u api:api2025 -X PATCH https://srv/api/v1/defects/42/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution_notes":"Griff ersetzt, getestet."}'

# Download QR code PNG
curl -u api:api2025 https://srv/api/v1/devices/CAM-001/qr -o qr_CAM-001.png

# Full event summary
curl -u api:api2025 https://srv/api/v1/events/PRJ-2025-042
```
