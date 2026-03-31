from datetime import UTC, datetime, timedelta
from functools import wraps
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, func, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash


ACTIVE_CHAT_STATUSES = ("queued", "assigned", "in_progress")
RESOLVED_CHAT_STATUSES = ("resolved", "closed")
ASSIGNABLE_ROLES = ("admin", "csr")
DEFAULT_MAX_CONCURRENT_CHATS = 4
CSR_ONLINE_WINDOW_SECONDS = 60
CSR_PRESENCE_WRITE_INTERVAL_SECONDS = 15
CENTRAL_API_URL = os.environ.get("CENTRAL_API_URL", "http://52.74.227.205:5003").rstrip("/")
CSR_WIDGET_KEY = os.environ.get("CSR_WIDGET_KEY", "csr_aridian_52_74_227_205_demo").strip()
CSR_API_KEY = os.environ.get("CSR_API_KEY", "").strip()


app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "csr-widget-app-secret-key-2024"

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "instance", "users.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = 86400

db = SQLAlchemy(app)

CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                r"http://127\.0\.0\.1:\d+",
                r"http://localhost:\d+",
                r"https://.*\.vercel\.app",
                "https://flt-frontend-web-sigma.vercel.app",
                "http://52.74.227.205:5003",
            ],
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
        }
    },
)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def derive_display_name(email):
    local_part = (email or "").split("@")[0].replace(".", " ").replace("_", " ").strip()
    return local_part.title() or "CSR User"


def isoformat_or_none(value):
    return value.isoformat() if value else None


def get_request_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value, default):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def parse_timestamp(value):
    if not value:
        return utcnow()

    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    try:
        normalized = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    except ValueError:
        return utcnow()


def normalize_sender_type(value):
    normalized = (value or "").strip().lower()
    if normalized in {"csr", "agent", "support"}:
        return "csr"
    if normalized in {"ai", "assistant", "bot", "system"}:
        return "ai"
    return "user"


def post_json(url, payload, timeout=5):
    body = json.dumps(payload).encode("utf-8")
    request_obj = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request_obj, timeout=timeout) as response:
        response_text = response.read().decode("utf-8")
        return response.status, json.loads(response_text) if response_text else {}


def describe_http_error(exc):
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        return payload.get("message") or payload.get("error")
    except Exception:
        return None


def build_central_auth_payload():
    # Support both the live widget key and the legacy CSR dashboard key.
    if not CSR_WIDGET_KEY and not CSR_API_KEY:
        return {}

    auth_payload = {}
    relay_key = CSR_WIDGET_KEY or CSR_API_KEY
    if relay_key:
        auth_payload["widget_key"] = relay_key
        auth_payload["csr_key"] = relay_key

    if CSR_API_KEY:
        auth_payload["csr_key"] = CSR_API_KEY

    return auth_payload


# ─── Models ──────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120))
    role = db.Column(db.String(20), nullable=False, default="csr", index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    max_concurrent_chats = db.Column(db.Integer, nullable=False, default=DEFAULT_MAX_CONCURRENT_CHATS)
    last_assigned_at = db.Column(db.DateTime)
    last_seen_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    assigned_chats = db.relationship(
        "ChatConversation",
        foreign_keys="ChatConversation.assigned_csr_id",
        back_populates="assigned_csr",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class ChatConversation(db.Model):
    __tablename__ = "chat_conversations"

    id = db.Column(db.Integer, primary_key=True)
    external_chat_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    customer_name = db.Column(db.String(150), nullable=False)
    customer_email = db.Column(db.String(150))
    subject = db.Column(db.String(255))
    priority = db.Column(db.String(20), nullable=False, default="normal")
    status = db.Column(db.String(20), nullable=False, default="queued", index=True)
    source = db.Column(db.String(40), nullable=False, default="qstp_widget")
    reverted_reason = db.Column(db.Text)
    last_customer_message = db.Column(db.Text)
    assigned_csr_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    assigned_at = db.Column(db.DateTime)
    reverted_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_activity_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    assigned_csr = db.relationship("User", foreign_keys=[assigned_csr_id], back_populates="assigned_chats")
    assignment_events = db.relationship(
        "ChatAssignmentEvent",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="ChatAssignmentEvent.created_at.desc()",
    )
    messages = db.relationship(
        "ChatMessage",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
    )


class ChatAssignmentEvent(db.Model):
    __tablename__ = "chat_assignment_events"

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("chat_conversations.id"), nullable=False, index=True)
    event_type = db.Column(db.String(30), nullable=False, index=True)
    from_csr_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    to_csr_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    acted_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    chat = db.relationship("ChatConversation", back_populates="assignment_events")
    from_csr = db.relationship("User", foreign_keys=[from_csr_id])
    to_csr = db.relationship("User", foreign_keys=[to_csr_id])
    acted_by = db.relationship("User", foreign_keys=[acted_by_user_id])


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("chat_conversations.id"), nullable=False, index=True)
    sender_type = db.Column(db.String(20), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    chat = db.relationship("ChatConversation", back_populates="messages")


# ─── Auth Helpers ────────────────────────────────────────────
def build_unauthorized_response():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Authentication required."}), 401
    return redirect(url_for("login"))


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def get_online_cutoff(now=None):
    return (now or utcnow()) - timedelta(seconds=CSR_ONLINE_WINDOW_SECONDS)


def is_user_online(user, now=None):
    return bool(
        user
        and user.is_active
        and user.last_seen_at
        and user.last_seen_at >= get_online_cutoff(now)
    )


def touch_user_presence(user, force=False):
    if not user or not user.is_active:
        return

    now = utcnow()
    if force or not user.last_seen_at or (now - user.last_seen_at).total_seconds() >= CSR_PRESENCE_WRITE_INTERVAL_SECONDS:
        user.last_seen_at = now
        db.session.commit()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            session.clear()
            return build_unauthorized_response()
        touch_user_presence(user)
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user.role != "admin":
            return jsonify({"error": "Administrator access is required."}), 403
        return f(*args, **kwargs)

    return decorated_function


# ─── Assignment Helpers ──────────────────────────────────────
def get_support_user_rows(available_only=False, online_only=False):
    filters = [User.is_active.is_(True), User.role.in_(ASSIGNABLE_ROLES)]
    if available_only:
        filters.append(User.is_available.is_(True))
    if online_only:
        filters.append(User.last_seen_at.is_not(None))
        filters.append(User.last_seen_at >= get_online_cutoff())

    return (
        db.session.query(
            User,
            func.count(ChatConversation.id).label("active_chat_count"),
        )
        .outerjoin(
            ChatConversation,
            and_(
                ChatConversation.assigned_csr_id == User.id,
                ChatConversation.status.in_(ACTIVE_CHAT_STATUSES),
            ),
        )
        .filter(*filters)
        .group_by(User.id)
        .all()
    )


def pick_best_csr():
    eligible_rows = []
    for user, active_chat_count in get_support_user_rows(available_only=True, online_only=True):
        capacity = user.max_concurrent_chats or DEFAULT_MAX_CONCURRENT_CHATS
        if active_chat_count < capacity:
            eligible_rows.append((user, active_chat_count))

    if not eligible_rows:
        return None

    eligible_rows.sort(
        key=lambda row: (
            row[1],
            row[0].last_assigned_at or datetime.min,
            row[0].created_at or datetime.min,
            row[0].id,
        )
    )
    return eligible_rows[0][0]


def log_assignment_event(chat, event_type, notes=None, from_csr_id=None, to_csr_id=None, acted_by_user_id=None):
    db.session.add(
        ChatAssignmentEvent(
            chat=chat,
            event_type=event_type,
            notes=notes,
            from_csr_id=from_csr_id,
            to_csr_id=to_csr_id,
            acted_by_user_id=acted_by_user_id,
        )
    )


def assign_chat(chat, actor=None, preferred_csr=None, note=None):
    now = utcnow()
    previous_assignee_id = chat.assigned_csr_id
    target_user = preferred_csr or pick_best_csr()

    if target_user is None:
        chat.assigned_csr_id = None
        chat.assigned_at = None
        chat.status = "queued"
        chat.last_activity_at = now
        log_assignment_event(
            chat,
            "queued",
            notes=note or "Queued because all CSR capacities are currently full.",
            from_csr_id=previous_assignee_id,
            acted_by_user_id=actor.id if actor else None,
        )
        return None

    chat.assigned_csr_id = target_user.id
    chat.assigned_at = now
    chat.status = "assigned"
    chat.last_activity_at = now
    target_user.last_assigned_at = now

    event_type = "assigned" if previous_assignee_id in (None, target_user.id) else "reassigned"
    log_assignment_event(
        chat,
        event_type,
        notes=note or "Assigned automatically from incoming QSTP handoff.",
        from_csr_id=previous_assignee_id,
        to_csr_id=target_user.id,
        acted_by_user_id=actor.id if actor else None,
    )
    return target_user


def rebalance_queued_chats(actor=None):
    assigned_count = 0
    queued_chats = (
        ChatConversation.query.filter(
            ChatConversation.status == "queued",
            ChatConversation.assigned_csr_id.is_(None),
        )
        .order_by(ChatConversation.reverted_at.asc(), ChatConversation.id.asc())
        .all()
    )

    for chat in queued_chats:
        assignee = assign_chat(
            chat,
            actor=actor,
            note="Assigned from the waiting queue after capacity became available.",
        )
        if assignee:
            assigned_count += 1

    if assigned_count:
        db.session.commit()

    return assigned_count


# ─── Chat Helpers ────────────────────────────────────────────
def can_user_open_chat(user, chat):
    return bool(user and chat and chat.assigned_csr_id == user.id)


def can_user_reply_to_chat(user, chat):
    return bool(
        user
        and chat
        and chat.assigned_csr_id == user.id
        and chat.status in ACTIVE_CHAT_STATUSES
    )


def can_user_resolve_chat(user, chat):
    return bool(user and chat and (chat.assigned_csr_id == user.id or user.role == "admin"))


def append_chat_message(chat, sender_type, content, created_at=None):
    timestamp = created_at or utcnow()
    message = ChatMessage(
        chat=chat,
        sender_type=sender_type,
        content=content,
        created_at=timestamp,
    )
    db.session.add(message)
    chat.last_activity_at = timestamp
    if sender_type == "user":
        chat.last_customer_message = content
    return message


def get_chat_preview(chat):
    if chat.messages:
        return chat.messages[-1].content
    if chat.last_customer_message:
        return chat.last_customer_message
    if chat.reverted_reason:
        return chat.reverted_reason
    return "No messages yet."


def import_transcript(chat, transcript, reset_existing=False):
    if reset_existing:
        ChatMessage.query.filter_by(chat_id=chat.id).delete(synchronize_session=False)
        db.session.flush()

    existing_signatures = {
        (msg.sender_type, msg.content, isoformat_or_none(msg.created_at))
        for msg in chat.messages
    }

    for item in transcript or []:
        sender_type = normalize_sender_type(item.get("sender"))
        content = (item.get("content") or "").strip()
        if not content:
            continue

        timestamp = parse_timestamp(item.get("timestamp"))
        signature = (sender_type, content, isoformat_or_none(timestamp))
        if signature in existing_signatures:
            continue

        append_chat_message(chat, sender_type, content, created_at=timestamp)
        existing_signatures.add(signature)


def build_lock_reason(chat):
    if chat.assigned_csr:
        return f"Assigned to {chat.assigned_csr.display_name or chat.assigned_csr.email}."
    return "Waiting for a free CSR to become available."


def serialize_user(user):
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name or derive_display_name(user.email),
        "role": user.role,
        "is_active": bool(user.is_active),
        "is_available": bool(user.is_available),
        "is_online": is_user_online(user),
        "max_concurrent_chats": user.max_concurrent_chats or DEFAULT_MAX_CONCURRENT_CHATS,
        "last_assigned_at": isoformat_or_none(user.last_assigned_at),
        "last_seen_at": isoformat_or_none(user.last_seen_at),
        "created_at": isoformat_or_none(user.created_at),
    }


def serialize_support_user(user, active_chat_count):
    capacity = user.max_concurrent_chats or DEFAULT_MAX_CONCURRENT_CHATS
    load_pct = min(100, round((active_chat_count / capacity) * 100)) if capacity else 0
    payload = serialize_user(user)
    payload.update(
        {
            "active_chat_count": active_chat_count,
            "load_pct": load_pct,
        }
    )
    return payload


def serialize_message(message):
    return {
        "id": message.id,
        "sender_type": message.sender_type,
        "content": message.content,
        "created_at": isoformat_or_none(message.created_at),
    }


def serialize_chat(chat, current_user):
    assigned_name = chat.assigned_csr.display_name or chat.assigned_csr.email if chat.assigned_csr else None
    if chat.status in RESOLVED_CHAT_STATUSES:
        ownership_bucket = "resolved"
    elif current_user and chat.assigned_csr_id == current_user.id:
        ownership_bucket = "mine"
    elif chat.assigned_csr_id:
        ownership_bucket = "other"
    else:
        ownership_bucket = "queued"

    return {
        "id": chat.id,
        "visitor_id": chat.external_chat_id,
        "external_chat_id": chat.external_chat_id,
        "customer_name": chat.customer_name,
        "customer_email": chat.customer_email,
        "subject": chat.subject,
        "status": chat.status,
        "priority": chat.priority,
        "source": chat.source,
        "reverted_reason": chat.reverted_reason,
        "last_customer_message": chat.last_customer_message,
        "preview": get_chat_preview(chat),
        "assigned_csr_id": chat.assigned_csr_id,
        "assigned_csr": serialize_user(chat.assigned_csr) if chat.assigned_csr else None,
        "assigned_label": assigned_name,
        "assigned_at": isoformat_or_none(chat.assigned_at),
        "reverted_at": isoformat_or_none(chat.reverted_at),
        "last_activity_at": isoformat_or_none(chat.last_activity_at),
        "resolved_at": isoformat_or_none(chat.resolved_at),
        "message_count": len(chat.messages),
        "ownership_bucket": ownership_bucket,
        "is_active": chat.status in ACTIVE_CHAT_STATUSES,
        "is_resolved": chat.status in RESOLVED_CHAT_STATUSES,
        "can_open": can_user_open_chat(current_user, chat),
        "can_reply": can_user_reply_to_chat(current_user, chat),
        "can_resolve": bool(current_user and can_user_resolve_chat(current_user, chat) and chat.status in ACTIVE_CHAT_STATUSES),
        "is_mine": bool(current_user and chat.assigned_csr_id == current_user.id),
        "lock_reason": None if can_user_open_chat(current_user, chat) else build_lock_reason(chat),
    }


def build_dashboard_payload(current_user):
    chats = (
        ChatConversation.query.order_by(
            ChatConversation.last_activity_at.desc(),
            ChatConversation.reverted_at.desc(),
        )
        .limit(100)
        .all()
    )

    support_user_rows = sorted(
        get_support_user_rows(available_only=False),
        key=lambda row: (
            row[0].role != "admin",
            (row[0].display_name or row[0].email).lower(),
            row[0].id,
        ),
    )

    return {
        "current_user": serialize_user(current_user),
        "integration": {
            "central_api_url": CENTRAL_API_URL,
            "relay_enabled": bool(build_central_auth_payload()),
        },
        "summary": {
            "total_chats": ChatConversation.query.count(),
            "active_chats": ChatConversation.query.filter(ChatConversation.status.in_(ACTIVE_CHAT_STATUSES)).count(),
            "queued_chats": ChatConversation.query.filter_by(status="queued").count(),
            "resolved_chats": ChatConversation.query.filter(ChatConversation.status.in_(RESOLVED_CHAT_STATUSES)).count(),
            "my_chats": ChatConversation.query.filter(
                ChatConversation.assigned_csr_id == current_user.id,
                ChatConversation.status.in_(ACTIVE_CHAT_STATUSES),
            ).count(),
            "available_csrs": User.query.filter(
                User.is_active.is_(True),
                User.is_available.is_(True),
                User.role.in_(ASSIGNABLE_ROLES),
                User.last_seen_at.is_not(None),
                User.last_seen_at >= get_online_cutoff(),
            ).count(),
        },
        "csrs": [serialize_support_user(user, active_chat_count) for user, active_chat_count in support_user_rows],
        "chats": [serialize_chat(chat, current_user) for chat in chats],
    }


def relay_reply_to_central(chat, message):
    auth_payload = build_central_auth_payload()
    if not auth_payload:
        return {"skipped": True, "reason": "CSR relay key is not configured."}

    try:
        _, payload = post_json(
            f"{CENTRAL_API_URL}/api/csr/external_message",
            {
                "visitor_id": chat.external_chat_id,
                "message": message,
                **auth_payload,
            },
            timeout=5,
        )
        if payload.get("success"):
            return {"ok": True}
        return {"ok": False, "error": payload.get("message") or "Central API rejected the message."}
    except HTTPError as exc:
        return {"ok": False, "error": describe_http_error(exc) or f"Central API HTTP {exc.code}"}
    except URLError as exc:
        return {"ok": False, "error": str(exc.reason)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def relay_resolution_to_central(chat):
    auth_payload = build_central_auth_payload()
    if not auth_payload:
        return {"skipped": True, "reason": "CSR relay key is not configured."}

    transcript = [
        {
            "sender": message.sender_type,
            "content": message.content,
            "timestamp": isoformat_or_none(message.created_at),
        }
        for message in chat.messages
    ]
    summary = f"CSR resolved chat handled by {chat.assigned_csr.display_name if chat.assigned_csr else 'assigned CSR'}."

    try:
        _, payload = post_json(
            f"{CENTRAL_API_URL}/api/csr/transfer",
            {
                "visitor_id": chat.external_chat_id,
                "transcript": transcript,
                "summary": summary,
                **auth_payload,
            },
            timeout=8,
        )
        if payload.get("success"):
            return {"ok": True}
        return {"ok": False, "error": payload.get("message") or "Central API rejected the transfer."}
    except HTTPError as exc:
        return {"ok": False, "error": describe_http_error(exc) or f"Central API HTTP {exc.code}"}
    except URLError as exc:
        return {"ok": False, "error": str(exc.reason)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


def find_chat_by_visitor_id(visitor_id):
    return ChatConversation.query.filter_by(external_chat_id=visitor_id).first()


# ─── Schema Bootstrap ────────────────────────────────────────
def ensure_schema():
    os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)
    db.create_all()

    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    user_column_updates = {
        "display_name": "ALTER TABLE users ADD COLUMN display_name VARCHAR(120)",
        "role": "ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'csr'",
        "is_active": "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1",
        "is_available": "ALTER TABLE users ADD COLUMN is_available BOOLEAN DEFAULT 1",
        "max_concurrent_chats": (
            "ALTER TABLE users ADD COLUMN max_concurrent_chats "
            f"INTEGER DEFAULT {DEFAULT_MAX_CONCURRENT_CHATS}"
        ),
        "last_assigned_at": "ALTER TABLE users ADD COLUMN last_assigned_at DATETIME",
        "last_seen_at": "ALTER TABLE users ADD COLUMN last_seen_at DATETIME",
    }

    with db.engine.begin() as connection:
        for column_name, statement in user_column_updates.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))

        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chat_conversations_assigned_csr_id ON chat_conversations (assigned_csr_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chat_conversations_external_chat_id ON chat_conversations (external_chat_id)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_conversations_status ON chat_conversations (status)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chat_assignment_events_chat_id ON chat_assignment_events (chat_id)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_messages_chat_id ON chat_messages (chat_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_messages_sender_type ON chat_messages (sender_type)"))


def bootstrap_users():
    users = User.query.order_by(User.created_at.asc(), User.id.asc()).all()
    if not users:
        return

    if not any(user.role == "admin" for user in users):
        users[0].role = "admin"

    for user in users:
        if not user.display_name:
            user.display_name = derive_display_name(user.email)
        if user.role not in ASSIGNABLE_ROLES:
            user.role = "csr"
        if user.is_active is None:
            user.is_active = True
        if user.is_available is None:
            user.is_available = True
        if not user.max_concurrent_chats or user.max_concurrent_chats < 1:
            user.max_concurrent_chats = DEFAULT_MAX_CONCURRENT_CHATS

    db.session.commit()


# ─── Auth Routes ─────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    return render_template("csr_dashboard.html", user=get_current_user())


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template("signup.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return render_template("signup.html")

        role = "admin" if User.query.count() == 0 else "csr"
        user = User(
            email=email,
            display_name=derive_display_name(email),
            role=role,
            is_active=True,
            is_available=True,
            max_concurrent_chats=DEFAULT_MAX_CONCURRENT_CHATS,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        rebalance_queued_chats(actor=user)

        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        user.last_seen_at = utcnow()
        db.session.commit()
        session.permanent = True
        session["user_id"] = user.id
        session["user_email"] = user.email
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    current_user = get_current_user()
    if current_user:
        current_user.last_seen_at = None
        db.session.commit()
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/health")
def health():
    return {
        "status": "healthy",
        "service": "CSR Widget App",
        "relay_enabled": bool(build_central_auth_payload()),
    }, 200


# ─── External Handoff Endpoints ──────────────────────────────
@app.route("/init", methods=["POST"])
def external_init():
    payload = get_request_payload()
    visitor_id = (payload.get("visitor_id") or "").strip()
    transcript = payload.get("transcript") or []

    if not visitor_id:
        return jsonify({"success": False, "message": "visitor_id is required"}), 400

    now = utcnow()
    chat = find_chat_by_visitor_id(visitor_id)
    reset_existing = False

    if not chat:
        chat = ChatConversation(
            external_chat_id=visitor_id,
            customer_name=visitor_id,
            subject="Incoming QSTP widget handoff",
            source="qstp_widget",
            reverted_reason="AI escalated this conversation to a human CSR.",
            priority="normal",
            status="queued",
            reverted_at=now,
            last_activity_at=now,
        )
        db.session.add(chat)
        db.session.flush()
        log_assignment_event(chat, "reverted", notes="Incoming handoff from the QSTP widget.")
    else:
        was_resolved = chat.status in RESOLVED_CHAT_STATUSES
        if was_resolved:
            reset_existing = True
            chat.resolved_at = None
            chat.assigned_csr_id = None
            chat.assigned_at = None
            chat.status = "queued"
            log_assignment_event(chat, "reopened", notes="Existing visitor reopened by a new AI handoff.")

        chat.customer_name = chat.customer_name or visitor_id
        chat.subject = chat.subject or "Incoming QSTP widget handoff"
        chat.source = "qstp_widget"
        chat.reverted_reason = "AI escalated this conversation to a human CSR."
        chat.reverted_at = now
        chat.last_activity_at = now

    import_transcript(chat, transcript, reset_existing=reset_existing)

    latest_user_messages = [item.get("content") for item in transcript if normalize_sender_type(item.get("sender")) == "user"]
    if latest_user_messages:
        chat.last_customer_message = latest_user_messages[-1]

    if not chat.assigned_csr_id or chat.status in RESOLVED_CHAT_STATUSES or chat.status == "queued":
        chat.assigned_csr_id = None
        chat.assigned_at = None
        assign_chat(chat, note="Assigned automatically from an incoming QSTP widget handoff.")

    db.session.commit()

    assigned_csr_name = None
    if chat.assigned_csr:
        assigned_csr_name = chat.assigned_csr.display_name or chat.assigned_csr.email

    return jsonify(
        {
            "success": True,
            "chat_id": chat.id,
            "assigned_csr_id": chat.assigned_csr_id,
            "assigned_csr_name": assigned_csr_name,
            "status": chat.status,
        }
    )


@app.route("/send", methods=["POST"])
def external_send():
    payload = get_request_payload()
    visitor_id = (payload.get("visitor_id") or "").strip()
    content = (payload.get("content") or "").strip()

    if not visitor_id or not content:
        return jsonify({"success": False, "message": "visitor_id and content are required"}), 400

    chat = find_chat_by_visitor_id(visitor_id)
    if not chat:
        return jsonify({"success": False, "message": "Chat session not found"}), 404

    append_chat_message(chat, "user", content)
    if chat.status == "assigned":
        chat.status = "in_progress"
    db.session.commit()

    return jsonify({"success": True})


@app.route("/cleanup", methods=["POST"])
def external_cleanup():
    payload = get_request_payload()
    visitor_id = (payload.get("visitor_id") or "").strip()
    if not visitor_id:
        return jsonify({"success": False, "message": "visitor_id is required"}), 400

    chat = find_chat_by_visitor_id(visitor_id)
    if not chat:
        return jsonify({"success": True})

    if chat.status in ACTIVE_CHAT_STATUSES:
        chat.status = "resolved"
        chat.resolved_at = utcnow()
        chat.last_activity_at = utcnow()
        log_assignment_event(chat, "cleaned_up", notes="Chat cleaned up by external resolver.")
        db.session.commit()

    return jsonify({"success": True})


# ─── Dashboard API ───────────────────────────────────────────
@app.route("/api/dashboard-data")
@login_required
def dashboard_data():
    return jsonify(build_dashboard_payload(get_current_user()))


@app.route("/api/chats/<int:chat_id>/messages")
@login_required
def chat_messages(chat_id):
    current_user = get_current_user()
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    if not can_user_open_chat(current_user, chat):
        return jsonify(
            {
                "error": "You can only open chats assigned to you.",
                "assigned_csr": serialize_user(chat.assigned_csr) if chat.assigned_csr else None,
            }
        ), 403

    return jsonify(
        {
            "chat": serialize_chat(chat, current_user),
            "messages": [serialize_message(message) for message in chat.messages],
        }
    )


@app.route("/api/chats/<int:chat_id>/reply", methods=["POST"])
@login_required
def reply_to_chat(chat_id):
    current_user = get_current_user()
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    if not can_user_reply_to_chat(current_user, chat):
        if chat.status in RESOLVED_CHAT_STATUSES:
            return jsonify({"error": "This chat is already resolved and is now read-only."}), 400
        return jsonify({"error": "Only active chats assigned to you can be replied to."}), 403

    payload = get_request_payload()
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Reply message is required."}), 400

    relay_result = relay_reply_to_central(chat, message)
    if relay_result.get("ok") is False:
        return jsonify({"error": relay_result["error"]}), 502

    append_chat_message(chat, "csr", message)
    chat.status = "in_progress"
    log_assignment_event(
        chat,
        "responded",
        notes="Assigned CSR sent a reply.",
        to_csr_id=current_user.id,
        acted_by_user_id=current_user.id,
    )
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "relay": relay_result,
            "chat": serialize_chat(chat, current_user),
            "messages": [serialize_message(message_obj) for message_obj in chat.messages],
        }
    )


@app.route("/api/chats/<int:chat_id>/resolve", methods=["POST"])
@login_required
def resolve_chat(chat_id):
    current_user = get_current_user()
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    if not can_user_resolve_chat(current_user, chat):
        return jsonify({"error": "Only the assigned CSR or an admin can resolve this chat."}), 403

    if chat.status in RESOLVED_CHAT_STATUSES:
        return jsonify({"error": "This chat is already resolved."}), 400

    relay_result = relay_resolution_to_central(chat)
    if relay_result.get("ok") is False:
        return jsonify({"error": relay_result["error"]}), 502

    chat.status = "resolved"
    chat.resolved_at = utcnow()
    chat.last_activity_at = utcnow()
    log_assignment_event(
        chat,
        "resolved",
        notes="Chat resolved by CSR workspace.",
        to_csr_id=chat.assigned_csr_id,
        acted_by_user_id=current_user.id,
    )
    db.session.commit()
    rebalance_queued_chats(actor=current_user)

    return jsonify({"success": True, "relay": relay_result, "dashboard": build_dashboard_payload(current_user)})


@app.route("/api/chats/<int:chat_id>/assign", methods=["POST"])
@admin_required
def reassign_chat(chat_id):
    current_user = get_current_user()
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    payload = get_request_payload()
    csr_id = payload.get("csr_id")
    preferred_csr = None

    if csr_id not in (None, "", "auto"):
        preferred_csr = db.session.get(User, parse_int(csr_id, 0))
        if not preferred_csr or not preferred_csr.is_active or preferred_csr.role not in ASSIGNABLE_ROLES:
            return jsonify({"error": "Selected CSR is not eligible for assignments."}), 400

    assign_chat(
        chat,
        actor=current_user,
        preferred_csr=preferred_csr,
        note="Chat reassigned by an administrator.",
    )
    db.session.commit()

    return jsonify({"success": True, "dashboard": build_dashboard_payload(current_user)})


@app.route("/api/chats/rebalance", methods=["POST"])
@admin_required
def rebalance_chats():
    current_user = get_current_user()
    assigned_count = rebalance_queued_chats(actor=current_user)
    return jsonify({"success": True, "assigned_count": assigned_count, "dashboard": build_dashboard_payload(current_user)})


@app.route("/api/csrs/<int:user_id>/settings", methods=["POST"])
@admin_required
def update_csr_settings(user_id):
    current_user = get_current_user()
    csr_user = db.session.get(User, user_id)
    if not csr_user or csr_user.role not in ASSIGNABLE_ROLES:
        return jsonify({"error": "CSR not found."}), 404

    payload = get_request_payload()
    csr_user.is_available = parse_bool(payload.get("is_available"), default=csr_user.is_available)
    csr_user.max_concurrent_chats = parse_int(
        payload.get("max_concurrent_chats"),
        csr_user.max_concurrent_chats or DEFAULT_MAX_CONCURRENT_CHATS,
    )
    db.session.commit()
    rebalance_queued_chats(actor=current_user)

    return jsonify({"success": True, "dashboard": build_dashboard_payload(current_user)})


# ─── Startup ─────────────────────────────────────────────────
with app.app_context():
    ensure_schema()
    bootstrap_users()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
