# FLT Tickets Integration API

Server-to-server APIs for the FLT web backend so buyers and organizers can list tickets and update status on their own tickets.

**Do not put the API key in browser JavaScript.** Call these endpoints from the web backend after the buyer/organizer is logged in.

---

## Base URL

```
http://52.74.227.205:5002
```

---

## Authorization

Every request must send **one** of these headers.

### Option 1 (recommended)

| Header | Value |
|---|---|
| `X-Service-Secret` | value of `TICKETS_API_KEY` from the server `.env` |

### Option 2

| Header | Value |
|---|---|
| `Authorization` | `Bearer <TICKETS_API_KEY>` |

POST requests that send a body also need:

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |

In Postman: Body → **raw** → **JSON** (not Text).

### Auth errors

| Status | Body |
|---|---|
| `401` | `{"error": "Invalid or missing API credentials."}` |
| `503` | `{"error": "Ticket integration API is not configured."}` |

---

## Ticket object

All list and status responses use this ticket shape:

```json
{
  "id": 1,
  "ticket_number": "TCK_528324",
  "title": "Saman Rani — email issue",
  "description": "he is not getting email",
  "priority": "normal",
  "status": "in_progress",
  "origin": "csr",
  "is_admin_generated": false,
  "is_chat_linked": true,
  "chat_id": 1,
  "customer_external_user_id": "139006",
  "created_by": {
    "role": "csr",
    "name": "Talha21"
  },
  "assigned_tech": {
    "id": 1,
    "name": "Talha22",
    "specialty": "Hardware"
  },
  "created_at": "2026-09-02T12:15:03.441991Z",
  "updated_at": "2026-09-02T12:15:45.841279Z",
  "resolved_at": null
}
```

`origin` is `csr`, `admin`, or `tech`.

User-linked tickets are **CSR tickets created from an authenticated widget chat**. The widget **User ID** (example `139006`) is used, not the visitor id (`v_...`).

Admin/tech tickets have `customer_external_user_id: null` and `is_chat_linked: false`.

---

## 1. Get all tickets

Returns every ticket (CSR + admin + tech).

```http
GET /api/integration/tickets
```

### Headers

```http
X-Service-Secret: <TICKETS_API_KEY>
```

### Query params

| Param | Required | Default | Notes |
|---|---|---|---|
| `user_id` | no | — | Filter to one FLT widget user id |
| `customer_external_user_id` | no | — | Alias of `user_id` |
| `origin` | no | — | `csr`, `admin`, or `tech`. Ignored if `user_id` is set |
| `status` | no | — | Exact status name, e.g. `open` |
| `limit` | no | `100` | 1–300 |
| `offset` | no | `0` | Pagination start |

### Body

None.

### Example

```
GET http://52.74.227.205:5002/api/integration/tickets?limit=50&offset=0
```

### Success `200`

```json
{
  "tickets": [ { "...ticket object..." } ],
  "filters": {},
  "pagination": {
    "offset": 0,
    "limit": 50,
    "total": 1,
    "has_more": false
  }
}
```

---

## 2. Get tickets for one buyer / organizer

Use the widget **User ID**.

### 2a. Query param (same URL as get-all)

```
GET http://52.74.227.205:5002/api/integration/tickets?user_id=139006
```

### 2b. Path

```
GET http://52.74.227.205:5002/api/integration/tickets/users/139006
```

### Headers

```http
X-Service-Secret: <TICKETS_API_KEY>
```

### Query params (both forms)

| Param | Required | Default | Notes |
|---|---|---|---|
| `status` | no | — | e.g. `open`, `closed` |
| `limit` | no | `100` | 1–300 |
| `offset` | no | `0` | |

### Body

None.

### Success `200`

```json
{
  "tickets": [
    {
      "id": 1,
      "ticket_number": "TCK_528324",
      "title": "Saman Rani — email issue",
      "status": "in_progress",
      "origin": "csr",
      "customer_external_user_id": "139006",
      "is_chat_linked": true
    }
  ],
  "filters": {
    "customer_external_user_id": "139006"
  },
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 1,
    "has_more": false
  }
}
```

Only CSR chat-linked tickets for that user are returned. Admin-generated tickets are not included.

---

## 3. Get admin-generated tickets

Tickets created by an admin (not linked to a buyer chat).

```
GET http://52.74.227.205:5002/api/integration/tickets/admin-generated
```

### Headers

```http
X-Service-Secret: <TICKETS_API_KEY>
```

### Query params

| Param | Required | Default |
|---|---|---|
| `status` | no | — |
| `limit` | no | `100` |
| `offset` | no | `0` |

### Body

None.

### Success `200`

```json
{
  "tickets": [ { "...ticket object with origin admin..." } ],
  "filters": {
    "origin": "admin"
  },
  "pagination": {
    "offset": 0,
    "limit": 100,
    "total": 0,
    "has_more": false
  }
}
```

Same result as:

```
GET /api/integration/tickets?origin=admin
```

---

## 4. Update status on the user's own ticket

A buyer/organizer can change status only if the ticket is linked to **their** widget user id.

```
POST /api/integration/tickets/{ticket_ref}/status
```

`ticket_ref` can be:

- ticket number: `TCK_528324`
- numeric id: `1`

### Headers

```http
X-Service-Secret: <TICKETS_API_KEY>
Content-Type: application/json
```

### Path params

| Param | Required | Example |
|---|---|---|
| `ticket_ref` | yes | `TCK_528324` |

### Body

```json
{
  "user_id": "139006",
  "status": "closed",
  "notes": "Issue is resolved"
}
```

| Field | Required | Notes |
|---|---|---|
| `user_id` | yes | FLT widget user id. Alias: `customer_external_user_id`. Can also be sent as query `?user_id=139006` |
| `status` | yes | See allowed values below |
| `notes` | no | Stored on the status history. Default: `Status updated by user {user_id}.` |

### Allowed `status` values

| `status` | Meaning |
|---|---|
| `open` | Open |
| `in_progress` | In Progress |
| `waiting_parts` | Waiting for Parts |
| `resolved` | Resolved |
| `closed` | Closed |

Labels also work, e.g. `"Closed"`.

### Example

```
POST http://52.74.227.205:5002/api/integration/tickets/TCK_528324/status
```

```json
{
  "user_id": "139006",
  "status": "closed",
  "notes": "Issue is resolved"
}
```

### Success `200`

```json
{
  "success": true,
  "message": "Ticket status updated to Closed.",
  "ticket": {
    "id": 1,
    "ticket_number": "TCK_528324",
    "status": "closed",
    "customer_external_user_id": "139006",
    "resolved_at": "2026-09-02T12:40:00Z"
  }
}
```

If the ticket already has that status:

```json
{
  "success": true,
  "message": "Ticket already has status In Progress.",
  "ticket": { }
}
```

### Errors

| Status | When | Body |
|---|---|---|
| `400` | Missing `user_id` | `{"error": "user_id is required."}` |
| `400` | Missing `status` | `{"error": "status is required."}` |
| `400` | Unknown status | `{"error": "Invalid status: xyz"}` |
| `403` | Ticket is not this user's, or admin/tech ticket | `{"error": "This ticket does not belong to this user."}` |
| `404` | Unknown ticket number/id | `{"error": "Ticket not found."}` |

---

## Quick Postman collection

Use header `X-Service-Secret` = `<TICKETS_API_KEY>` on all of these.

| Name | Method | URL | Body |
|---|---|---|---|
| All tickets | GET | `http://52.74.227.205:5002/api/integration/tickets` | none |
| One user | GET | `http://52.74.227.205:5002/api/integration/tickets?user_id=139006` | none |
| One user (path) | GET | `http://52.74.227.205:5002/api/integration/tickets/users/139006` | none |
| Admin tickets | GET | `http://52.74.227.205:5002/api/integration/tickets/admin-generated` | none |
| Update own status | POST | `http://52.74.227.205:5002/api/integration/tickets/TCK_528324/status` | JSON below |

POST body:

```json
{
  "user_id": "139006",
  "status": "closed",
  "notes": "Issue is resolved"
}
```

POST must use Body → raw → **JSON**.

---

## Web backend usage

1. Authenticate the buyer/organizer in the FLT web app.
2. Read their FLT user id (the same id the widget shows, e.g. `139006`).
3. Call get-by-user with that id.
4. To change status, POST with that same `user_id`. The CSR app checks the ticket is linked to that user.

The CSR/tech/admin portal APIs (`/api/tickets`, cookie login) are separate and are not for buyer/organizer pages.
