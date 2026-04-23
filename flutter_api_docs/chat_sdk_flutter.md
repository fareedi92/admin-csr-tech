# Chat SDK Flutter Guide

This file is only for building the visitor chat SDK in Flutter against the running `chat-widget-manager` backend.

## Runtime

- Service: `chat-widget-manager`
- Code: `/home/ubuntu/chat-widget-manager/app.py`
- Port: `5004`
- Base URL: `http://52.74.227.205:5004`

## Required inputs

Your Flutter SDK needs:

- `widgetKey`
- `visitorId`
- `domain`
- optional `userType`
- `sinceId` for polling

`visitorId` should be generated once and persisted locally, similar to:

```text
v_xxxxxxx
```

## Endpoints

### `POST /validate_widget`

Purpose:

- validate widget access
- load config
- detect current session mode

Request:

```json
{
  "widget_key": "BUSINESS_WIDGET_KEY",
  "domain": "example.com",
  "visitor_id": "v_abc123xyz"
}
```

Success response:

```json
{
  "valid": true,
  "business_name": "Business Name",
  "session_mode": "active_ai",
  "user_type": "buyer",
  "widget_config": {
    "widgetTitle": "Business Support",
    "welcomeMessage": "Hello! How can we help you today?",
    "csrResolvedMessage": "You are now connected back to the AI assistant.",
    "primaryColor": "#5B50E7",
    "apiUrl": "/api/chat",
    "pollUrl": "/api/chat/poll",
    "pollInterval": 3000,
    "externalCsrApiEndpoint": "http://52.74.227.205:5002"
  }
}
```

Errors:

- `400`: missing widget key or domain
- `403`: domain not authorized
- `404`: invalid widget key

### `POST /api/chat`

Purpose:

- send visitor message
- get AI reply
- or continue CSR-mode conversation

Request:

```json
{
  "message": "I need help with my booking",
  "widget_key": "BUSINESS_WIDGET_KEY",
  "visitor_id": "v_abc123xyz",
  "user_type": "buyer"
}
```

Normal AI response:

```json
{
  "output": "Hello, how can I assist you?",
  "mode": "active_ai",
  "session_id": 12,
  "user_msg_id": 44,
  "ai_msg_id": 45,
  "user_type": "buyer",
  "timestamp": "2026-04-16T10:10:10.000000Z"
}
```

Escalation response:

```json
{
  "output": "I am transferring you to a human agent.",
  "mode": "pending_csr",
  "user_msg_id": 44,
  "ai_msg_id": 45,
  "user_type": "buyer",
  "csr_relayed": true,
  "csr_assignment": {
    "chat_id": 101,
    "assigned_csr_id": 7,
    "assigned_csr_name": "Alice",
    "status": "assigned"
  }
}
```

Already in CSR mode:

```json
{
  "output": "",
  "mode": "active_csr",
  "user_msg_id": 50,
  "user_type": "buyer"
}
```

### `POST /api/chat/poll`

Purpose:

- fetch new messages
- detect latest mode

Request:

```json
{
  "visitor_id": "v_abc123xyz",
  "since_id": 45,
  "widget_key": "BUSINESS_WIDGET_KEY"
}
```

Response:

```json
{
  "messages": [
    {
      "id": 46,
      "content": "Hello, I am your support agent.",
      "sender": "csr",
      "timestamp": "2026-04-16T10:11:00.000000Z"
    }
  ],
  "session_status": "active_csr"
}
```

## Flutter state rules

- `active_ai`: show normal AI chat
- `pending_csr`: show waiting-for-agent state
- `active_csr`: show live-human state

Recommended polling:

- `/api/chat/poll` every `3000 ms`

## Minimal Flutter interface

```dart
abstract class VisitorChatSdk {
  Future<void> validateWidget({
    required String widgetKey,
    required String domain,
    required String visitorId,
  });

  Future<void> sendMessage({
    required String widgetKey,
    required String visitorId,
    required String message,
    String? userType,
  });

  Future<void> pollMessages({
    required String widgetKey,
    required String visitorId,
    required int sinceId,
  });
}
```

