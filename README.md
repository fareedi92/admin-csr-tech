# Chat Widget Manager

Standalone Flask app for managing the Frontline Ticketing chat widget layer:

- user login/register and multi-business management
- widget key / CSR key generation and embed scripts
- chat APIs for anonymous and authenticated visitors
- server-side token verification against FLT
- SQLite storage for businesses, sessions, messages, and API logs

## Run

```bash
cd /home/ubuntu/chat-widget-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Default port: `5004` (override with `PORT`).

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session secret | local dev fallback |
| `DATABASE_URL` | Widget DB | `instance/widget_manager.db` |
| `CSR_DATABASE_URL` | CSR mirror DB | `instance/widget_manager_csr.db` |
| `PORT` | HTTP port | `5004` |
| `DEFAULT_N8N_INSTANCE_ID` | n8n instance header | built-in demo id |
| `DEFAULT_CSR_API_URL` | CSR handoff base URL | empty |
| `CHATBOT_VERIFY_BASE_URL` | FLT verify host | `https://beta-tj1.frontlineticketing.com` |
| `CHATBOT_SERVICE_SECRET` | `X-Service-Secret` for FLT verify | stored service secret |

---

## Visitor authentication

The widget sends an `auth` object on:

- `POST /validate_widget`
- `POST /api/chat`
- `POST /api/chat/poll`

### Modes

| `auth.mode` | `auth.token` | Behavior |
|---|---|---|
| `anonymous` | ignored / `null` | Session stays anonymous |
| `authenticated` | required | Widget manager verifies the token with FLT, then stores user id/name/email on the chat session |

`mode` in chat API responses still means CSR routing status (`active_ai`, `pending_csr`, `active_csr`). Visitor identity uses `auth` / `auth_mode` to avoid that naming collision.

---

## FLT verify contract

Base URL: [https://beta-tj1.frontlineticketing.com/](https://beta-tj1.frontlineticketing.com/)

```http
POST /api/chatbot/verify
Content-Type: application/json
Accept: application/json
X-Service-Secret: <service-secret>

{
  "token": "<visitor-auth-token-from-host-app>"
}
```

Successful responses are accepted when either:

```json
{ "valid": true, "user": { "id": 123, "name": "Jane Doe", "email": "jane@example.com" } }
```

or:

```json
{ "authenticated": true, "user": { "id": "123", "name": "Jane Doe", "email": "jane@example.com" } }
```

Failed token / failed verification returns `401` from the widget APIs.

The service secret is kept server-side only (DB + env). It is never embedded in widget JavaScript.

---

## Example payloads

### 1) Anonymous validate

```json
{
  "widget_key": "YOUR_WIDGET_KEY",
  "domain": "beta-tj1.frontlineticketing.com",
  "visitor_id": "v_abc123",
  "auth": {
    "mode": "anonymous",
    "token": null
  }
}
```

Example response:

```json
{
  "valid": true,
  "business_name": "Frontline Customer Care",
  "session_mode": "active_ai",
  "user_type": null,
  "authentication": {
    "mode": "anonymous",
    "user": null
  },
  "widget_config": { "...": "..." }
}
```

### 2) Authenticated validate

```json
{
  "widget_key": "YOUR_WIDGET_KEY",
  "domain": "beta-tj1.frontlineticketing.com",
  "visitor_id": "v_abc123",
  "auth": {
    "mode": "authenticated",
    "token": "USER_SESSION_OR_API_TOKEN_FROM_FLT"
  }
}
```

Example response:

```json
{
  "valid": true,
  "authentication": {
    "mode": "authenticated",
    "user": {
      "id": "123",
      "name": "Jane Doe",
      "email": "jane@example.com",
      "metadata": {}
    }
  }
}
```

### 3) Anonymous chat message

```json
{
  "message": "I need help with my tickets",
  "prompt": "I need help with my tickets",
  "widget_key": "YOUR_WIDGET_KEY",
  "visitor_id": "v_abc123",
  "user_type": "buyer",
  "images": [],
  "auth": {
    "mode": "anonymous",
    "token": null
  }
}
```

### 4) Authenticated chat message

```json
{
  "message": "Where is my order?",
  "prompt": "Where is my order?",
  "widget_key": "YOUR_WIDGET_KEY",
  "visitor_id": "v_abc123",
  "user_type": "buyer",
  "images": [],
  "auth": {
    "mode": "authenticated",
    "token": "USER_SESSION_OR_API_TOKEN_FROM_FLT"
  }
}
```

Example response:

```json
{
  "output": "I can help with that.",
  "mode": "active_ai",
  "auth_mode": "authenticated",
  "session_id": 42,
  "user_msg_id": 100,
  "ai_msg_id": 101,
  "user_type": "buyer"
}
```

### 5) Poll

```json
{
  "visitor_id": "v_abc123",
  "since_id": 101,
  "widget_key": "YOUR_WIDGET_KEY",
  "auth": {
    "mode": "authenticated",
    "token": "USER_SESSION_OR_API_TOKEN_FROM_FLT"
  }
}
```

---

## Host-page embed (authenticated)

Configure auth **before** loading the widget script. The host site supplies the signed-in user token; the widget never invents one.

```html
<script>
window.AuthenticatedChatWidgetConfig = {
  auth: {
    mode: "authenticated",
    token: "USER_SESSION_OR_API_TOKEN_FROM_FLT"
  }
};
</script>
<script src="https://YOUR_WIDGET_MANAGER_HOST/embed/YOUR_WIDGET_KEY.js"></script>
```

Anonymous embed:

```html
<script>
window.AuthenticatedChatWidgetConfig = {
  auth: {
    mode: "anonymous",
    token: null
  }
};
</script>
<script src="https://YOUR_WIDGET_MANAGER_HOST/embed/YOUR_WIDGET_KEY.js"></script>
```

Optional runtime update:

```js
window.AuthenticatedChatWidget.setAuthentication({
  mode: "authenticated",
  token: "NEW_TOKEN"
});
// or
window.AuthenticatedChatWidget.setAuthentication({
  mode: "anonymous",
  token: null
});
```

---

## What gets stored on successful auth

On the widget-manager `chat_session` row:

- `auth_mode = authenticated`
- `authenticated_user_id`
- `authenticated_user_data` (JSON user payload)
- `auth_token_fingerprint` (SHA-256 of the token, never the raw token)

API logs redact `token` / secret fields as `[REDACTED]`.

When CSR escalation happens, the authenticated user object is forwarded to the CSR handoff payload as:

```json
{
  "visitor_id": "v_abc123",
  "user_type": "buyer",
  "authentication": {
    "mode": "authenticated",
    "user": {
      "id": "123",
      "name": "Jane Doe",
      "email": "jane@example.com"
    }
  }
}
```

---

## Business admin settings

In the business form:

1. **FLT chatbot verify base URL** → default `https://beta-tj1.frontlineticketing.com`
2. **Chatbot verification service secret** → `X-Service-Secret` value
3. **External CSR API endpoint** → separate CSR handoff base (not used for token verify)

---

## Tests

```bash
cd /home/ubuntu/chat-widget-manager
source .venv/bin/activate
python -m unittest -v test_widget_auth.py
```

Coverage includes:

- anonymous validation
- authenticated chat against mocked FLT `valid: true` responses
- invalid token rejection
- token redaction in logs

---

## Notes

- Bot messages still go through the fixed n8n webhook configured in `app.py`.
- Widget legitimacy (`widget_key` + authorized domain) is separate from visitor authentication (`auth.mode` + FLT token).
- For live authenticated QA you need a real FLT user token from the signed-in host app on [beta-tj1](https://beta-tj1.frontlineticketing.com/).
