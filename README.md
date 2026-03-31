# CSR Workspace App

Flask app for a simple multi-CSR workspace that receives incoming handoffs from `QSTP_New`, auto-assigns them to CSRs, and lets every CSR see the queue while only the assigned CSR can open and reply to the chat.

## Main Flow

1. `QSTP_New` escalates a widget conversation to CSR.
2. It sends the transcript to this app through `POST /init`.
3. This app auto-assigns the chat to the lightest available CSR.
4. All logged-in CSRs can see the chat in the list.
5. Only the assigned CSR can open the transcript and reply.
6. New visitor messages arrive through `POST /send`.
7. When the assigned CSR resolves the chat, queued chats are rebalanced automatically.

## Database Schema

### `users`

- `id`
- `email`
- `password_hash`
- `display_name`
- `role`
- `is_active`
- `is_available`
- `max_concurrent_chats`
- `last_assigned_at`
- `created_at`

### `chat_conversations`

- `id`
- `external_chat_id`
- `customer_name`
- `customer_email`
- `subject`
- `priority`
- `status`
- `source`
- `reverted_reason`
- `last_customer_message`
- `assigned_csr_id`
- `assigned_at`
- `reverted_at`
- `last_activity_at`
- `resolved_at`
- `created_at`
- `updated_at`

### `chat_assignment_events`

- `id`
- `chat_id`
- `event_type`
- `from_csr_id`
- `to_csr_id`
- `acted_by_user_id`
- `notes`
- `created_at`

### `chat_messages`

- `id`
- `chat_id`
- `sender_type`
- `content`
- `created_at`

## Assignment Logic

- Incoming chats are assigned automatically from `/init`.
- The app checks all active and available `admin` and `csr` users.
- It counts each CSR's active chats.
- The next chat goes to the CSR with the lowest load.
- If loads tie, the chat goes to the CSR who has waited longest since the last assignment.
- If everyone is full, the chat stays queued until capacity opens.

## Access Rules

- Every logged-in CSR can see all chats in the list.
- Only the assigned CSR can open the transcript.
- Only the assigned CSR can reply.
- Admins can manually reassign chats, but the UI still keeps non-owned chats locked for normal CSR handling.

## Setup

### 1. Create a virtual environment

```bash
cd /home/ubuntu/csr_widget_app
python3 -m venv .venv
```

### 2. Install dependencies

```bash
./.venv/bin/pip install -r requirements.txt
```

### 3. Run the app

```bash
./.venv/bin/python app.py
```

The app runs on `http://localhost:5002`.

## Important Environment Variables

- `CENTRAL_API_URL`
  Default: `http://52.74.227.205:5003`

- `CSR_WIDGET_KEY`
  Required if you want CSR replies and resolve actions to relay back to the real QSTP customer widget.

Example:

```bash
export CENTRAL_API_URL="http://52.74.227.205:5003"
export CSR_WIDGET_KEY="your_real_widget_key"
./.venv/bin/python app.py
```

## Endpoints

- `GET /`
  CSR workspace UI

- `GET /health`
  Health check

- `POST /init`
  Receives a new QSTP handoff with transcript and auto-assigns it

- `POST /send`
  Receives new visitor messages after handoff

- `POST /cleanup`
  Best-effort external cleanup hook

- `GET /api/dashboard-data`
  Returns summaries, visible chats, and CSR workload

- `GET /api/chats/<id>/messages`
  Returns transcript only if the chat is assigned to the current CSR

- `POST /api/chats/<id>/reply`
  Assigned CSR reply

- `POST /api/chats/<id>/resolve`
  Resolve chat and rebalance queue

- `POST /api/chats/<id>/assign`
  Admin reassignment

- `POST /api/chats/rebalance`
  Admin queue rebalance

- `POST /api/csrs/<id>/settings`
  Admin CSR capacity and availability update

## Notes

- Existing `users.db` files are upgraded in place on startup.
- The first user becomes `admin` if no admin exists.
- Later signups become `csr`.
- If `CSR_WIDGET_KEY` is not configured, replies and resolves still work locally in the CSR workspace but they will not relay back to the live QSTP widget.
