from datetime import UTC, datetime, timedelta
from functools import wraps
from html import escape
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, func, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash


ACTIVE_CHAT_STATUSES = ("queued", "assigned", "in_progress")
RESOLVED_CHAT_STATUSES = ("resolved", "closed")
ASSIGNABLE_ROLES = ("csr",)
DEFAULT_MAX_CONCURRENT_CHATS = 4
CSR_ONLINE_WINDOW_SECONDS = 60
CSR_PRESENCE_WRITE_INTERVAL_SECONDS = 15
CENTRAL_API_URL = os.environ.get("CENTRAL_API_URL", "http://52.74.227.205:5003").rstrip("/")
CSR_WIDGET_KEY = os.environ.get("CSR_WIDGET_KEY", "csr_aridian_52_74_227_205_demo").strip()
CSR_API_KEY = os.environ.get("CSR_API_KEY", "").strip()


app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "csr-widget-app-secret-key-2024"

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, "instance")
INTEGRATION_CONFIG_PATH = os.path.join(instance_dir, "integration_settings.json")
CSR_DASHBOARD_APP_PATH = os.path.join(basedir, "static", "csr-dashboard-app.html")
DEFAULT_CSR_WIDGET_BASE_URL = os.environ.get("CSR_WIDGET_BASE_URL", "http://52.74.227.205:5004").rstrip("/")
DEFAULT_CSR_SCRIPT_PATH = "/widget-assets/csr-dashboard-widget.js"
DEFAULT_CSR_CONTAINER_ID = "csr-console"
DEFAULT_CSR_DASHBOARD_TITLE = "Frontline Customer Care CSR Widget"
DEFAULT_CSR_WIDGET_TITLE = "FLT CSR"
DEFAULT_CSR_PRIMARY_COLOR = "#2563EB"
KNOWLEDGE_BASE_UPDATER_URL = os.environ.get(
    "KNOWLEDGE_BASE_UPDATER_URL",
    "https://aidevv.3utilities.com/form/f03ca103-dda0-49bc-9bd8-821e3e62e9c7",
).strip()
DEFAULT_CHAT_LIST_POLL = 5000
DEFAULT_MESSAGE_POLL = 3000
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


def normalize_role(value, default="csr"):
    normalized = (value or default or "csr").strip().lower()
    return normalized if normalized in {"admin", "csr"} else default


def dashboard_endpoint_for(user_or_role):
    role = user_or_role if isinstance(user_or_role, str) else getattr(user_or_role, "role", "csr")
    return "admin_dashboard" if normalize_role(role) == "admin" else "csr_dashboard"


def auth_context(role):
    normalized_role = normalize_role(role)
    is_admin = normalized_role == "admin"
    return {
        "auth_role": normalized_role,
        "role_label": "Admin" if is_admin else "CSR",
        "auth_title": f"{'Administrator' if is_admin else 'CSR'} Portal",
        "switch_login_url": url_for("csr_login" if is_admin else "admin_login"),
        "switch_signup_url": url_for("csr_signup" if is_admin else "admin_signup"),
        "alternate_role_label": "CSR" if is_admin else "Admin",
    }


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


def normalize_url(value, default=""):
    raw = (value or default or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return default
    if not parsed.netloc and not parsed.path:
        return default
    return raw.rstrip("/")


def normalize_script_path(value):
    raw = (value or DEFAULT_CSR_SCRIPT_PATH).strip()
    if not raw:
        return DEFAULT_CSR_SCRIPT_PATH
    if raw.startswith(("http://", "https://")):
        return raw
    return raw if raw.startswith("/") else f"/{raw}"


def normalize_script_src(value, base_url):
    raw = (value or "").strip()
    if raw.startswith(("http://", "https://")):
        return raw

    normalized_path = normalize_script_path(raw or DEFAULT_CSR_SCRIPT_PATH)
    normalized_base_url = normalize_url(base_url, DEFAULT_CSR_WIDGET_BASE_URL)
    return f"{normalized_base_url}{normalized_path}" if normalized_base_url else normalized_path


def normalize_container_id(value):
    raw = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in (value or "").strip())
    return raw.strip("-_") or DEFAULT_CSR_CONTAINER_ID


def normalize_color(value, default=DEFAULT_CSR_PRIMARY_COLOR):
    raw = (value or default or "").strip()
    if not raw:
        return default

    if raw.startswith("#"):
        raw = raw[1:]

    if len(raw) not in {3, 6} or any(character not in "0123456789abcdefABCDEF" for character in raw):
        return default

    if len(raw) == 3:
        raw = "".join(character * 2 for character in raw)

    return f"#{raw.upper()}"


def build_default_integration_settings():
    return {
        "page_title": DEFAULT_CSR_DASHBOARD_TITLE,
        "base_url": DEFAULT_CSR_WIDGET_BASE_URL,
        "container_id": DEFAULT_CSR_CONTAINER_ID,
        "csr_key": CSR_WIDGET_KEY,
        "widget_title": DEFAULT_CSR_WIDGET_TITLE,
        "primary_color": DEFAULT_CSR_PRIMARY_COLOR,
        "auto_activate": False,
        "chat_list_poll": DEFAULT_CHAT_LIST_POLL,
        "message_poll": DEFAULT_MESSAGE_POLL,
        "script_src": f"{DEFAULT_CSR_WIDGET_BASE_URL}{DEFAULT_CSR_SCRIPT_PATH}",
        "relay_api_url": CENTRAL_API_URL,
        "relay_api_key": CSR_API_KEY,
    }


def normalize_integration_settings(raw_settings=None):
    defaults = build_default_integration_settings()
    source = raw_settings or {}

    base_url = normalize_url(
        source.get("base_url") or source.get("script_base_url"),
        defaults["base_url"],
    )
    relay_api_url = normalize_url(
        source.get("relay_api_url") or source.get("central_api_url"),
        defaults["relay_api_url"],
    )
    csr_key = (source.get("csr_key") or source.get("csr_widget_key") or defaults["csr_key"]).strip()
    relay_api_key = (source.get("relay_api_key") or source.get("csr_api_key") or defaults["relay_api_key"]).strip()
    page_title = (source.get("page_title") or defaults["page_title"]).strip() or DEFAULT_CSR_DASHBOARD_TITLE

    script_src = source.get("script_src")
    if not script_src and (source.get("script_base_url") or source.get("script_path")):
        legacy_base_url = normalize_url(source.get("script_base_url"), base_url or defaults["base_url"])
        script_src = normalize_script_src(source.get("script_path"), legacy_base_url)

    return {
        "page_title": page_title[:120],
        "base_url": base_url,
        "container_id": normalize_container_id(source.get("container_id") or defaults["container_id"]),
        "csr_key": csr_key,
        "widget_title": (source.get("widget_title") or defaults["widget_title"]).strip() or DEFAULT_CSR_WIDGET_TITLE,
        "primary_color": normalize_color(source.get("primary_color"), defaults["primary_color"]),
        "auto_activate": parse_bool(source.get("auto_activate"), default=defaults["auto_activate"]),
        "chat_list_poll": parse_int(source.get("chat_list_poll"), defaults["chat_list_poll"]),
        "message_poll": parse_int(source.get("message_poll"), defaults["message_poll"]),
        "script_src": normalize_script_src(script_src or defaults["script_src"], base_url or defaults["base_url"]),
        "relay_api_url": relay_api_url,
        "relay_api_key": relay_api_key,
    }


def load_integration_settings():
    settings = build_default_integration_settings()
    try:
        with open(INTEGRATION_CONFIG_PATH, "r", encoding="utf-8") as file_obj:
            stored = json.load(file_obj)
        if isinstance(stored, dict):
            settings.update(stored)
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        pass

    return normalize_integration_settings(settings)


def build_csr_dashboard_script_src(settings):
    return settings["script_src"]


def build_csr_dashboard_widget_config(settings):
    return {
        "autoActivate": bool(settings["auto_activate"]),
        "baseUrl": settings["base_url"],
        "chatListPoll": settings["chat_list_poll"],
        "containerId": settings["container_id"],
        "csrKey": settings["csr_key"],
        "messagePoll": settings["message_poll"],
        "primaryColor": settings["primary_color"],
        "widgetTitle": settings["widget_title"],
    }


def build_csr_dashboard_script_tag(settings):
    config_json = json.dumps(build_csr_dashboard_widget_config(settings), indent=2)
    return (
        "<script>\n"
        "window.CSRDashboardWidgetConfig = "
        f"{config_json};\n"
        "</script>\n"
        f'<script src="{build_csr_dashboard_script_src(settings)}"></script>'
    )


def render_csr_dashboard_app_html(settings):
    config_json = json.dumps(build_csr_dashboard_widget_config(settings), indent=2)
    script_src = escape(build_csr_dashboard_script_src(settings))
    container_id = escape(settings["container_id"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(settings["page_title"])}</title>
</head>
<body>
<div id="{container_id}"></div>
<script>
window.CSRDashboardWidgetConfig = {config_json};
</script>
<script src="{script_src}"></script>
</body>
</html>
"""


def sync_integration_settings_artifacts(settings):
    os.makedirs(instance_dir, exist_ok=True)
    normalized = normalize_integration_settings(settings)
    with open(INTEGRATION_CONFIG_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(normalized, file_obj, indent=2)
        file_obj.write("\n")

    with open(CSR_DASHBOARD_APP_PATH, "w", encoding="utf-8") as file_obj:
        file_obj.write(render_csr_dashboard_app_html(normalized))

    return normalized


def serialize_integration_settings(settings=None):
    config = normalize_integration_settings(settings or load_integration_settings())
    relay_key = config["relay_api_key"] or config["csr_key"]
    return {
        "relay_api_url": config["relay_api_url"],
        "relay_enabled": bool(config["relay_api_url"] and relay_key),
        "settings": config,
        "base_url": config["base_url"],
        "script_src": build_csr_dashboard_script_src(config),
        "script_tag": build_csr_dashboard_script_tag(config),
        "page_html": render_csr_dashboard_app_html(config),
        "preview_url": url_for("static", filename="csr-dashboard-app.html"),
    }


def build_central_auth_payload(settings=None):
    config = normalize_integration_settings(settings or load_integration_settings())
    # Support both the live widget key and the legacy CSR dashboard key.
    if not config["csr_key"] and not config["relay_api_key"]:
        return {}

    auth_payload = {}
    relay_key = config["csr_key"] or config["relay_api_key"]
    if relay_key:
        auth_payload["widget_key"] = relay_key
        auth_payload["csr_key"] = relay_key

    if config["relay_api_key"]:
        auth_payload["csr_key"] = config["relay_api_key"]

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


class AdminAccount(db.Model):
    __tablename__ = "admin_accounts"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120))
    last_seen_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def role(self):
        return "admin"

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
    acted_by_name = db.Column(db.String(120))
    acted_by_role = db.Column(db.String(20))
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
    if request.path.startswith("/admin/"):
        return redirect(url_for("admin_login"))
    if request.path.startswith("/csr/"):
        return redirect(url_for("csr_login"))
    return redirect(url_for("login"))


def get_current_csr_user():
    user_id = session.get("csr_user_id") or (session.get("user_id") if session.get("account_type") == "csr" else None)
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    return user if user and user.role == "csr" else None


def get_current_admin():
    admin_id = session.get("admin_id")
    if not admin_id:
        return None
    return db.session.get(AdminAccount, admin_id)


def get_current_user():
    return get_current_admin() or get_current_csr_user()


def get_online_cutoff(now=None):
    return (now or utcnow()) - timedelta(seconds=CSR_ONLINE_WINDOW_SECONDS)


def is_user_online(user, now=None):
    return bool(
        user
        and getattr(user, "is_active", True)
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


def touch_admin_presence(admin, force=False):
    if not admin:
        return

    now = utcnow()
    if force or not admin.last_seen_at or (now - admin.last_seen_at).total_seconds() >= CSR_PRESENCE_WRITE_INTERVAL_SECONDS:
        admin.last_seen_at = now
        db.session.commit()


def touch_actor_presence(actor, force=False):
    if isinstance(actor, User):
        touch_user_presence(actor, force=force)
    elif isinstance(actor, AdminAccount):
        touch_admin_presence(actor, force=force)


def actor_user_id(actor):
    return actor.id if isinstance(actor, User) else None


def actor_display_name(actor):
    if not actor:
        return "System"
    return getattr(actor, "display_name", None) or getattr(actor, "email", None) or "System"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        actor = get_current_user()
        if not actor:
            session.clear()
            return build_unauthorized_response()
        touch_actor_presence(actor)
        return f(*args, **kwargs)

    return decorated_function


def csr_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_csr_user()
        if not user:
            actor = get_current_user()
            if actor:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "CSR access is required."}), 403
                return redirect(url_for(dashboard_endpoint_for(actor)))
            session.clear()
            return build_unauthorized_response()
        touch_user_presence(user)
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin = get_current_admin()
        if not admin:
            actor = get_current_user()
            if actor:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Administrator access is required."}), 403
                return redirect(url_for(dashboard_endpoint_for(actor)))
            session.clear()
            return build_unauthorized_response()
        touch_admin_presence(admin)
        return f(*args, **kwargs)

    return decorated_function


# ─── Assignment Helpers ──────────────────────────────────────
def get_support_user_rows(available_only=False, online_only=False, include_inactive=False):
    filters = [User.role.in_(ASSIGNABLE_ROLES)]
    if not include_inactive:
        filters.append(User.is_active.is_(True))
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


def log_assignment_event(
    chat,
    event_type,
    notes=None,
    from_csr_id=None,
    to_csr_id=None,
    acted_by_user_id=None,
    acted_by_name_value=None,
    acted_by_role_value=None,
):
    db.session.add(
        ChatAssignmentEvent(
            chat=chat,
            event_type=event_type,
            notes=notes,
            from_csr_id=from_csr_id,
            to_csr_id=to_csr_id,
            acted_by_user_id=acted_by_user_id,
            acted_by_name=acted_by_name_value,
            acted_by_role=acted_by_role_value,
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
            acted_by_user_id=actor_user_id(actor),
            acted_by_name_value=actor_display_name(actor) if actor else None,
            acted_by_role_value=getattr(actor, "role", None) if actor else None,
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
        acted_by_user_id=actor_user_id(actor),
        acted_by_name_value=actor_display_name(actor) if actor else None,
        acted_by_role_value=getattr(actor, "role", None) if actor else None,
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
    return bool(user and chat and (user.role == "admin" or chat.assigned_csr_id == user.id))


def can_user_reply_to_chat(user, chat):
    return bool(
        user
        and isinstance(user, User)
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


def serialize_admin(admin):
    return {
        "id": admin.id,
        "email": admin.email,
        "display_name": admin.display_name or derive_display_name(admin.email),
        "role": "admin",
        "last_seen_at": isoformat_or_none(admin.last_seen_at),
        "created_at": isoformat_or_none(admin.created_at),
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
    elif isinstance(current_user, User) and chat.assigned_csr_id == current_user.id:
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
        "is_mine": bool(isinstance(current_user, User) and chat.assigned_csr_id == current_user.id),
        "lock_reason": None if can_user_open_chat(current_user, chat) else build_lock_reason(chat),
    }


def serialize_assignment_event(event):
    return {
        "id": event.id,
        "event_type": event.event_type,
        "notes": event.notes,
        "created_at": isoformat_or_none(event.created_at),
        "from_csr_name": event.from_csr.display_name or event.from_csr.email if event.from_csr else None,
        "to_csr_name": event.to_csr.display_name or event.to_csr.email if event.to_csr else None,
        "acted_by_name": event.acted_by_name or (event.acted_by.display_name or event.acted_by.email if event.acted_by else None),
        "acted_by_role": event.acted_by_role,
    }


def build_resolution_report(csr_users):
    now = utcnow()
    today_start = datetime(now.year, now.month, now.day)
    yesterday_start = today_start - timedelta(days=1)

    today_counts = {
        csr_id: count
        for csr_id, count in db.session.query(
            ChatAssignmentEvent.to_csr_id,
            func.count(ChatAssignmentEvent.id),
        )
        .filter(
            ChatAssignmentEvent.event_type == "resolved",
            ChatAssignmentEvent.to_csr_id.is_not(None),
            ChatAssignmentEvent.created_at >= today_start,
        )
        .group_by(ChatAssignmentEvent.to_csr_id)
        .all()
    }

    yesterday_counts = {
        csr_id: count
        for csr_id, count in db.session.query(
            ChatAssignmentEvent.to_csr_id,
            func.count(ChatAssignmentEvent.id),
        )
        .filter(
            ChatAssignmentEvent.event_type == "resolved",
            ChatAssignmentEvent.to_csr_id.is_not(None),
            ChatAssignmentEvent.created_at >= yesterday_start,
            ChatAssignmentEvent.created_at < today_start,
        )
        .group_by(ChatAssignmentEvent.to_csr_id)
        .all()
    }

    leaderboard = []
    for csr in csr_users:
        leaderboard.append(
            {
                "id": csr["id"],
                "display_name": csr["display_name"],
                "email": csr["email"],
                "resolved_today": today_counts.get(csr["id"], 0),
                "resolved_yesterday": yesterday_counts.get(csr["id"], 0),
                "open_chats": csr["active_chat_count"],
                "max_concurrent_chats": csr["max_concurrent_chats"],
                "is_online": csr["is_online"],
            }
        )

    leaderboard.sort(
        key=lambda item: (
            -item["resolved_today"],
            -item["resolved_yesterday"],
            -item["open_chats"],
            item["display_name"].lower(),
        )
    )

    return {
        "today_total": sum(today_counts.values()),
        "yesterday_total": sum(yesterday_counts.values()),
        "leaderboard": leaderboard,
    }


def build_admin_dashboard_payload(current_admin):
    integration = serialize_integration_settings()
    chats = (
        ChatConversation.query.order_by(
            ChatConversation.last_activity_at.desc(),
            ChatConversation.reverted_at.desc(),
        )
        .limit(150)
        .all()
    )
    online_cutoff = get_online_cutoff()
    support_user_rows = sorted(
        get_support_user_rows(available_only=False, include_inactive=True),
        key=lambda row: (
            (row[0].display_name or row[0].email).lower(),
            row[0].id,
        ),
    )
    csr_users = [serialize_support_user(user, active_chat_count) for user, active_chat_count in support_user_rows]
    registered_csrs = User.query.filter(User.role.in_(ASSIGNABLE_ROLES)).count()
    online_csrs = User.query.filter(
        User.role.in_(ASSIGNABLE_ROLES),
        User.is_active.is_(True),
        User.last_seen_at.is_not(None),
        User.last_seen_at >= online_cutoff,
    ).count()
    available_csrs = User.query.filter(
        User.role.in_(ASSIGNABLE_ROLES),
        User.is_active.is_(True),
        User.is_available.is_(True),
        User.last_seen_at.is_not(None),
        User.last_seen_at >= online_cutoff,
    ).count()
    active_csrs = (
        db.session.query(func.count(func.distinct(ChatConversation.assigned_csr_id)))
        .filter(
            ChatConversation.assigned_csr_id.is_not(None),
            ChatConversation.status.in_(ACTIVE_CHAT_STATUSES),
        )
        .scalar()
        or 0
    )
    available_csr_users = [
        csr
        for csr in csr_users
        if csr["is_active"] and csr["is_available"] and csr["is_online"]
    ]
    recent_events = (
        ChatAssignmentEvent.query.order_by(
            ChatAssignmentEvent.created_at.desc(),
            ChatAssignmentEvent.id.desc(),
        )
        .limit(120)
        .all()
    )
    resolution_report = build_resolution_report(csr_users)
    status_breakdown = {
        "queued": ChatConversation.query.filter_by(status="queued").count(),
        "assigned": ChatConversation.query.filter_by(status="assigned").count(),
        "in_progress": ChatConversation.query.filter_by(status="in_progress").count(),
        "resolved": ChatConversation.query.filter(ChatConversation.status.in_(RESOLVED_CHAT_STATUSES)).count(),
    }

    return {
        "mode": "admin",
        "current_user": serialize_admin(current_admin),
        "integration": integration,
        "summary": {
            "registered_csrs": registered_csrs,
            "online_csrs": online_csrs,
            "available_csrs": available_csrs,
            "active_csrs": active_csrs,
            "total_chats": ChatConversation.query.count(),
            "active_chats": ChatConversation.query.filter(ChatConversation.status.in_(ACTIVE_CHAT_STATUSES)).count(),
            "queued_chats": ChatConversation.query.filter_by(status="queued").count(),
            "resolved_chats": ChatConversation.query.filter(ChatConversation.status.in_(RESOLVED_CHAT_STATUSES)).count(),
            "total_capacity": sum(csr["max_concurrent_chats"] for csr in csr_users if csr["is_active"]),
            "used_capacity": sum(csr["active_chat_count"] for csr in csr_users if csr["is_active"]),
            "resolved_today": resolution_report["today_total"],
            "resolved_yesterday": resolution_report["yesterday_total"],
        },
        "csr_users": csr_users,
        "available_csr_users": available_csr_users,
        "chats": [serialize_chat(chat, current_admin) for chat in chats],
        "recent_activity": [serialize_assignment_event(event) for event in recent_events],
        "reports": {
            "status_breakdown": status_breakdown,
            "resolution_leaderboard": resolution_report["leaderboard"],
        },
    }


def build_csr_dashboard_payload(current_user):
    integration = serialize_integration_settings()
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
            (row[0].display_name or row[0].email).lower(),
            row[0].id,
        ),
    )
    support_users = [serialize_support_user(user, active_chat_count) for user, active_chat_count in support_user_rows]

    return {
        "mode": "csr",
        "current_user": serialize_user(current_user),
        "integration": integration,
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
        "csrs": support_users,
        "chats": [serialize_chat(chat, current_user) for chat in chats],
    }


def build_dashboard_payload(current_actor):
    if isinstance(current_actor, AdminAccount):
        return build_admin_dashboard_payload(current_actor)
    return build_csr_dashboard_payload(current_actor)


def relay_reply_to_central(chat, message):
    settings = load_integration_settings()
    auth_payload = build_central_auth_payload(settings)
    if not settings["relay_api_url"]:
        return {"skipped": True, "reason": "Central API URL is not configured."}
    if not auth_payload:
        return {"skipped": True, "reason": "CSR relay key is not configured."}

    try:
        _, payload = post_json(
            f"{settings['relay_api_url']}/api/csr/external_message",
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
    settings = load_integration_settings()
    auth_payload = build_central_auth_payload(settings)
    if not settings["relay_api_url"]:
        return {"skipped": True, "reason": "Central API URL is not configured."}
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
            f"{settings['relay_api_url']}/api/csr/transfer",
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

        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_admin_accounts_email ON admin_accounts (email)"))
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

    assignment_columns = {column["name"] for column in inspector.get_columns("chat_assignment_events")}
    assignment_updates = {
        "acted_by_name": "ALTER TABLE chat_assignment_events ADD COLUMN acted_by_name VARCHAR(120)",
        "acted_by_role": "ALTER TABLE chat_assignment_events ADD COLUMN acted_by_role VARCHAR(20)",
    }
    with db.engine.begin() as connection:
        for column_name, statement in assignment_updates.items():
            if column_name not in assignment_columns:
                connection.execute(text(statement))


def email_in_use(email):
    normalized_email = (email or "").strip().lower()
    return bool(
        AdminAccount.query.filter_by(email=normalized_email).first()
        or User.query.filter_by(email=normalized_email).first()
    )


def migrate_legacy_admins():
    legacy_admins = User.query.filter(User.role == "admin").order_by(User.created_at.asc(), User.id.asc()).all()
    if not legacy_admins:
        return

    for legacy_admin in legacy_admins:
        admin_account = AdminAccount.query.filter_by(email=legacy_admin.email).first()
        if not admin_account:
            admin_account = AdminAccount(
                email=legacy_admin.email,
                password_hash=legacy_admin.password_hash,
                display_name=legacy_admin.display_name or derive_display_name(legacy_admin.email),
                last_seen_at=legacy_admin.last_seen_at,
                created_at=legacy_admin.created_at or utcnow(),
            )
            db.session.add(admin_account)

        active_chats = ChatConversation.query.filter(
            ChatConversation.assigned_csr_id == legacy_admin.id,
            ChatConversation.status.in_(ACTIVE_CHAT_STATUSES),
        ).all()
        for chat in active_chats:
            chat.assigned_csr_id = None
            chat.assigned_at = None
            chat.status = "queued"
            chat.last_activity_at = utcnow()
            log_assignment_event(
                chat,
                "queued",
                notes=f"Chat returned to queue while separating legacy admin account {legacy_admin.display_name or legacy_admin.email} from CSR users.",
                from_csr_id=legacy_admin.id,
                acted_by_name_value=legacy_admin.display_name or legacy_admin.email,
                acted_by_role_value="admin",
            )

        legacy_admin.role = "archived_admin"
        legacy_admin.is_active = False
        legacy_admin.is_available = False

    db.session.commit()
    rebalance_queued_chats()
    db.session.commit()


def bootstrap_users():
    migrate_legacy_admins()

    users = User.query.order_by(User.created_at.asc(), User.id.asc()).all()
    if not users:
        return

    for user in users:
        if not user.display_name:
            user.display_name = derive_display_name(user.email)
        if user.role not in {"csr", "archived_admin"}:
            user.role = "csr"
        if user.role == "archived_admin":
            user.is_active = False
            user.is_available = False
        else:
            if user.is_active is None:
                user.is_active = True
            if user.is_available is None:
                user.is_available = True
            if not user.max_concurrent_chats or user.max_concurrent_chats < 1:
                user.max_concurrent_chats = DEFAULT_MAX_CONCURRENT_CHATS

    db.session.commit()


# ─── Auth Routes ─────────────────────────────────────────────
@app.route("/")
def index():
    current_actor = get_current_user()
    if current_actor:
        return redirect(url_for(dashboard_endpoint_for(current_actor)))
    return render_template("login.html", **auth_context(normalize_role(request.args.get("role"), default="csr")))


@app.route("/csr/dashboard")
@csr_required
def csr_dashboard():
    return render_template("csr_dashboard.html", user=get_current_csr_user())


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template(
        "admin_dashboard.html",
        user=get_current_admin(),
        knowledge_base_updater_url=KNOWLEDGE_BASE_UPDATER_URL,
    )


def handle_signup(role=None):
    auth_role = normalize_role(role or request.values.get("role"), default="csr")
    if auth_role != "admin":
        flash("CSR accounts are created by an administrator from the admin dashboard.", "error")
        return redirect(url_for("login", role="csr"))

    if get_current_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        display_name = request.form.get("display_name", "").strip()

        if not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template("signup.html", **auth_context(auth_role))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html", **auth_context(auth_role))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html", **auth_context(auth_role))

        if email_in_use(email):
            flash("An account with this email already exists.", "error")
            return render_template("signup.html", **auth_context(auth_role))

        if auth_role == "admin":
            admin = AdminAccount(
                email=email,
                display_name=display_name or derive_display_name(email),
            )
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            flash("Admin account created successfully! Please log in.", "success")
            return redirect(url_for("admin_login"))

        user = User(
            email=email,
            display_name=display_name or derive_display_name(email),
            role="csr",
            is_active=True,
            is_available=True,
            max_concurrent_chats=DEFAULT_MAX_CONCURRENT_CHATS,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        rebalance_queued_chats(actor=user)

        flash("CSR account created successfully! Please log in.", "success")
        return redirect(url_for("csr_login"))

    return render_template("signup.html", **auth_context(auth_role))


def handle_login(role=None):
    auth_role = normalize_role(role or request.values.get("role"), default="csr")
    if get_current_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html", **auth_context(auth_role))

        if auth_role == "admin":
            admin = AdminAccount.query.filter_by(email=email).first()
            if not admin or not admin.check_password(password):
                flash("Invalid admin email or password.", "error")
                return render_template("login.html", **auth_context(auth_role))

            admin.last_seen_at = utcnow()
            db.session.commit()
            session.clear()
            session.permanent = True
            session["account_type"] = "admin"
            session["admin_id"] = admin.id
            session["user_email"] = admin.email
            return redirect(url_for("admin_dashboard"))

        user = User.query.filter_by(email=email, role="csr").first()
        if not user or not user.check_password(password):
            flash("Invalid CSR email or password.", "error")
            return render_template("login.html", **auth_context(auth_role))

        user.last_seen_at = utcnow()
        db.session.commit()
        session.clear()
        session.permanent = True
        session["account_type"] = "csr"
        session["csr_user_id"] = user.id
        session["user_email"] = user.email
        return redirect(url_for("csr_dashboard"))

    return render_template("login.html", **auth_context(auth_role))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    return redirect(url_for("admin_signup"))


@app.route("/admin/signup", methods=["GET", "POST"])
def admin_signup():
    return handle_signup("admin")


@app.route("/csr/signup", methods=["GET", "POST"])
def csr_signup():
    flash("CSR accounts are created by an administrator from the admin dashboard.", "error")
    return redirect(url_for("login", role="csr"))


@app.route("/login", methods=["GET", "POST"])
def login():
    return handle_login(normalize_role(request.values.get("role"), default="csr"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    return redirect(url_for("login", role="admin"))


@app.route("/csr/login", methods=["GET", "POST"])
def csr_login():
    return redirect(url_for("login", role="csr"))


@app.route("/logout")
def logout():
    current_user = get_current_user()
    next_login_route = url_for("login")
    if current_user:
        next_login_route = url_for("admin_login" if current_user.role == "admin" else "csr_login")
        current_user.last_seen_at = None
        db.session.commit()
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(next_login_route)


@app.route("/health")
def health():
    integration = serialize_integration_settings()
    return {
        "status": "healthy",
        "service": "CSR Widget App",
        "relay_enabled": integration["relay_enabled"],
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
        log_assignment_event(
            chat,
            "reverted",
            notes="Incoming handoff from the QSTP widget.",
            acted_by_name_value="Widget Relay",
            acted_by_role_value="system",
        )
    else:
        was_resolved = chat.status in RESOLVED_CHAT_STATUSES
        if was_resolved:
            reset_existing = True
            chat.resolved_at = None
            chat.assigned_csr_id = None
            chat.assigned_at = None
            chat.status = "queued"
            log_assignment_event(
                chat,
                "reopened",
                notes="Existing visitor reopened by a new AI handoff.",
                acted_by_name_value="Widget Relay",
                acted_by_role_value="system",
            )

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
    log_assignment_event(
        chat,
        "customer_message",
        notes="Customer sent a new message from the widget.",
        to_csr_id=chat.assigned_csr_id,
        acted_by_name_value="Widget Relay",
        acted_by_role_value="system",
    )
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
        log_assignment_event(
            chat,
            "cleaned_up",
            notes="Chat cleaned up by external resolver.",
            to_csr_id=chat.assigned_csr_id,
            acted_by_name_value="External Resolver",
            acted_by_role_value="system",
        )
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
            "events": [serialize_assignment_event(event) for event in chat.assignment_events],
        }
    )


@app.route("/api/chats/<int:chat_id>/reply", methods=["POST"])
@csr_required
def reply_to_chat(chat_id):
    current_user = get_current_csr_user()
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
        acted_by_name_value=actor_display_name(current_user),
        acted_by_role_value=current_user.role,
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
        notes=f"Chat resolved by {actor_display_name(current_user)}.",
        to_csr_id=chat.assigned_csr_id,
        acted_by_user_id=actor_user_id(current_user),
        acted_by_name_value=actor_display_name(current_user),
        acted_by_role_value=current_user.role,
    )
    db.session.commit()
    rebalance_queued_chats(actor=current_user)

    return jsonify({"success": True, "relay": relay_result, "dashboard": build_dashboard_payload(current_user)})


@app.route("/api/chats/<int:chat_id>/delete", methods=["POST"])
@admin_required
def delete_chat(chat_id):
    current_user = get_current_admin()
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    external_chat_id = chat.external_chat_id
    db.session.delete(chat)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": f"Deleted chat {external_chat_id} from the CSR database.",
            "dashboard": build_dashboard_payload(current_user),
        }
    )


@app.route("/api/chats/<int:chat_id>/assign", methods=["POST"])
@admin_required
def reassign_chat(chat_id):
    current_user = get_current_admin()
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
        note=f"Chat reassigned by administrator {actor_display_name(current_user)}.",
    )
    db.session.commit()

    return jsonify({"success": True, "dashboard": build_dashboard_payload(current_user)})


@app.route("/api/chats/rebalance", methods=["POST"])
@admin_required
def rebalance_chats():
    current_user = get_current_admin()
    assigned_count = rebalance_queued_chats(actor=current_user)
    return jsonify({"success": True, "assigned_count": assigned_count, "dashboard": build_dashboard_payload(current_user)})


@app.route("/api/csrs/<int:user_id>/settings", methods=["POST"])
@admin_required
def update_csr_settings(user_id):
    current_user = get_current_admin()
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


@app.route("/api/admin/csrs/create", methods=["POST"])
@admin_required
def create_csr_account():
    current_admin = get_current_admin()
    payload = get_request_payload()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    display_name = (payload.get("display_name") or "").strip()
    max_concurrent_chats = parse_int(payload.get("max_concurrent_chats"), DEFAULT_MAX_CONCURRENT_CHATS)
    is_available = parse_bool(payload.get("is_available"), default=True)

    if not email or not password:
        return jsonify({"error": "CSR email and password are required."}), 400

    if len(password) < 6:
        return jsonify({"error": "CSR password must be at least 6 characters."}), 400

    if email_in_use(email):
        return jsonify({"error": "An account with this email already exists."}), 400

    csr_user = User(
        email=email,
        display_name=display_name or derive_display_name(email),
        role="csr",
        is_active=True,
        is_available=is_available,
        max_concurrent_chats=max_concurrent_chats,
    )
    csr_user.set_password(password)
    db.session.add(csr_user)
    db.session.commit()
    rebalance_queued_chats(actor=current_admin)

    return jsonify(
        {
            "success": True,
            "message": f"CSR account created for {csr_user.display_name or csr_user.email}.",
            "dashboard": build_dashboard_payload(current_admin),
        }
    )


@app.route("/api/admin/integration-settings", methods=["POST"])
@admin_required
def update_integration_settings():
    current_admin = get_current_admin()
    payload = get_request_payload()

    settings = normalize_integration_settings(
        {
            "page_title": payload.get("page_title"),
            "base_url": payload.get("base_url"),
            "container_id": payload.get("container_id"),
            "csr_key": payload.get("csr_key"),
            "widget_title": payload.get("widget_title"),
            "primary_color": payload.get("primary_color"),
            "auto_activate": payload.get("auto_activate"),
            "chat_list_poll": payload.get("chat_list_poll"),
            "message_poll": payload.get("message_poll"),
            "script_src": payload.get("script_src"),
            "relay_api_url": payload.get("relay_api_url"),
            "relay_api_key": payload.get("relay_api_key"),
        }
    )

    if not settings["base_url"]:
        return jsonify({"error": "Base URL is required."}), 400
    if not settings["csr_key"]:
        return jsonify({"error": "CSR key is required."}), 400
    if not settings["script_src"]:
        return jsonify({"error": "Script source is required."}), 400

    sync_integration_settings_artifacts(settings)

    return jsonify(
        {
            "success": True,
            "message": "CSR integration settings saved to the server file.",
            "dashboard": build_dashboard_payload(current_admin),
        }
    )


# ─── Startup ─────────────────────────────────────────────────
with app.app_context():
    ensure_schema()
    bootstrap_users()
    sync_integration_settings_artifacts(load_integration_settings())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
