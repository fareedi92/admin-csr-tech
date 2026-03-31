# CSR WIDGET APP - COMPLETE WORKFLOW DIAGRAM

## 📋 TABLE OF CONTENTS
1. Pages Overview
2. User Workflow (Registration → Chat Resolution)
3. Database Schema & Tables
4. Assignment Logic Tree
5. Chat Redirect Logic
6. Complete Process Flow Diagram

---

## 🖥️ PAGES IN THE APPLICATION

```
┌─────────────────────────────────────────────────────────────┐
│                    4 MAIN PAGES                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. SIGNUP PAGE (/signup)                                     │
│     ├─ Input: Email, Password, Confirm Password              │
│     ├─ Action: Create new CSR account                        │
│     └─ Logic: Auto-role first user as ADMIN, rest as CSR     │
│                                                               │
│  2. LOGIN PAGE (/login)                                       │
│     ├─ Input: Email, Password                                │
│     ├─ Action: Validate credentials                          │
│     └─ Session: Set user_id in session                       │
│                                                               │
│  3. DASHBOARD PAGE (/)                                        │
│     ├─ Requires: Login (Protected Route)                     │
│     ├─ Display: List of all chats with status                │
│     ├─ Data: CSR workload, queue stats                       │
│     └─ UI File: csr_dashboard.html                           │
│                                                               │
│  4. LOGOUT                                                    │
│     ├─ Action: Clear session                                 │
│     └─ Redirect: Back to login page                          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 👤 USER WORKFLOW: REGISTRATION → CHAT RESOLUTION

```
START: NEW CSR COMES TO SYSTEM
│
├─→ 1️⃣ CSR VISITS SIGNUP PAGE (/signup)
│   ├─ Enter Email
│   ├─ Enter Password (min 6 chars)
│   ├─ Confirm Password
│   └─ Click "Sign Up"
│       │
│       └─→ VALIDATION CHECKS:
│           ├─ ✓ All fields required
│           ├─ ✓ Passwords match
│           ├─ ✓ Email not already registered
│           └─ ✓ Password >= 6 characters
│
│           IF VALIDATION FAILS → Flash error & stay on signup
│           IF VALIDATION PASSES ↓
│
├─→ 2️⃣ ACCOUNT CREATION
│   ├─ Create User in Database:
│   │  TABLE: users
│   │  COLUMNS:
│   │  ├─ id (Primary Key)
│   │  ├─ email (Unique)
│   │  ├─ password_hash (encrypted)
│   │  ├─ display_name (derived from email)
│   │  ├─ role = "admin" (if first user) OR "csr" (if not)
│   │  ├─ is_active = TRUE
│   │  ├─ is_available = TRUE
│   │  ├─ max_concurrent_chats = 4 (default)
│   │  ├─ last_seen_at = NULL
│   │  └─ created_at = NOW()
│   │
│   └─ Redirect to LOGIN PAGE
│
├─→ 3️⃣ CSR LOGS IN (/login)
│   ├─ Enter email & password
│   ├─ VALIDATION:
│   │  ├─ Check if user exists
│   │  └─ Check if password matches
│   │
│   ├─ IF INVALID → Flash error & stay on login
│   └─ IF VALID ↓
│       ├─ Update user.last_seen_at = NOW()
│       ├─ Set session["user_id"] = user.id
│       ├─ Set session["user_email"] = user.email
│       └─ Redirect to DASHBOARD
│
├─→ 4️⃣ CSR SEES DASHBOARD (/)
│   ├─ PROTECTED ROUTE: Requires login
│   ├─ Load all chat conversations
│   ├─ Display for CURRENT CSR:
│   │  ├─ Queue Stats (total, assigned, resolved)
│   │  ├─ CSR Workload (how many active chats each CSR has)
│   │  ├─ Chat List showing:
│   │  │  ├─ Customer Name
│   │  │  ├─ Status (queued, assigned, in_progress, resolved)
│   │  │  ├─ Priority
│   │  │  ├─ Last Message Preview
│   │  │  ├─ Assigned CSR
│   │  │  └─ Time since last activity
│   │  │
│   │  └─ Each CSR can see ALL chats but:
│   │     ├─ Can OPEN only their assigned chats
│   │     ├─ Can REPLY only to their assigned chats
│   │     └─ (Admin can reassign & manage all)
│   │
│   └─ User presence tracked: last_seen_at updated
│
├─→ 5️⃣ CHAT ARRIVES FROM EXTERNAL SYSTEM (QSTP_New)
│   │
│   └─ EXTERNAL HANDOFF VIA POST /init
│       ├─ PAYLOAD FROM QSTP:
│       │  ├─ visitor_id (unique conversation ID)
│       │  ├─ transcript[] (array of messages)
│       │  │  └─ Each message: {sender, content, timestamp}
│       │  └─ OPTIONAL: customer_email, subject, priority
│       │
│       └─ CHAT CREATION LOGIC:
│           ├─ Check if chat with this visitor_id exists
│           │
│           ├─ IF NEW CHAT:
│           │  └─ Create ChatConversation in DB:
│           │     TABLE: chat_conversations
│           │     COLUMNS:
│           │     ├─ id (Primary Key)
│           │     ├─ external_chat_id = visitor_id (Unique)
│           │     ├─ customer_name = visitor_id
│           │     ├─ customer_email = NULL (optional)
│           │     ├─ subject = "Incoming QSTP widget handoff"
│           │     ├─ priority = "normal"
│           │     ├─ status = "queued"
│           │     ├─ source = "qstp_widget"
│           │     ├─ reverted_reason = "AI escalated..."
│           │     ├─ assigned_csr_id = NULL (pending assignment)
│           │     ├─ assigned_at = NULL
│           │     ├─ reverted_at = NOW()
│           │     ├─ last_activity_at = NOW()
│           │     ├─ resolved_at = NULL
│           │     ├─ last_customer_message = NULL
│           │     ├─ created_at = NOW()
│           │     └─ updated_at = NOW()
│           │
│           ├─ IF EXISTING CHAT:
│           │  ├─ If was resolved: reopen it & reset status to "queued"
│           │  ├─ Update fields with new data (if provided)
│           │  └─ Reset transcript if reopened
│           │
│           └─ IMPORT TRANSCRIPT:
│               └─ For each message in transcript:
│                   TABLE: chat_messages
│                   COLUMNS:
│                   ├─ id (Primary Key)
│                   ├─ chat_id = ChatConversation.id (Foreign Key)
│                   ├─ sender_type = "user" | "ai" | "csr"
│                   ├─ content = message text
│                   └─ created_at = timestamp
│
├─→ 6️⃣ AUTO-ASSIGNMENT LOGIC 🎯
│   │
│   └─ AFTER CHAT IS CREATED, SYSTEM RUNS: assign_chat()
│       │
│       ├─ STEP 1: Pick Best CSR
│       │  └─ pick_best_csr() runs this selection:
│       │
│       │     A. GET ALL ELIGIBLE CSRs:
│       │        └─ Criteria:
│       │           ├─ is_active = TRUE
│       │           ├─ role IN ("admin", "csr")
│       │           ├─ is_available = TRUE (if specified)
│       │           ├─ last_seen_at >= NOW() - 60 seconds (ONLINE_WINDOW)
│       │
│       │     B. FOR EACH ELIGIBLE CSR:
│       │        ├─ Count their ACTIVE chats:
│       │        │  └─ Active statuses: "queued", "assigned", "in_progress"
│       │        ├─ Calculate available capacity:
│       │        │  └─ capacity = max_concurrent_chats (default 4)
│       │        └─ If active_chats < capacity → ELIGIBLE
│       │
│       │     C. SORT ELIGIBLE CSRs BY PRIORITY:
│       │        └─ Order by:
│       │           ├─ 1️⃣ LOWEST active_chat_count (least loaded first)
│       │           ├─ 2️⃣ OLDEST last_assigned_at (hasn't had assignment in longest)
│       │           ├─ 3️⃣ OLDEST created_at (oldest user in system)
│       │           └─ 4️⃣ LOWEST id (tiebreaker)
│       │
│       │     D. PICK FIRST CSR:
│       │        └─ If no eligible CSR → stay QUEUED, don't assign
│       │
│       ├─ STEP 2: Log Assignment Event
│       │  TABLE: chat_assignment_events
│       │  COLUMNS:
│       │  ├─ id (Primary Key)
│       │  ├─ chat_id (Foreign Key → chat_conversations.id)
│       │  ├─ event_type = "assigned" | "reassigned" | "queued"
│       │  ├─ from_csr_id (who had it before, if reassign)
│       │  ├─ to_csr_id (CSR getting it now)
│       │  ├─ acted_by_user_id (who triggered, usually system)
│       │  ├─ notes = reason for assignment
│       │  └─ created_at = NOW()
│       │
│       └─ STEP 3: Update Chat Status
│           ├─ chat.assigned_csr_id = selected_csr.id
│           ├─ chat.assigned_at = NOW()
│           ├─ chat.status = "assigned"
│           ├─ selected_csr.last_assigned_at = NOW()
│           └─ Commit to database
│
├─→ 7️⃣ CSR OPENS ASSIGNED CHAT
│   │
│   └─ CLICK on chat in dashboard
│       ├─ Request: GET /api/chats/<chat_id>/messages
│       ├─ AUTHENTICATION: Must be logged in
│       │
│       ├─ PERMISSION CHECK:
│       │  └─ Verify: chat.assigned_csr_id == current_user.id
│       │     ├─ IF NOT ASSIGNED TO THEM:
│       │     │  └─ Return 403 Forbidden
│       │     └─ IF ASSIGNED TO THEM:
│       │        └─ Return full chat with all messages
│       │
│       └─ RESPONSE:
│           ├─ Serialize chat object (metadata)
│           ├─ Serialize all messages in chronological order
│           └─ Display in UI for CSR to read
│
├─→ 8️⃣ NEW CUSTOMER MESSAGE ARRIVES (EXTERNAL)
│   │
│   └─ EXTERNAL API CALL: POST /send
│       ├─ PAYLOAD:
│       │  ├─ visitor_id (which chat)
│       │  └─ content (message text)
│       │
│       ├─ LOGIC:
│       │  ├─ Find chat by external_chat_id = visitor_id
│       │  ├─ Append message:
│       │  │  └─ INSERT INTO chat_messages:
│       │  │     ├─ chat_id = found_chat.id
│       │  │     ├─ sender_type = "user" (from customer)
│       │  │     ├─ content = message text
│       │  │     └─ created_at = NOW()
│       │  │
│       │  └─ Update chat status:
│       │     ├─ If status = "assigned" → change to "in_progress"
│       │     └─ Update last_activity_at = NOW()
│       │
│       └─ RESULT: Dashboard refreshes, CSR sees new message
│
├─→ 9️⃣ CSR READS & REPLIES TO CHAT
│   │
│   └─ CLICK "Reply" in chat UI
│       ├─ Request: POST /api/chats/<chat_id>/reply
│       ├─ AUTHENTICATION: Must be logged in
│       │
│       ├─ PERMISSION CHECK:
│       │  ├─ chat.assigned_csr_id == current_user.id
│       │  ├─ chat.status IN ("queued", "assigned", "in_progress")
│       │  │  (not resolved or closed)
│       │  └─ IF CHECKS FAIL → Return 403 Forbidden
│       │
│       ├─ RELAY TO CENTRAL API (if configured):
│       │  └─ POST to CENTRAL_API_URL/path
│       │     ├─ Payload includes:
│       │     │  ├─ CSR_WIDGET_KEY (for auth)
│       │     │  ├─ chat ID
│       │     │  └─ message text
│       │     └─ Response: {"ok": true/false, "error": "..."}
│       │        └─ If relay fails → return 502 error to UI
│       │
│       ├─ APPEND CSR MESSAGE (if relay succeeded):
│       │  └─ INSERT INTO chat_messages:
│       │     ├─ chat_id = chat.id
│       │     ├─ sender_type = "csr"
│       │     ├─ content = reply message
│       │     └─ created_at = NOW()
│       │
│       ├─ UPDATE CHAT:
│       │  ├─ chat.status = "in_progress"
│       │  └─ chat.last_activity_at = NOW()
│       │
│       ├─ LOG EVENT:
│       │  └─ INSERT INTO chat_assignment_events:
│       │     ├─ event_type = "responded"
│       │     ├─ to_csr_id = current_user.id
│       │     ├─ notes = "Assigned CSR sent a reply"
│       │     └─ created_at = NOW()
│       │
│       └─ RETURN: Updated chat & all messages to CSR
│
├─→ 🔟 CSR RESOLVES CHAT
│   │
│   └─ CLICK "Resolve" in chat UI
│       ├─ Request: POST /api/chats/<chat_id>/resolve
│       ├─ AUTHENTICATION: Must be logged in
│       │
│       ├─ PERMISSION CHECK:
│       │  ├─ Assigned CSR OR Admin can resolve
│       │  ├─ chat.status NOT IN ("resolved", "closed")
│       │  └─ IF CHECKS FAIL → Return 403/400 error
│       │
│       ├─ RELAY TO CENTRAL API (if configured):
│       │  └─ POST to CENTRAL_API_URL/resolve_path
│       │     ├─ Payload: chat info, resolution signal
│       │     └─ Response: {"ok": true/false, "error": "..."}
│       │        └─ If fails → return 502 error
│       │
│       ├─ UPDATE CHAT STATUS:
│       │  ├─ chat.status = "resolved"
│       │  ├─ chat.resolved_at = NOW()
│       │  └─ chat.last_activity_at = NOW()
│       │
│       ├─ LOG RESOLUTION EVENT:
│       │  └─ INSERT INTO chat_assignment_events:
│       │     ├─ event_type = "resolved"
│       │     ├─ to_csr_id = chat.assigned_csr_id
│       │     ├─ acted_by_user_id = current_user.id
│       │     ├─ notes = "Chat resolved by CSR workspace"
│       │     └─ created_at = NOW()
│       │
│       ├─ 🔄 REBALANCE QUEUED CHATS:
│       │  └─ rebalance_queued_chats() is called:
│       │     ├─ Find all chats with:
│       │     │  ├─ status = "queued"
│       │     │  └─ assigned_csr_id = NULL
│       │     ├─ FOR EACH queued chat (ordered by reverted_at):
│       │     │  └─ Try to assign using pick_best_csr()
│       │     │     └─ Now that this CSR resolved a chat,
│       │     │        they might have capacity for a queued chat
│       │     └─ Count how many were assigned
│       │
│       └─ RETURN: Success, updated dashboard to CSR
│
└─→ END: Chat is resolved
```

---

## 💾 DATABASE SCHEMA & TABLES

### Table: `users`
```
┌─────────────────────────────────────────────────────────┐
│ TABLE: users                                            │
├─────────────────────────────────────────────────────────┤
│ Column Name         │ Type      │ Constraints           │
├─────────────────────┼───────────┼───────────────────────┤
│ id                  │ INTEGER   │ PRIMARY KEY, AUTO_INC │
│ email               │ STRING    │ UNIQUE, NOT NULL      │
│ password_hash       │ STRING    │ NOT NULL              │
│ display_name        │ STRING    │ (derived from email)  │
│ role                │ STRING    │ "admin" | "csr"       │
│ is_active           │ BOOLEAN   │ default TRUE          │
│ is_available        │ BOOLEAN   │ default TRUE          │
│ max_concurrent_chats│ INTEGER   │ default 4             │
│ last_assigned_at    │ DATETIME  │ (for load balancing)  │
│ last_seen_at        │ DATETIME  │ (presence tracking)   │
│ created_at          │ DATETIME  │ DEFAULT CURRENT_TIME  │
│ updated_at          │ DATETIME  │ ON UPDATE             │
└─────────────────────────────────────────────────────────┘

KEY USAGE:
├─ Role-based: role determines admin vs CSR permissions
├─ Availability: is_available controls assignment eligibility
├─ Capacity: max_concurrent_chats limits active chat count
├─ Load Balancing: last_assigned_at breaks ties in assignment
└─ Presence: last_seen_at tracks who's online (window: 60 sec)
```

### Table: `chat_conversations`
```
┌─────────────────────────────────────────────────────────┐
│ TABLE: chat_conversations                               │
├─────────────────────────────────────────────────────────┤
│ Column Name         │ Type      │ Constraints           │
├─────────────────────┼───────────┼───────────────────────┤
│ id                  │ INTEGER   │ PRIMARY KEY, AUTO_INC │
│ external_chat_id    │ STRING    │ UNIQUE, NOT NULL      │
│                     │           │ (visitor_id from QSTP)│
│ customer_name       │ STRING    │ NOT NULL              │
│ customer_email      │ STRING    │ (optional)            │
│ subject             │ STRING    │ (optional)            │
│ priority            │ STRING    │ "normal" | "high"     │
│ status              │ STRING    │ INDEX (for queries)   │
│                     │           │ "queued"              │
│                     │           │ "assigned"            │
│                     │           │ "in_progress"         │
│                     │           │ "resolved"            │
│                     │           │ "closed"              │
│ source              │ STRING    │ "qstp_widget"         │
│ reverted_reason     │ TEXT      │ Why AI escalated      │
│ last_customer_msg   │ TEXT      │ Cache of last msg     │
│ assigned_csr_id     │ INTEGER   │ FK → users.id         │
│                     │           │ NULL if queued        │
│ assigned_at         │ DATETIME  │ When assigned         │
│ reverted_at         │ DATETIME  │ When AI escalated     │
│ last_activity_at    │ DATETIME  │ Last msg/action       │
│ resolved_at         │ DATETIME  │ When CSR resolved     │
│ created_at          │ DATETIME  │ Chat creation time    │
│ updated_at          │ DATETIME  │ Last update time      │
└─────────────────────────────────────────────────────────┘

STATUS FLOW:
"queued" → "assigned" → "in_progress" → "resolved"
    ↑                                         │
    └─────── (rebalance when resolved) ──────┘

ACTIVE STATUSES: "queued", "assigned", "in_progress"
RESOLVED STATUSES: "resolved", "closed"
```

### Table: `chat_messages`
```
┌─────────────────────────────────────────────────────────┐
│ TABLE: chat_messages                                    │
├─────────────────────────────────────────────────────────┤
│ Column Name         │ Type      │ Constraints           │
├─────────────────────┼───────────┼───────────────────────┤
│ id                  │ INTEGER   │ PRIMARY KEY, AUTO_INC │
│ chat_id             │ INTEGER   │ FK → chat_convs.id    │
│ sender_type         │ STRING    │ INDEX (for filtering) │
│                     │           │ "user" (customer)     │
│                     │           │ "ai" (from AI system) │
│                     │           │ "csr" (support agent) │
│ content             │ TEXT      │ The message body      │
│ created_at          │ DATETIME  │ Message timestamp     │
└─────────────────────────────────────────────────────────┘

ORDERING: Retrieved chronologically (created_at ASC)
IMPORT: Transcript imported on chat creation
APPEND: New messages appended from /send and /reply
```

### Table: `chat_assignment_events`
```
┌─────────────────────────────────────────────────────────┐
│ TABLE: chat_assignment_events                           │
├─────────────────────────────────────────────────────────┤
│ Column Name         │ Type      │ Constraints           │
├─────────────────────┼───────────┼───────────────────────┤
│ id                  │ INTEGER   │ PRIMARY KEY, AUTO_INC │
│ chat_id             │ INTEGER   │ FK → chat_convs.id    │
│ event_type          │ STRING    │ INDEX (audit trail)   │
│                     │           │ "assigned"            │
│                     │           │ "reassigned"          │
│                     │           │ "queued"              │
│                     │           │ "responded"           │
│                     │           │ "resolved"            │
│                     │           │ "reopened"            │
│                     │           │ "reverted"            │
│                     │           │ "cleaned_up"          │
│ from_csr_id         │ INTEGER   │ FK → users.id         │
│                     │           │ (previous owner, NULL)│
│ to_csr_id           │ INTEGER   │ FK → users.id         │
│                     │           │ (new owner, NULL)     │
│ acted_by_user_id    │ INTEGER   │ FK → users.id         │
│                     │           │ (who triggered event) │
│ notes               │ TEXT      │ Reason / context      │
│ created_at          │ DATETIME  │ Event timestamp       │
└─────────────────────────────────────────────────────────┘

AUDIT: Provides full history of chat lifecycle
ORDERED: By created_at DESC (newest first)
```

---

## 🎯 ASSIGNMENT LOGIC TREE

```
CHAT ARRIVES VIA /init
│
└─ NEED TO ASSIGN?
   │
   ├─ YES: if chat.assigned_csr_id is NULL or status is queued
   │
   └──→ GET ELIGIBLE CSRs
       │
       └─ FILTERS:
          ├─ is_active = TRUE
          ├─ role IN ("admin", "csr")
          ├─ (optional) is_available = TRUE
          ├─ (optional) last_seen_at >= NOW() - 60 sec (ONLINE)
          └─ COUNT(active_chats) < max_concurrent_chats

             WHERE active_chats = chats with status IN
                   ("queued", "assigned", "in_progress")

       │
       └─ ELIGIBLE CSRs FOUND?
          │
          ├─ NO → Keep chat status = "queued"
          │        assigned_csr_id = NULL
          │        (wait for capacity)
          │
          └─ YES → PICK BEST CSR (lowest load)
             │
             └─ SORT by:
                ├─ 1. ACTIVE_CHAT_COUNT (ascending)
                │    Example: CSR A has 2, CSR B has 3 → Pick A
                │
                ├─ 2. LAST_ASSIGNED_AT (ascending)
                │    If tied on count: Who waited longest
                │    Example: A last got chat at 10:00, B at 10:05 → Pick A
                │
                ├─ 3. CREATED_AT (ascending)
                │    If tied on time: Who was hired first
                │
                └─ 4. ID (ascending)
                   Tiebreaker: lower ID wins

       │
       └─ ASSIGN SELECTED CSR
          ├─ Update chat:
          │  ├─ assigned_csr_id = selected_csr.id
          │  ├─ assigned_at = NOW()
          │  └─ status = "assigned"
          │
          ├─ Update CSR:
          │  └─ last_assigned_at = NOW()
          │
          └─ Log assignment event
             └─ event_type = "assigned" (or "reassigned")


EXAMPLE SCENARIO:
─────────────────
CSR Database:
┌─────────────────────────────────────────────────────────┐
│ ID  │ Email      │ Active │ Available │ Online? │ Load   │
├─────┼────────────┼────────┼───────────┼─────────┼────────┤
│ 1   │ alice@...  │ Yes    │ Yes       │ Yes     │ 2 chats│
│ 2   │ bob@...    │ Yes    │ No        │ Yes     │ 1 chat │
│ 3   │ carol@...  │ Yes    │ Yes       │ No      │ 0 chats│
│ 4   │ dave@...   │ No     │ Yes       │ Yes     │ 1 chat │
└─────┴────────────┴────────┴───────────┴─────────┴────────┘

RESULT:
├─ Bob is NOT assigned: is_available = NO
├─ Carol is NOT assigned: is_available = YES but NOT ONLINE
├─ Dave is NOT assigned: is_active = NO
├─ Alice is SELECTED (only eligible candidate)
│  └─ Even though Carol has lower load, she's offline
└─ Chat assigned to Alice (ID=1)
```

---

## 🔄 CHAT REDIRECT & REBALANCE LOGIC

```
CHAT STATUS TRANSITIONS:

                    ┌─ NEW CHAT ARRIVES ─┐
                    │                    │
              /init endpoint             /send (messages)
                    │                    │
                    ▼                    ▼
            ┌──────────────────────────────────────┐
            │  "queued"                            │
            │  (waiting for CSR availability)      │
            │  assigned_csr_id = NULL              │
            └──────────────────────────────────────┘
                    │
                    │ assign_chat()
                    │ (CSR has capacity)
                    ▼
            ┌──────────────────────────────────────┐
            │  "assigned"                          │
            │  (assigned to a CSR, waiting to open)│
            │  assigned_csr_id = CSR.id            │
            │  assigned_at = NOW()                 │
            └──────────────────────────────────────┘
                    │
         ┌──────────┤
         │          │
         │          │ CSR opens & /send (new message)
         │          │ changes status to in_progress
         │          │
         ▼          ▼
            ┌──────────────────────────────────────┐
            │  "in_progress"                       │
            │  (CSR actively handling)              │
            │  assigned_csr_id = CSR.id            │
            └──────────────────────────────────────┘
                    │
                    │ /reply (/resolve endpoint)
                    │
                    ▼
            ┌──────────────────────────────────────┐
            │  "resolved"                          │
            │  (CSR marked as complete)            │
            │  resolved_at = NOW()                 │
            └──────────────────────────────────────┘
                    │
                    │ REBALANCE_QUEUED_CHATS()
                    │
                    └──→ Try to assign any "queued" chats
                        if the CSR has freed up capacity


EXTERNAL CLEANUP (/cleanup endpoint):
└─ If chat is in ACTIVE_CHAT_STATUSES
   └─ Force status = "resolved"
   └─ Update resolved_at = NOW()
   └─ Log "cleaned_up" event


CHAT REOPENS:
└─ If /init receives visitor_id for a RESOLVED chat
   └─ Reset status = "queued"
   └─ Clear assigned_csr_id = NULL
   └─ Reset resolved_at = NULL
   └─ Log "reopened" event
   └─ Assign to best available CSR again
```

---

## 📊 COMPLETE PROCESS FLOW DIAGRAM

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                      CSR WIDGET APP FLOW                          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

EXTERNAL SYSTEM                         CSR WIDGET APP              DATABASE
(QSTP_New)                              (Flask Server)              (SQLite)
│                                       │                           │
│                                       │◄──── App Start ────       │
│                                       │      ensure_schema()      │
│                                       │      bootstrap_users()    │
│                                       │                           │
│  ┌─ User 1: SIGNUP ───────────────────►/signup (GET)             │
│  │                                   │                           │
│  │  email=alice@csr.com              │──────────────────────────►│ INSERT
│  │  password=secret123               │ Create user (role=admin)  │ users
│  │  confirm=secret123                │                           │
│  │                                   │◄──────────────────────────│
│  │                                   │ redirect to /login        │
│  │                                   │                           │
│  └─ User 1: LOGIN ───────────────────►/login (POST)              │
│     alice@csr.com / secret123        │                           │
│                                      │ Check password ───────────►│ SELECT
│                                      │                           │ users
│                                      │◄──────────────────────────│
│                                      │ Set session[user_id] = 1  │
│                                      │ Update last_seen_at ──────►│ UPDATE
│                                      │ redirect to /              │ users
│  ┌─ User 1: DASHBOARD ──────────────►/ (GET)                     │
│  │ (protected by @login_required)   │ Load csr_dashboard.html   │
│  │                                   │ Build dashboard payload ──►│ SELECT
│  │                                   │ (chats, CSRs, stats)      │ chats,
│  │                                   │                           │ users
│  │                                   │◄──────────────────────────│
│  │                                   │ Render HTML w/ data       │
│  │                                   │ Display chat list         │
│  │                                   │                           │
│  │  [Alice sees: "No chats yet"]     │                           │
│  │                                   │                           │
│  │  (Another CSR joins later...)     │                           │
│  │                                   │                           │
│  └─────────────────────────────────────────────────────────────────
│
│
│  ╔════════════════════════════════════════════════════════════════╗
│  ║ EXTERNAL QSTP WIDGET SENDS CHAT HANDOFF                        ║
│  ╚════════════════════════════════════════════════════════════════╝
│
├──────────────────────────────────────►/init (POST)                │
│  {                                    │                           │
│    "visitor_id": "v_12345",           │ Parse request             │
│    "transcript": [                    │ Find_chat_by_visitor_id() │
│      {                                │                           │
│        "sender": "user",              │ Chat NOT found ────────────►│ INSERT
│        "content": "Hello, help!",     │ Create chat               │ chat_
│        "timestamp": "2026-03-31T..." │ external_chat_id=visitor  │ convs
│      },                               │ status="queued"           │
│      {                                │ assigned_csr_id=NULL      │
│        "sender": "ai",                │                           │◄──────
│        "content": "Let me escalate",   │                           │
│        "timestamp": "2026-03-31T..."   │                           │
│      }                                │ Import transcript ────────►│ INSERT
│    ]                                  │ For each msg:             │ chat_
│  }                                    │ ├─ INSERT chat_messages   │ mesgs
│                                       │                           │◄──────
│                                       │ assign_chat() ────────────►│ SELECT
│                                       │ pick_best_csr() calls:    │ users
│                                       │ ├─ get_support_user_rows()│
│                                       │ ├─ Filter by criteria     │
│                                       │ └─ Sort by load, then by  │
│                                       │    last_assigned_at       │
│                                       │                           │◄──────
│                                       │                           │
│                                       │ Selected CSR = Alice (1)  │
│                                       │ UPDATE chat:              │──────►│ UPDATE
│                                       │ ├─ assigned_csr_id = 1   │ chat_
│                                       │ ├─ assigned_at = NOW()    │ convs
│                                       │ └─ status = "assigned"    │
│                                       │                           │◄──────
│                                       │ INSERT assignment event ──►│ INSERT
│                                       │                           │ chat_
│                                       │ {                         │ assign
│                                       │   chat_id: 1,             │ _evts
│                                       │   event_type: "assigned", │
│                                       │   to_csr_id: 1,           │
│                                       │   notes: "..."            │
│                                       │ }                         │
│                                       │                           │◄──────
│                                       │                           │
│                                       │◄────── Response ──────────│
│                                       │ {                         │
│                                       │   "success": true,        │
│                                       │   "chat_id": 1,           │
│                                       │   "assigned_csr_id": 1,   │
│                                       │   "assigned_csr_name":"...",
│                                       │   "status": "assigned"    │
│                                       │ }                         │
│                                       │                           │
├──────────────────────────────────────────────────────────────────────
│
│  ╔════════════════════════════════════════════════════════════════╗
│  ║ CSR SEES CHAT IN DASHBOARD & OPENS IT                          ║
│  ╚════════════════════════════════════════════════════════════════╝
│
│  [Alice sees chat in dashboard]       │                           │
│  [Clicks to open chat]                ►/api/chats/1/messages     │
│                                       │ (logged in as Alice)      │
│                                       │                           │
│                                       │ Permission check:         │
│                                       │ chat.assigned_csr_id==1 ──►│ SELECT
│                                       │ ✓ Permission granted      │ chats
│                                       │                           │◄──────
│                                       │ Serialize chat & msgs ────►│ SELECT
│                                       │                           │ chat_
│                                       │                           │ mesgs
│                                       │                           │◄──────
│                                       │                           │
│                                       │ Return transcript to UI   │
│                                       │ [UI displays conversation]│
│                                       │                           │
├──────────────────────────────────────────────────────────────────────
│
│  ╔════════════════════════════════════════════════════════════════╗
│  ║ CUSTOMER SENDS NEW MESSAGE (EXTERNAL QSTP)                     ║
│  ╚════════════════════════════════════════════════════════════════╝
│
├──────────────────────────────────────►/send (POST)                │
│  {                                    │ visitor_id = v_12345      │
│    "visitor_id": "v_12345",           │ content = "Are you there?"│
│    "content": "Are you there?"        │                           │
│  }                                    │ find_chat() ──────────────►│ SELECT
│                                       │                           │ chats
│                                       │◄──────────────────────────│
│                                       │ Found chat_id = 1         │
│                                       │                           │
│                                       │ append_chat_message() ────►│ INSERT
│                                       │ {                         │ chat_
│                                       │   chat_id: 1,             │ mesgs
│                                       │   sender_type: "user",    │
│                                       │   content: "..."          │
│                                       │ }                         │
│                                       │                           │◄──────
│                                       │ Update chat.status:       │
│                                       │ if "assigned"→"in_prog" ──►│ UPDATE
│                                       │                           │ chat_
│                                       │                           │ convs
│                                       │                           │◄──────
│                                       │ Return {"success": true}  │
│                                       │                           │
│  [Alice's dashboard refreshes]        │                           │
│  [She sees new message indicator]     │                           │
│                                       │                           │
├──────────────────────────────────────────────────────────────────────
│
│  ╔════════════════════════════════════════════════════════════════╗
│  ║ CSR REPLIES TO CUSTOMER                                        ║
│  ╚════════════════════════════════════════════════════════════════╝
│
│  [Alice reads message & clicks Reply] │                           │
│  [Composes: "Hello! How can I help?"] ►/api/chats/1/reply        │
│                                       │ (logged in as Alice)      │
│                                       │                           │
│                                       │ Permission check: ───────►│ SELECT
│                                       │ - Assigned to Alice (✓)   │ chats
│                                       │ - Active status (✓)       │◄──────
│                                       │                           │
│                                       │ Relay to Central API ─────►(External)
│                                       │ POST to CENTRAL_API_URL   │(HTTP)
│                                       │ with CSR_WIDGET_KEY       │
│                                       │ [Central confirms receipt]│
│                                       │◄─────────────────────────
│                                       │ Response: {"ok": true}    │
│                                       │                           │
│                                       │ append_chat_message() ────►│ INSERT
│                                       │ {                         │ chat_
│                                       │   chat_id: 1,             │ mesgs
│                                       │   sender_type: "csr",     │
│                                       │   content: "Hello!..."    │
│                                       │ }                         │
│                                       │                           │◄──────
│                                       │ Update chat.status ───────►│ UPDATE
│                                       │ = "in_progress"           │ chat_
│                                       │                           │ convs
│                                       │ INSERT event ─────────────►│ INSERT
│                                       │ event_type: "responded"   │ chat_
│                                       │                           │ assign
│                                       │                           │ _evts
│                                       │                           │◄──────
│                                       │                           │
│                                       │ Return updated chat+msgs  │
│                                       │                           │
│  [Message shows as sent]              │                           │
│                                       │                           │
├──────────────────────────────────────────────────────────────────────
│
│  ╔════════════════════════════════════════════════════════════════╗
│  ║ CSR RESOLVES CHAT (CONVERSATION COMPLETE)                      ║
│  ╚════════════════════════════════════════════════════════════════╝
│
│  [Alice clicks "Resolve Chat"]        ►/api/chats/1/resolve      │
│                                       │ (logged in as Alice)      │
│                                       │                           │
│                                       │ Permission check: ───────►│ SELECT
│                                       │ - Assigned or Admin (✓)   │ chats
│                                       │ - Not resolved yet (✓)    │◄──────
│                                       │                           │
│                                       │ Relay to Central API ─────►(External)
│                                       │ POST to resolve endpoint   │(HTTP)
│                                       │ [Central marks as done]   │
│                                       │◄─────────────────────────
│                                       │ Response: {"ok": true}    │
│                                       │                           │
│                                       │ Update chat status ───────►│ UPDATE
│                                       │ = "resolved"              │ chat_
│                                       │ resolved_at = NOW()       │ convs
│                                       │                           │◄──────
│                                       │                           │
│                                       │ INSERT event ─────────────►│ INSERT
│                                       │ event_type: "resolved"    │ chat_
│                                       │                           │ assign
│                                       │                           │ _evts
│                                       │                           │◄──────
│                                       │                           │
│                                       │ rebalance_queued_chats()  │
│                                       │ Find all chats with:      │
│                                       │ - status = "queued"       │──────►│ SELECT
│                                       │ - assigned_csr_id = NULL  │ chats
│                                       │                           │◄──────
│                                       │ For each queued chat:     │
│                                       │ - Try assign again ───────►│ SELECT
│                                       │ - Alice now has capacity! │ users
│                                       │                           │◄──────
│                                       │ If any assigned: ─────────►│ UPDATE
│                                       │ UPDATE chats, INSERT evts │ chat_
│                                       │                           │ convs
│                                       │                           │ INSERT
│                                       │                           │ chat_
│                                       │                           │ assign
│                                       │                           │ _evts
│                                       │                           │◄──────
│                                       │                           │
│                                       │ Return success + updated  │
│                                       │ dashboard                 │
│                                       │                           │
│  [Chat moves to "Resolved"]           │                           │
│  [Alice's load decreases]             │                           │
│  [Queued chats auto-assigned]         │                           │
│                                       │                           │
└──────────────────────────────────────────────────────────────────────

```

---

## 🔐 PERMISSION RULES SUMMARY

```
┌────────────────────────────────────────────────────────────┐
│                    PERMISSION MATRIX                        │
├────────────────────────────────────────────────────────────┤
│ Action              │ CSR  │ Admin │ Requirement            │
├─────────────────────┼──────┼───────┼────────────────────────┤
│ View Dashboard      │ ✓    │ ✓     │ Must be logged in      │
│ View Chat List      │ ✓    │ ✓     │ Logged in              │
│ Open Own Chat       │ ✓    │ ✓     │ Assigned to them       │
│ Open Others' Chat   │ ✗    │ ✗     │ Cannot open unassigned │
│ Reply to Chat       │ ✓    │ ✓     │ Assigned + Active      │
│ Resolve Chat        │ ✓    │ ✓     │ Assigned or Admin      │
│ Reassign Chat       │ ✗    │ ✓     │ Admin only             │
│ Rebalance Queue     │ ✗    │ ✓     │ Admin only             │
│ Update CSR Settings │ ✗    │ ✓     │ Admin only             │
│ Auto-Assignment     │ -    │ -     │ System (no user needed)│
└────────────────────┴──────┴───────┴────────────────────────┘
```

---

## 📝 ROUTE ENDPOINT SUMMARY

```
┌────────────────────────────────────────────────────────────┐
│           PUBLIC & PROTECTED ENDPOINTS                      │
├────────────────────────────────────────────────────────────┤
│ Endpoint                    │ Method │ Protected │ Purpose  │
├─────────────────────────────┼────────┼───────────┼──────────┤
│ /                           │ GET    │ Yes       │ Dashboard│
│ /signup                     │ GET    │ No        │ Signup   │
│ /signup                     │ POST   │ No        │ Create   │
│ /login                      │ GET    │ No        │ Login    │
│ /login                      │ POST   │ No        │ Auth     │
│ /logout                     │ GET    │ Yes       │ Logout   │
│ /health                     │ GET    │ No        │ Health   │
│ /init                       │ POST   │ No        │ Chat in  │
│ /send                       │ POST   │ No        │ Message  │
│ /cleanup                    │ POST   │ No        │ Cleanup  │
│ /api/dashboard-data         │ GET    │ Yes       │ Data     │
│ /api/chats/<id>/messages    │ GET    │ Yes       │ Transcript
│ /api/chats/<id>/reply       │ POST   │ Yes       │ Reply    │
│ /api/chats/<id>/resolve     │ POST   │ Yes       │ Resolve  │
│ /api/chats/<id>/assign      │ POST   │ Admin     │ Reassign │
│ /api/chats/rebalance        │ POST   │ Admin     │ Rebalance│
│ /api/csrs/<id>/settings     │ POST   │ Admin     │ Settings │
└─────────────────────────────┴────────┴───────────┴──────────┘

Protected = Requires login (@login_required decorator)
Admin = Requires admin role (@admin_required decorator)
```

---

## 🔧 KEY FUNCTIONS & THEIR ROLES

```
AUTHENTICATION:
├─ get_current_user()        → Get logged-in user from session
├─ login_required()          → Decorator for protected routes
└─ admin_required()          → Decorator for admin-only routes

PRESENCE TRACKING:
├─ touch_user_presence()     → Update last_seen_at (every 15 sec)
├─ is_user_online()          → Check if user was seen in last 60 sec
└─ get_online_cutoff()       → Calculate online window boundary

ASSIGNMENT:
├─ pick_best_csr()           → Select CSR with lowest load
├─ get_support_user_rows()   → Get all available CSRs + their load
├─ assign_chat()             → Assign or reassign a chat
└─ rebalance_queued_chats()  → Assign waiting chats to free CSRs

CHAT OPERATIONS:
├─ find_chat_by_visitor_id() → Lookup chat by external ID
├─ append_chat_message()     → Add message to chat
├─ import_transcript()       → Bulk import initial messages
├─ get_chat_preview()        → Get last message preview
├─ can_user_open_chat()      → Check permission to view
├─ can_user_reply_to_chat()  → Check permission to reply
└─ can_user_resolve_chat()   → Check permission to resolve

RELAYING:
├─ relay_reply_to_central()  → Send CSR reply to QSTP
└─ relay_resolution_to_central() → Signal chat resolved to QSTP

SERIALIZATION:
├─ serialize_user()          → Convert User to JSON
├─ serialize_message()       → Convert ChatMessage to JSON
├─ serialize_chat()          → Convert ChatConversation to JSON
├─ build_dashboard_payload() → Build complete UI data
└─ serialize_support_user()  → Serialize with workload info
```

---

## 🎬 END-TO-END LIFECYCLE SUMMARY

```
┌─────────────────────────────────────────────────────────────┐
│              COMPLETE CHAT LIFECYCLE                         │
├─────────────────────────────────────────────────────────────┤
│ Stage          │ Action                 │ Status Transition │
├────────────────┼────────────────────────┼──────────────────┤
│ 0. Setup       │ CSRs sign up & log in  │ (not a chat)     │
│                │                        │                  │
│ 1. Arrival     │ External /init sends   │ NULL →           │
│                │ chat + transcript      │ "queued"         │
│                │                        │                  │
│ 2. Assignment  │ System picks best CSR  │ "queued" →       │
│                │ based on load          │ "assigned"       │
│                │                        │                  │
│ 3. Discovery   │ Assigned CSR opens     │ (no change,      │
│                │ chat in dashboard      │  visible now)    │
│                │                        │                  │
│ 4. Activity    │ External /send or /api │ "assigned" →     │
│                │ /reply updates chat    │ "in_progress"    │
│                │                        │                  │
│ 5. Resolution  │ CSR clicks resolve     │ "in_progress" → │
│                │ endpoint or external   │ "resolved"      │
│                │ /cleanup called        │                  │
│                │                        │                  │
│ 6. Rebalance   │ System tries to assign │ (may assign      │
│                │ queued chats to freed  │ queued chats)    │
│                │ CSR capacity           │                  │
│                │                        │                  │
│ 7. Potential   │ If same visitor comes  │ "resolved" →     │
│    Reopen      │ back via /init again   │ "queued" again   │
│                │                        │                  │
└────────────────┴────────────────────────┴──────────────────┘
```

---

## 📞 SUMMARY

**4 Pages:**
1. **Signup** - New CSR registration
2. **Login** - CSR authentication
3. **Dashboard** - Main workspace with chat list
4. **Logout** - Session termination

**4 Database Tables:**
1. **users** - CSR accounts & availability
2. **chat_conversations** - Chat metadata & status
3. **chat_messages** - Message transcript
4. **chat_assignment_events** - Audit trail of lifecycle

**3 Main Status States:**
- **Queued** - Waiting for CSR capacity
- **Assigned/In Progress** - CSR handling
- **Resolved** - Complete

**Core Logic:**
- CSR receives chats from external QSTP system
- System auto-assigns based on load (least busy CSR)
- Assigned CSR can view & reply
- Once resolved, queues are rebalanced
- Full audit trail maintained
