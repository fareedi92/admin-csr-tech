# CSR SDK Flutter Guide

This file is only for building the standalone CSR SDK in Flutter against the running `chat-widget-manager` backend.

## Runtime

- Service: `chat-widget-manager`
- Code: `/home/ubuntu/chat-widget-manager/app.py`
- Port: `5004`
- Base URL: `http://52.74.227.205:5004`

## Required input

Your Flutter CSR SDK needs:

- `csrKey`

The standalone CSR widget APIs are key-based, not session-cookie-based.

## Endpoints

### `GET /api/v1/external/csr/chats?csr_key=...`

Purpose:

- fetch current CSR conversations

Response:

```json
{
  "chats": [
    {
      "id": 14,
      "visitor_id": "v_abc123xyz",
      "status": "pending_csr",
      "last_message": "I need help with my booking",
      "timestamp": "2026-04-16T10:00:05.000000Z",
      "summary": "AI escalated to human agent."
    }
  ]
}
```

### `GET /api/v1/external/csr/messages/<session_id>?csr_key=...`

Purpose:

- load transcript for one CSR conversation

Response:

```json
{
  "messages": [
    {
      "id": 1,
      "content": "I need help with my booking",
      "sender": "user",
      "timestamp": "2026-04-16T10:00:00.000000Z"
    },
    {
      "id": 2,
      "content": "I am transferring you to a human agent.",
      "sender": "ai",
      "timestamp": "2026-04-16T10:00:05.000000Z"
    }
  ],
  "session_status": "pending_csr"
}
```

### `POST /api/v1/external/csr/reply`

Purpose:

- send CSR message into the live conversation

Request:

```json
{
  "session_id": 14,
  "message": "Hello, I can help you with that.",
  "csr_key": "CSR_WIDGET_KEY"
}
```

Response:

```json
{
  "success": true,
  "message_id": 101
}
```

Backend effect:

- if session was `pending_csr`, it becomes `active_csr`
- message is stored in the main chat session
- message is mirrored in CSR conversation tables

### `POST /api/v1/external/csr/close`

Purpose:

- resolve CSR conversation and return visitor back to AI mode

Request:

```json
{
  "session_id": 14,
  "csr_key": "CSR_WIDGET_KEY"
}
```

Response:

```json
{
  "success": true,
  "message": "Chat resolved and returned to AI"
}
```

Backend effect:

- main session becomes `active_ai`
- CSR assignment is cleared
- a system AI message is appended
- mirrored CSR conversation becomes resolved

## Recommended polling

- chat list: every `5000 ms`
- selected transcript: every `3000 ms`

## Flutter state rules

- use chat list endpoint for sidebar/list state
- use messages endpoint for transcript state
- after reply, reload transcript
- after close, reload transcript and chat list

## Minimal Flutter interface

```dart
abstract class CsrChatSdk {
  Future<void> getChats({
    required String csrKey,
  });

  Future<void> getMessages({
    required String csrKey,
    required int sessionId,
  });

  Future<void> sendReply({
    required String csrKey,
    required int sessionId,
    required String message,
  });

  Future<void> closeChat({
    required String csrKey,
    required int sessionId,
  });
}
```

