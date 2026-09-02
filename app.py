from datetime import UTC, datetime, timedelta
from functools import wraps
from html import escape
import hmac
import json
import os
import random
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, func, inspect, or_, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload
from werkzeug.security import check_password_hash, generate_password_hash


ACTIVE_CHAT_STATUSES = ("queued", "assigned", "in_progress")
RESOLVED_CHAT_STATUSES = ("resolved", "closed")
ASSIGNABLE_ROLES = ("csr",)
DEFAULT_MAX_CONCURRENT_CHATS = 4
# Stale-session fallback. Chrome throttles background timers to ~60s, so this
# must stay well above one minute. Explicit logout/close uses presence_online.
CSR_ONLINE_WINDOW_SECONDS = 180
CSR_PRESENCE_WRITE_INTERVAL_SECONDS = 15
CENTRAL_API_URL = os.environ.get("CENTRAL_API_URL", "http://52.74.227.205:5003").rstrip("/")
CSR_WIDGET_KEY = os.environ.get("CSR_WIDGET_KEY", "csr_aridian_52_74_227_205_demo").strip()
CSR_API_KEY = os.environ.get("CSR_API_KEY", "").strip()
TICKET_CODE_PREFIXES = ("TCK", "FLT", "CLP", "IDK", "SUP", "OPS", "HLP", "TKT", "SRV", "INC")


basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))
TICKETS_API_KEY = os.environ.get("TICKETS_API_KEY", "").strip()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "csr-widget-app-secret-key-2024")

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


def build_database_uri():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    db_password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    if supabase_url and db_password:
        project_ref = supabase_url.replace("https://", "").split(".")[0]
        encoded_password = quote_plus(db_password)
        pooler_host = os.environ.get("SUPABASE_POOLER_HOST", "").strip()
        if pooler_host:
            return (
                f"postgresql://postgres.{project_ref}:{encoded_password}"
                f"@{pooler_host}:6543/postgres"
            )
        return f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

    raise RuntimeError(
        "Database configuration missing. Set DATABASE_URL or SUPABASE_URL + SUPABASE_DB_PASSWORD in .env"
    )


app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
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
            "allow_headers": ["Content-Type", "Authorization", "X-Service-Secret"],
            "supports_credentials": True,
        }
    },
)


@app.after_request
def prevent_dynamic_page_caching(response):
    """Never let a signed-in dashboard be restored after logout via browser history."""
    if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def as_naive_utc(value):
    """Normalize DB/Python datetimes to naive UTC for consistent comparisons."""
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def derive_display_name(email):
    local_part = (email or "").split("@")[0].replace(".", " ").replace("_", " ").strip()
    return local_part.title() or "CSR User"


def normalize_role(value, default="csr"):
    normalized = (value or default or "csr").strip().lower()
    return normalized if normalized in {"admin", "csr"} else default


def dashboard_endpoint_for(user_or_role):
    role = user_or_role if isinstance(user_or_role, str) else getattr(user_or_role, "role", "csr")
    if isinstance(user_or_role, TechTeamAccount):
        return "tech_dashboard"
    if normalize_role(role) == "admin":
        return "admin_dashboard"
    return "csr_dashboard"


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
    """Serialize datetimes as UTC ISO-8601 with Z so browsers convert to local time."""
    if not value:
        return None
    if getattr(value, "tzinfo", None) is not None:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    # App stores naive datetimes as UTC.
    return f"{value.isoformat()}Z"


def get_request_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    raw = request.get_data(cache=True, as_text=True)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            pass
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
    unlimited_chats = db.Column(db.Boolean, nullable=False, default=True)
    last_assigned_at = db.Column(db.DateTime)
    last_seen_at = db.Column(db.DateTime)
    presence_online = db.Column(db.Boolean, nullable=False, default=False)
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
    customer_external_user_id = db.Column(db.String(120), index=True)
    auth_mode = db.Column(db.String(20), nullable=False, default="anonymous")
    authenticated_user_data = db.Column(db.Text)
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
    image_attachments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    chat = db.relationship("ChatConversation", back_populates="messages")


# ─── Technical Team Models ───────────────────────────────────
class TechTeamAccount(db.Model):
    __tablename__ = "tech_team_accounts"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120))
    specialty = db.Column(db.String(100), default="General")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_seen_at = db.Column(db.DateTime)
    presence_online = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    claimed_tickets = db.relationship(
        "Ticket",
        back_populates="assigned_tech",
        foreign_keys="Ticket.assigned_tech_id",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class TicketStatus(db.Model):
    __tablename__ = "ticket_statuses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20), default="#64748b")
    sort_order = db.Column(db.Integer, default=0)
    is_default = db.Column(db.Boolean, default=False)
    is_resolved = db.Column(db.Boolean, default=False)

    @staticmethod
    def get_default_statuses():
        return [
            {"name": "open", "label": "Open", "color": "#f59e0b", "sort_order": 1, "is_default": True, "is_resolved": False},
            {"name": "in_progress", "label": "In Progress", "color": "#3b82f6", "sort_order": 2, "is_default": True, "is_resolved": False},
            {"name": "waiting_parts", "label": "Waiting for Parts", "color": "#8b5cf6", "sort_order": 3, "is_default": True, "is_resolved": False},
            {"name": "resolved", "label": "Resolved", "color": "#10b981", "sort_order": 4, "is_default": True, "is_resolved": True},
            {"name": "closed", "label": "Closed", "color": "#64748b", "sort_order": 5, "is_default": True, "is_resolved": True},
        ]


def normalize_ticket_status_label(label):
    """Keep legacy status labels readable in every dashboard."""
    value = (label or "").strip()
    compact_value = value.lower().replace("_", "").replace("-", "").replace(" ", "")
    return "On Hold" if compact_value == "onhold" else value


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(24), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    priority = db.Column(db.String(20), nullable=False, default="normal")
    status = db.Column(db.String(50), nullable=False, default="open", index=True)
    # Origin keeps CSR chat tickets separate from admin/tech operational tickets.
    # csr = created from a customer chat; admin/tech = independent (no chat required).
    origin = db.Column(db.String(20), nullable=False, default="csr", index=True)
    created_by_csr_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey("admin_accounts.id"), nullable=True, index=True)
    created_by_tech_id = db.Column(db.Integer, db.ForeignKey("tech_team_accounts.id"), nullable=True, index=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("chat_conversations.id"), index=True)
    assigned_tech_id = db.Column(db.Integer, db.ForeignKey("tech_team_accounts.id"), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    resolved_at = db.Column(db.DateTime)

    created_by_csr = db.relationship("User", foreign_keys=[created_by_csr_id])
    created_by_admin = db.relationship("AdminAccount", foreign_keys=[created_by_admin_id])
    created_by_tech = db.relationship("TechTeamAccount", foreign_keys=[created_by_tech_id])
    chat_conversation = db.relationship("ChatConversation", foreign_keys=[chat_id])
    assigned_tech = db.relationship(
        "TechTeamAccount",
        foreign_keys=[assigned_tech_id],
        back_populates="claimed_tickets",
    )
    status_logs = db.relationship(
        "TicketStatusLog",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketStatusLog.created_at.desc()",
    )
    messages = db.relationship(
        "TicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketMessage.created_at.asc()",
    )


class TicketStatusLog(db.Model):
    __tablename__ = "ticket_status_logs"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50), nullable=False)
    old_assigned_tech_id = db.Column(db.Integer)
    new_assigned_tech_id = db.Column(db.Integer)
    changed_by_user_id = db.Column(db.Integer)
    changed_by_role = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    ticket = db.relationship("Ticket", back_populates="status_logs")


class TicketMessage(db.Model):
    __tablename__ = "ticket_messages"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    sender_type = db.Column(db.String(20), nullable=False, index=True)  # 'csr' or 'tech'
    sender_id = db.Column(db.Integer, nullable=False)
    sender_name = db.Column(db.String(120))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    ticket = db.relationship("Ticket", back_populates="messages")


# ─── Auth Helpers ────────────────────────────────────────────
def build_unauthorized_response():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Authentication required."}), 401
    if request.path.startswith("/admin/"):
        return redirect(url_for("admin_login"))
    if request.path.startswith("/csr/"):
        return redirect(url_for("csr_login"))
    if request.path.startswith("/tech/"):
        return redirect(url_for("tech_login"))
    return redirect(url_for("login"))


def tickets_api_required(f):
    """Protect server-to-server ticket integration endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not TICKETS_API_KEY:
            return jsonify({"error": "Ticket integration API is not configured."}), 503

        supplied_key = (request.headers.get("X-Service-Secret") or "").strip()
        authorization = (request.headers.get("Authorization") or "").strip()
        if not supplied_key and authorization.lower().startswith("bearer "):
            supplied_key = authorization[7:].strip()

        if not supplied_key or not hmac.compare_digest(supplied_key, TICKETS_API_KEY):
            return jsonify({"error": "Invalid or missing API credentials."}), 401
        return f(*args, **kwargs)

    return decorated_function


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
    # A browser can have more than one portal identity alive at once. Prefer
    # the portal that made the request (or the most recently authenticated
    # portal) instead of always choosing the admin account first. This keeps
    # CSR-only dashboard calls, such as opening a Mine chat, in the CSR scope.
    preferred_role = (request.headers.get("X-Portal") or session.get("account_type") or "").strip().lower()
    getters = {
        "admin": get_current_admin,
        "csr": get_current_csr_user,
        "tech": get_current_tech_user,
    }
    preferred_getter = getters.get(preferred_role)
    if preferred_getter:
        preferred_user = preferred_getter()
        if preferred_user:
            return preferred_user
    return get_current_admin() or get_current_csr_user() or get_current_tech_user()


def clear_portal_session(role):
    """Remove only one portal identity so CSR, admin, and tech tabs can coexist."""
    key_by_role = {
        "admin": "admin_id",
        "csr": "csr_user_id",
        "tech": "tech_user_id",
    }
    session.pop(key_by_role[role], None)
    if role == "csr":
        session.pop("user_id", None)  # Legacy CSR session key.

    if session.get("account_type") == role:
        session.pop("account_type", None)
        session.pop("user_email", None)

    if not any(session.get(key) for key in key_by_role.values()):
        session.clear()


def get_online_cutoff(now=None):
    return (as_naive_utc(now) or utcnow()) - timedelta(seconds=CSR_ONLINE_WINDOW_SECONDS)


def online_presence_filters(model, now=None):
    return [
        model.presence_online.is_(True),
        model.last_seen_at.is_not(None),
        model.last_seen_at >= get_online_cutoff(now),
    ]


def is_presence_online(account, now=None):
    if not account or not getattr(account, "is_active", True):
        return False
    if not getattr(account, "presence_online", False):
        return False
    last_seen = as_naive_utc(getattr(account, "last_seen_at", None))
    if not last_seen:
        return False
    return last_seen >= get_online_cutoff(now)


def is_user_online(user, now=None):
    return is_presence_online(user, now=now)


def is_tech_online(tech, now=None):
    """Live presence for technical team (explicit session + recent heartbeat)."""
    return is_presence_online(tech, now=now)


def _stamp_presence(account, *, online, force=False):
    if not account:
        return False
    now = utcnow()
    changed = False
    current_online = bool(getattr(account, "presence_online", False))
    if current_online != bool(online):
        account.presence_online = bool(online)
        changed = True
    last_seen = as_naive_utc(getattr(account, "last_seen_at", None))
    age_seconds = None if last_seen is None else (now - last_seen).total_seconds()
    if force or last_seen is None or age_seconds is None or age_seconds >= CSR_PRESENCE_WRITE_INTERVAL_SECONDS:
        account.last_seen_at = now
        changed = True
    if changed:
        db.session.commit()
    return changed


def touch_user_presence(user, force=False):
    if not user or not user.is_active:
        return
    _stamp_presence(user, online=True, force=force)


def touch_admin_presence(admin, force=False):
    if not admin:
        return
    now = utcnow()
    last_seen = as_naive_utc(admin.last_seen_at)
    if force or not last_seen or (now - last_seen).total_seconds() >= CSR_PRESENCE_WRITE_INTERVAL_SECONDS:
        admin.last_seen_at = now
        db.session.commit()


def touch_actor_presence(actor, force=False):
    if isinstance(actor, User):
        touch_user_presence(actor, force=force)
    elif isinstance(actor, AdminAccount):
        touch_admin_presence(actor, force=force)
    elif isinstance(actor, TechTeamAccount):
        touch_tech_presence(actor, force=force)


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


def get_current_tech_user():
    tech_id = session.get("tech_user_id")
    if not tech_id:
        return None
    return db.session.get(TechTeamAccount, tech_id)


def touch_tech_presence(tech, force=False):
    if not tech or not getattr(tech, "is_active", True):
        return
    _stamp_presence(tech, online=True, force=force)


def mark_user_offline(user):
    """Close the live session but keep last_seen as the logout/close time."""
    if user:
        _stamp_presence(user, online=False, force=True)


def mark_tech_offline(tech):
    if tech:
        _stamp_presence(tech, online=False, force=True)


def finalize_user_presence(user):
    """Mark CSR offline on logout or browser close."""
    mark_user_offline(user)


def finalize_tech_presence(tech):
    mark_tech_offline(tech)


def finalize_admin_presence(admin):
    if admin:
        touch_admin_presence(admin, force=True)


def tech_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        tech = get_current_tech_user()
        if not tech:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Technical team access is required."}), 403
            return redirect(url_for("tech_login"))
        if not tech.is_active:
            finalize_tech_presence(tech)
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "Technical team account is disabled."}), 403
            flash("Your technical team account is disabled.", "error")
            return redirect(url_for("tech_login"))
        touch_tech_presence(tech)
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
        filters.extend(online_presence_filters(User))

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
    # All online + available CSRs are eligible; chats are unlimited by default.
    eligible_rows = list(get_support_user_rows(available_only=True, online_only=True))
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
# Super-CSR model: every authenticated CSR/admin can *view* every chat's
# transcript. A chat becomes "owned" only when a CSR claims it (by clicking);
# at that point other CSRs see it in read-only mode while the owning CSR (or
# an admin) can reply and resolve.


def can_user_open_chat(user, chat):
    return bool(user and chat)


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


def can_user_claim_chat(user, chat):
    if not (user and isinstance(user, User) and chat):
        return False
    if user.role not in ASSIGNABLE_ROLES:
        return False
    if chat.status in RESOLVED_CHAT_STATUSES:
        return False
    return chat.assigned_csr_id in (None, user.id)


def claim_chat(chat, user):
    """Atomically claim a queued/unassigned chat for the given CSR.

    Returns (ok, error_message). The claim succeeds if the chat is not
    resolved and is either currently unassigned or already owned by
    the same user (idempotent click).
    """
    if not user or not isinstance(user, User) or user.role not in ASSIGNABLE_ROLES:
        return False, "Only CSR users can claim chats."

    if chat.status in RESOLVED_CHAT_STATUSES:
        return False, "This chat is already resolved."

    if chat.assigned_csr_id == user.id:
        return True, None

    now = utcnow()
    new_status = "in_progress" if chat.status == "in_progress" else "assigned"

    # Atomic claim: only succeeds when the row is still unassigned. This
    # protects against two CSRs racing to click the same queued card.
    result = db.session.execute(
        update(ChatConversation)
        .where(
            ChatConversation.id == chat.id,
            ChatConversation.assigned_csr_id.is_(None),
        )
        .values(
            assigned_csr_id=user.id,
            assigned_at=now,
            status=new_status,
            last_activity_at=now,
        )
    )

    if result.rowcount == 0:
        db.session.refresh(chat)
        owner = chat.assigned_csr
        owner_label = (owner.display_name or owner.email) if owner else "another CSR"
        return False, f"This chat has already been claimed by {owner_label}."

    db.session.refresh(chat)
    user.last_assigned_at = now
    log_assignment_event(
        chat,
        "claimed",
        notes=f"Chat claimed by {user.display_name or user.email}.",
        to_csr_id=user.id,
        acted_by_user_id=user.id,
        acted_by_name_value=user.display_name or user.email,
        acted_by_role_value=user.role,
    )
    return True, None


def normalize_image_attachments(payload):
    raw_images = payload.get("images") or payload.get("attachments") or []
    if not isinstance(raw_images, list):
        raw_images = [raw_images]

    attachments = []
    for raw_image in raw_images:
        if not isinstance(raw_image, dict):
            continue
        url = (
            raw_image.get("image_url")
            or raw_image.get("imageUrl")
            or raw_image.get("url")
            or raw_image.get("data_url")
            or raw_image.get("dataUrl")
            or ""
        )
        data_url = raw_image.get("data_url") or raw_image.get("dataUrl") or ""
        if not url:
            continue
        attachments.append(
            {
                "name": str(raw_image.get("name") or "Uploaded image")[:160],
                "mime_type": str(raw_image.get("mime_type") or raw_image.get("type") or ""),
                "image_url": url,
                "imageUrl": url,
                "url": url,
                "data_url": data_url,
            }
        )

    for key in ("image_url", "imageUrl"):
        if payload.get(key):
            attachments.append(
                {
                    "name": "Uploaded image",
                    "mime_type": "",
                    "image_url": payload[key],
                    "imageUrl": payload[key],
                    "url": payload[key],
                    "data_url": "",
                }
            )

    for url in payload.get("image_urls") or []:
        if url:
            attachments.append(
                {
                    "name": "Uploaded image",
                    "mime_type": "",
                    "image_url": url,
                    "imageUrl": url,
                    "url": url,
                    "data_url": "",
                }
            )

    deduped = []
    seen = set()
    for attachment in attachments:
        key = attachment.get("image_url") or attachment.get("url") or attachment.get("data_url")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(attachment)
    return deduped


def serialize_image_attachments(attachments):
    return json.dumps(attachments) if attachments else None


def deserialize_image_attachments(raw_attachments):
    if not raw_attachments:
        return []
    try:
        attachments = json.loads(raw_attachments)
    except (TypeError, ValueError):
        return []
    return attachments if isinstance(attachments, list) else []


def image_urls_for_attachments(attachments):
    urls = []
    for attachment in attachments or []:
        url = attachment.get("image_url") or attachment.get("imageUrl") or attachment.get("url") or attachment.get("data_url")
        if url:
            urls.append(url)
    return urls


def add_image_fields(payload, attachments):
    urls = image_urls_for_attachments(attachments)
    payload["images"] = attachments
    payload["image_urls"] = urls
    if urls:
        payload["image_url"] = urls[0]
        payload["imageUrl"] = urls[0]
    return payload


def append_chat_message(chat, sender_type, content, created_at=None, image_attachments=None):
    timestamp = created_at or utcnow()
    clean_attachments = image_attachments or []
    message = ChatMessage(
        chat=chat,
        sender_type=sender_type,
        content=content or ("[image]" if clean_attachments else ""),
        image_attachments=serialize_image_attachments(clean_attachments),
        created_at=timestamp,
    )
    db.session.add(message)
    chat.last_activity_at = timestamp
    if sender_type == "user":
        chat.last_customer_message = content or ("[image]" if clean_attachments else "")
    return message


def get_chat_preview(chat, latest_message=None):
    if latest_message is not None:
        attachments = deserialize_image_attachments(latest_message.image_attachments)
        if latest_message.content and attachments:
            return f"{latest_message.content} [image]"
        if attachments:
            return "[image]"
        return latest_message.content
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
        (msg.sender_type, msg.content, isoformat_or_none(msg.created_at), msg.image_attachments or "")
        for msg in chat.messages
    }

    for item in transcript or []:
        sender_type = normalize_sender_type(item.get("sender"))
        content = (item.get("content") or "").strip()
        attachments = normalize_image_attachments(item)
        if not content and not attachments:
            continue

        timestamp = parse_timestamp(item.get("timestamp"))
        serialized_attachments = serialize_image_attachments(attachments) or ""
        signature = (sender_type, content or ("[image]" if attachments else ""), isoformat_or_none(timestamp), serialized_attachments)
        if signature in existing_signatures:
            continue

        append_chat_message(chat, sender_type, content, created_at=timestamp, image_attachments=attachments)
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
        "presence_online": bool(getattr(user, "presence_online", False)),
        "max_concurrent_chats": None,
        "unlimited_chats": True,
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
    # Concurrent chat caps are retired — every CSR is unlimited.
    load_pct = min(100, min(40, active_chat_count * 4))
    payload = serialize_user(user)
    payload.update(
        {
            "active_chat_count": active_chat_count,
            "load_pct": load_pct,
            "unlimited_chats": True,
            "max_concurrent_chats": None,
        }
    )
    return payload


def serialize_message(message):
    attachments = deserialize_image_attachments(message.image_attachments)
    return add_image_fields(
        {
            "id": message.id,
            "sender_type": message.sender_type,
            "content": message.content,
            "created_at": isoformat_or_none(message.created_at),
        },
        attachments,
    )


def serialize_chat(chat, current_user, message_count=None, latest_message=None):
    assigned_name = chat.assigned_csr.display_name or chat.assigned_csr.email if chat.assigned_csr else None
    is_csr_actor = isinstance(current_user, User) and getattr(current_user, "role", None) in ASSIGNABLE_ROLES
    is_mine = bool(is_csr_actor and chat.assigned_csr_id == current_user.id)
    is_resolved = chat.status in RESOLVED_CHAT_STATUSES
    if message_count is None:
        message_count = ChatMessage.query.filter_by(chat_id=chat.id).count()

    if is_resolved:
        ownership_bucket = "resolved"
    elif is_mine:
        ownership_bucket = "mine"
    elif chat.assigned_csr_id:
        ownership_bucket = "other"
    else:
        ownership_bucket = "queued"

    # Read-only if the chat is owned by a different CSR, or if it is already
    # resolved. Admins never get the read-only badge because they can always
    # reassign; CSRs who don't own it see it as read-only transcript.
    is_read_only_for_user = bool(
        is_csr_actor
        and not is_mine
        and (chat.assigned_csr_id is not None or is_resolved)
    )

    return {
        "id": chat.id,
        "visitor_id": chat.external_chat_id,
        "external_chat_id": chat.external_chat_id,
        "customer_name": chat.customer_name,
        "customer_email": chat.customer_email,
        "customer_external_user_id": chat.customer_external_user_id,
        "auth_mode": chat.auth_mode,
        "subject": chat.subject,
        "status": chat.status,
        "priority": chat.priority,
        "source": chat.source,
        "reverted_reason": chat.reverted_reason,
        "last_customer_message": chat.last_customer_message,
        "preview": get_chat_preview(chat, latest_message=latest_message),
        "assigned_csr_id": chat.assigned_csr_id,
        "assigned_csr": serialize_user(chat.assigned_csr) if chat.assigned_csr else None,
        "assigned_label": assigned_name,
        "assigned_at": isoformat_or_none(chat.assigned_at),
        "reverted_at": isoformat_or_none(chat.reverted_at),
        "last_activity_at": isoformat_or_none(chat.last_activity_at),
        "resolved_at": isoformat_or_none(chat.resolved_at),
        "message_count": message_count,
        "latest_message_id": latest_message.id if latest_message else None,
        "latest_sender_type": latest_message.sender_type if latest_message else None,
        "ownership_bucket": ownership_bucket,
        "is_active": chat.status in ACTIVE_CHAT_STATUSES,
        "is_resolved": is_resolved,
        "can_open": can_user_open_chat(current_user, chat),
        "can_reply": can_user_reply_to_chat(current_user, chat),
        "can_resolve": bool(current_user and can_user_resolve_chat(current_user, chat) and chat.status in ACTIVE_CHAT_STATUSES),
        "can_claim": bool(is_csr_actor and can_user_claim_chat(current_user, chat) and chat.assigned_csr_id is None),
        "is_mine": is_mine,
        "is_read_only": is_read_only_for_user,
        "lock_reason": build_lock_reason(chat) if is_read_only_for_user else None,
        "authenticated_user_data": chat.authenticated_user_data,
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


ADMIN_DASHBOARD_PAGE_SCOPES = {
    "overview": {"summary", "csr_users", "available_csr_users", "reports"},
    # "credentials": {"integration"},  # Credentials tab temporarily disabled
    "knowledge-base": set(),
    "team": {"csr_users", "available_csr_users", "reports"},
    "tech": set(),
    "chats": {"chats"},
    "chats-active": {"chats"},
    "tickets-current": set(),
    "tickets-old": set(),
    "activity": set(),
    "account": set(),
}

ADMIN_DASHBOARD_NO_POLL_PAGES = {
    "knowledge-base",
    "tech",
    "activity",
    "account",
    "tickets-current",
    "tickets-old",
}


ADMIN_CHATS_DEFAULT_PER_PAGE = 20
ADMIN_CHATS_MAX_PER_PAGE = 100
ADMIN_ACTIVITY_DEFAULT_BATCH = 5
ADMIN_ACTIVITY_MAX_BATCH = 50


def get_message_counts_for_chats(chat_ids):
    """Return {chat_id: message_count} in a single SQL query.

    Avoids the N+1 pattern of calling ``len(chat.messages)`` per chat, which
    otherwise triggers a full transcript load for every row in the ledger.
    """
    if not chat_ids:
        return {}
    rows = (
        db.session.query(ChatMessage.chat_id, func.count(ChatMessage.id))
        .filter(ChatMessage.chat_id.in_(list(chat_ids)))
        .group_by(ChatMessage.chat_id)
        .all()
    )
    return {chat_id: count for chat_id, count in rows}


def get_latest_messages_for_chats(chat_ids):
    """Return {chat_id: latest_message} without loading full transcripts."""
    if not chat_ids:
        return {}
    latest_ids = (
        db.session.query(ChatMessage.chat_id, func.max(ChatMessage.id).label("latest_id"))
        .filter(ChatMessage.chat_id.in_(list(chat_ids)))
        .group_by(ChatMessage.chat_id)
        .subquery()
    )
    rows = (
        db.session.query(ChatMessage)
        .join(latest_ids, ChatMessage.id == latest_ids.c.latest_id)
        .all()
    )
    return {message.chat_id: message for message in rows}


def build_admin_dashboard_payload(current_admin, page=None, chat_page=1, chat_per_page=ADMIN_CHATS_DEFAULT_PER_PAGE):
    scope = ADMIN_DASHBOARD_PAGE_SCOPES.get(page)
    integration = serialize_integration_settings()
    payload = {
        "mode": "admin",
        "current_user": serialize_admin(current_admin),
    }
    include_all = scope is None
    needs_csr_data = include_all or bool(scope & {"summary", "csr_users", "available_csr_users", "reports"})

    csr_users = []
    available_csr_users = []
    resolution_report = {"today_total": 0, "yesterday_total": 0, "leaderboard": []}

    if include_all or "integration" in scope:
        payload["integration"] = integration

    if needs_csr_data:
        support_user_rows = sorted(
            get_support_user_rows(available_only=False, include_inactive=True),
            key=lambda row: (
                (row[0].display_name or row[0].email).lower(),
                row[0].id,
            ),
        )
        csr_users = [serialize_support_user(user, active_chat_count) for user, active_chat_count in support_user_rows]
        available_csr_users = [
            csr
            for csr in csr_users
            if csr["is_active"] and csr["is_available"] and csr["is_online"]
        ]
        resolution_report = build_resolution_report(csr_users)

    if include_all or "summary" in scope:
        registered_csrs = User.query.filter(User.role.in_(ASSIGNABLE_ROLES)).count()
        online_csrs = User.query.filter(
            User.role.in_(ASSIGNABLE_ROLES),
            User.is_active.is_(True),
            *online_presence_filters(User),
        ).count()
        available_csrs = User.query.filter(
            User.role.in_(ASSIGNABLE_ROLES),
            User.is_active.is_(True),
            User.is_available.is_(True),
            *online_presence_filters(User),
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
        payload["summary"] = {
            "registered_csrs": registered_csrs,
            "online_csrs": online_csrs,
            "available_csrs": available_csrs,
            "active_csrs": active_csrs,
            "total_chats": ChatConversation.query.count(),
            "active_chats": ChatConversation.query.filter(ChatConversation.status.in_(ACTIVE_CHAT_STATUSES)).count(),
            "queued_chats": ChatConversation.query.filter_by(status="queued").count(),
            "resolved_chats": ChatConversation.query.filter(ChatConversation.status.in_(RESOLVED_CHAT_STATUSES)).count(),
            "total_capacity": None,
            "used_capacity": sum(csr["active_chat_count"] for csr in csr_users if csr["is_active"]),
            "unlimited_capacity": True,
            "resolved_today": resolution_report["today_total"],
            "resolved_yesterday": resolution_report["yesterday_total"],
        }

    if include_all or "csr_users" in scope:
        payload["csr_users"] = csr_users

    if include_all or "available_csr_users" in scope:
        payload["available_csr_users"] = available_csr_users

    if include_all or "reports" in scope:
        status_breakdown = {
            "queued": ChatConversation.query.filter_by(status="queued").count(),
            "assigned": ChatConversation.query.filter_by(status="assigned").count(),
            "in_progress": ChatConversation.query.filter_by(status="in_progress").count(),
            "resolved": ChatConversation.query.filter(ChatConversation.status.in_(RESOLVED_CHAT_STATUSES)).count(),
        }
        payload["reports"] = {
            "status_breakdown": status_breakdown,
            "resolution_leaderboard": resolution_report["leaderboard"],
        }

    if include_all or "chats" in scope:
        try:
            page_num = max(1, int(chat_page or 1))
        except (TypeError, ValueError):
            page_num = 1
        try:
            per_page = int(chat_per_page or ADMIN_CHATS_DEFAULT_PER_PAGE)
        except (TypeError, ValueError):
            per_page = ADMIN_CHATS_DEFAULT_PER_PAGE
        per_page = max(5, min(ADMIN_CHATS_MAX_PER_PAGE, per_page))

        chats_query = ChatConversation.query.options(joinedload(ChatConversation.assigned_csr))
        # Active Chats page only loads live conversations to keep the payload light.
        if page == "chats-active":
            chats_query = chats_query.filter(ChatConversation.status.in_(ACTIVE_CHAT_STATUSES))
            payload["chat_scope"] = "active"
        else:
            payload["chat_scope"] = "history"

        total_chats_count = chats_query.count()
        total_pages = max(1, (total_chats_count + per_page - 1) // per_page)
        if page_num > total_pages:
            page_num = total_pages
        offset = (page_num - 1) * per_page

        chats = (
            chats_query
            .order_by(
                ChatConversation.last_activity_at.desc(),
                ChatConversation.reverted_at.desc(),
            )
            .offset(offset)
            .limit(per_page)
            .all()
        )
        chat_ids = [chat.id for chat in chats]
        counts = get_message_counts_for_chats(chat_ids)
        latest_messages = get_latest_messages_for_chats(chat_ids)
        payload["chats"] = [
            serialize_chat(
                chat,
                current_admin,
                message_count=counts.get(chat.id, 0),
                latest_message=latest_messages.get(chat.id),
            )
            for chat in chats
        ]
        payload["chats_pagination"] = {
            "page": page_num,
            "per_page": per_page,
            "total": total_chats_count,
            "total_pages": total_pages,
            "has_prev": page_num > 1,
            "has_next": page_num < total_pages,
        }

    if include_all or "recent_activity" in scope:
        payload["recent_activity"] = get_admin_activity_events(
            limit=ADMIN_ACTIVITY_DEFAULT_BATCH,
            offset=0,
        )["events"]

    return payload


def get_admin_activity_events(limit=None, offset=0):
    try:
        batch_limit = int(limit or ADMIN_ACTIVITY_DEFAULT_BATCH)
    except (TypeError, ValueError):
        batch_limit = ADMIN_ACTIVITY_DEFAULT_BATCH
    try:
        batch_offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        batch_offset = 0
    batch_limit = max(1, min(ADMIN_ACTIVITY_MAX_BATCH, batch_limit))

    total = ChatAssignmentEvent.query.count()
    events = (
        ChatAssignmentEvent.query
        .options(
            joinedload(ChatAssignmentEvent.from_csr),
            joinedload(ChatAssignmentEvent.to_csr),
            joinedload(ChatAssignmentEvent.acted_by),
        )
        .order_by(
            ChatAssignmentEvent.created_at.desc(),
            ChatAssignmentEvent.id.desc(),
        )
        .offset(batch_offset)
        .limit(batch_limit)
        .all()
    )
    loaded = batch_offset + len(events)
    return {
        "events": [serialize_assignment_event(event) for event in events],
        "pagination": {
            "total": total,
            "offset": batch_offset,
            "limit": batch_limit,
            "loaded": loaded,
            "has_more": loaded < total,
        },
    }


CSR_ACTIVE_CHATS_LIMIT = 120


def build_csr_dashboard_payload(current_user):
    integration = serialize_integration_settings()
    # Only load OPEN chats on the main dashboard payload so the initial load
    # stays light. Resolved history is fetched on demand via the dedicated
    # paginated endpoint below when the user switches to the "Closed" tab.
    chats = (
        ChatConversation.query
        .options(joinedload(ChatConversation.assigned_csr))
        .filter(
            ChatConversation.status.in_(ACTIVE_CHAT_STATUSES),
            or_(
                ChatConversation.assigned_csr_id.is_(None),
                ChatConversation.assigned_csr_id == current_user.id,
            ),
        )
        .order_by(
            ChatConversation.last_activity_at.desc(),
            ChatConversation.reverted_at.desc(),
        )
        .limit(CSR_ACTIVE_CHATS_LIMIT)
        .all()
    )
    chat_ids = [chat.id for chat in chats]
    chat_counts = get_message_counts_for_chats(chat_ids)
    latest_messages = get_latest_messages_for_chats(chat_ids)

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
            "other_chats": ChatConversation.query.filter(
                ChatConversation.assigned_csr_id.is_not(None),
                ChatConversation.assigned_csr_id != current_user.id,
                ChatConversation.status.in_(ACTIVE_CHAT_STATUSES),
            ).count(),
            "available_csrs": User.query.filter(
                User.is_active.is_(True),
                User.is_available.is_(True),
                User.role.in_(ASSIGNABLE_ROLES),
                *online_presence_filters(User),
            ).count(),
        },
        "csrs": support_users,
        "chats": [
            serialize_chat(
                chat,
                current_user,
                message_count=chat_counts.get(chat.id, 0),
                latest_message=latest_messages.get(chat.id),
            )
            for chat in chats
        ],
    }


def get_request_dashboard_page():
    page = (request.args.get("page") or request.headers.get("X-Admin-Page") or "").strip()
    if page in ADMIN_DASHBOARD_PAGE_SCOPES:
        return page
    return None


def build_dashboard_payload(current_actor, page=None):
    if isinstance(current_actor, AdminAccount):
        return build_admin_dashboard_payload(current_actor, page=page)
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
        add_image_fields(
            {
                "sender": message.sender_type,
                "content": message.content,
                "timestamp": isoformat_or_none(message.created_at),
            },
            deserialize_image_attachments(message.image_attachments),
        )
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
def backfill_chat_external_user_ids():
    """Recover the external user link for chats stored before the ID column."""
    chats = ChatConversation.query.filter(
        ChatConversation.customer_external_user_id.is_(None),
        ChatConversation.authenticated_user_data.is_not(None),
    ).all()
    changed = False
    for chat in chats:
        try:
            authenticated_user = json.loads(chat.authenticated_user_data)
        except (TypeError, ValueError):
            continue
        if not isinstance(authenticated_user, dict):
            continue

        external_user_id = authenticated_user.get("id")
        verification_response = authenticated_user.get("verification_response")
        if external_user_id is None and isinstance(verification_response, dict):
            verified_user = verification_response.get("user")
            if isinstance(verified_user, dict):
                external_user_id = verified_user.get("id")

        if external_user_id is not None:
            chat.customer_external_user_id = str(external_user_id)
            changed = True

    if changed:
        db.session.commit()


def ensure_schema():
    os.makedirs(instance_dir, exist_ok=True)
    db.create_all()
    inspector = inspect(db.engine)
    existing_columns = {column["name"] for column in inspector.get_columns("chat_conversations")}
    column_definitions = {
        "customer_external_user_id": "VARCHAR(120)",
        "auth_mode": "VARCHAR(20) NOT NULL DEFAULT 'anonymous'",
        "authenticated_user_data": "TEXT",
    }
    with db.engine.begin() as connection:
        for column_name, column_definition in column_definitions.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE chat_conversations ADD COLUMN {column_name} {column_definition}")
                )

    backfill_chat_external_user_ids()

    if inspector.has_table("tickets"):
        ticket_columns = {column["name"]: column for column in inspector.get_columns("tickets")}
        with db.engine.begin() as connection:
            if "created_by_admin_id" not in ticket_columns:
                connection.execute(
                    text("ALTER TABLE tickets ADD COLUMN created_by_admin_id INTEGER REFERENCES admin_accounts(id)")
                )
            if "created_by_tech_id" not in ticket_columns:
                connection.execute(
                    text("ALTER TABLE tickets ADD COLUMN created_by_tech_id INTEGER REFERENCES tech_team_accounts(id)")
                )
            if "origin" not in ticket_columns:
                connection.execute(
                    text("ALTER TABLE tickets ADD COLUMN origin VARCHAR(20) NOT NULL DEFAULT 'csr'")
                )
                # Backfill origin from creator columns for existing rows.
                connection.execute(text("""
                    UPDATE tickets
                    SET origin = CASE
                        WHEN created_by_admin_id IS NOT NULL THEN 'admin'
                        WHEN created_by_tech_id IS NOT NULL THEN 'tech'
                        WHEN chat_id IS NOT NULL OR created_by_csr_id IS NOT NULL THEN 'csr'
                        ELSE 'csr'
                    END
                """))
            # Allow admin/tech-created tickets without a CSR creator.
            csr_col = ticket_columns.get("created_by_csr_id")
            if csr_col is not None and not csr_col.get("nullable", True):
                try:
                    connection.execute(text("ALTER TABLE tickets ALTER COLUMN created_by_csr_id DROP NOT NULL"))
                except Exception:
                    pass

    added_user_presence = _ensure_presence_online_column("users")
    added_tech_presence = _ensure_presence_online_column("tech_team_accounts")
    if added_user_presence or added_tech_presence:
        cutoff = get_online_cutoff()
        if added_user_presence:
            User.query.filter(User.last_seen_at.is_not(None), User.last_seen_at >= cutoff).update(
                {User.presence_online: True},
                synchronize_session=False,
            )
        if added_tech_presence:
            TechTeamAccount.query.filter(
                TechTeamAccount.last_seen_at.is_not(None),
                TechTeamAccount.last_seen_at >= cutoff,
            ).update(
                {TechTeamAccount.presence_online: True},
                synchronize_session=False,
            )
        db.session.commit()


def _ensure_presence_online_column(table_name):
    inspector = inspect(db.engine)
    if not inspector.has_table(table_name):
        return False
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "presence_online" in columns:
        return False
    with db.engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN presence_online BOOLEAN NOT NULL DEFAULT FALSE")
        )
    return True


def generate_ticket_number():
    """Build code PREFIX_NUMBER — e.g. TCK_4821, FLT_25656. Prefix is from a fixed pool; digits are random each time."""
    prefix = random.choice(TICKET_CODE_PREFIXES)
    digits = random.randint(1000, 999999)
    return f"{prefix}_{digits}"


def generate_unique_ticket_number(max_attempts=30):
    for _ in range(max_attempts):
        candidate = generate_ticket_number()
        if not Ticket.query.filter_by(ticket_number=candidate).first():
            return candidate
    return f"TCK_{random.randint(100000, 999999)}"


def find_email_owner(email):
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return None

    admin = AdminAccount.query.filter_by(email=normalized_email).first()
    if admin:
        return {
            "type": "admin",
            "label": "Admin",
            "id": admin.id,
            "display_name": admin.display_name or admin.email,
        }

    user = User.query.filter_by(email=normalized_email).first()
    if user:
        role_label = "CSR" if normalize_role(user.role) == "csr" else normalize_role(user.role).replace("_", " ").title()
        return {
            "type": "user",
            "label": role_label,
            "id": user.id,
            "display_name": user.display_name or user.email,
        }

    tech = TechTeamAccount.query.filter_by(email=normalized_email).first()
    if tech:
        return {
            "type": "tech",
            "label": "Technical Team",
            "id": tech.id,
            "display_name": tech.display_name or tech.email,
        }

    return None


def email_in_use(email):
    return bool(find_email_owner(email))


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


def seed_dummy_users():
    """Seed a dummy CSR and admin for local testing if no users exist."""
    dummy_csr = User.query.filter_by(email="dummy.csr@example.test").first()
    if not dummy_csr:
        dummy_csr = User(
            email="dummy.csr@example.test",
            display_name="Dummy CSR",
            role="csr",
            is_active=True,
            is_available=True,
            max_concurrent_chats=DEFAULT_MAX_CONCURRENT_CHATS,
            unlimited_chats=True,
        )
        dummy_csr.set_password("dummy123")
        db.session.add(dummy_csr)

    dummy_admin = AdminAccount.query.filter_by(email="dummy.admin@example.test").first()
    if not dummy_admin:
        dummy_admin = AdminAccount(
            email="dummy.admin@example.test",
            display_name="Dummy Admin",
        )
        dummy_admin.set_password("dummy123")
        db.session.add(dummy_admin)

    db.session.commit()


def bootstrap_users():
    migrate_legacy_admins()

    users = User.query.order_by(User.created_at.asc(), User.id.asc()).all()
    if not users:
        seed_dummy_users()
        users = User.query.order_by(User.created_at.asc(), User.id.asc()).all()

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
            # All CSRs are unlimited concurrent chat handlers.
            user.unlimited_chats = True
            if not user.max_concurrent_chats or user.max_concurrent_chats < 1:
                user.max_concurrent_chats = DEFAULT_MAX_CONCURRENT_CHATS

    db.session.commit()


# ─── Auth Routes ─────────────────────────────────────────────
@app.route("/")
def index():
    current_actor = get_current_user()
    if current_actor:
        return redirect(url_for(dashboard_endpoint_for(current_actor)))
    if get_current_tech_user():
        return redirect(url_for("tech_dashboard"))
    return redirect(url_for("login"))


@app.route("/csr/dashboard")
@csr_required
def csr_dashboard():
    return render_template("csr_dashboard.html", user=get_current_csr_user())


def render_admin_dashboard_page(page, title, copy):
    return render_template(
        "admin_dashboard.html",
        user=get_current_admin(),
        admin_page=page,
        admin_page_title=title,
        admin_page_copy=copy,
        dashboard_enabled=page not in ADMIN_DASHBOARD_NO_POLL_PAGES,
        knowledge_base_updater_url=KNOWLEDGE_BASE_UPDATER_URL,
    )


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return redirect(url_for("admin_overview"))


@app.route("/admin/dashboard/overview")
@admin_required
def admin_overview():
    return render_admin_dashboard_page(
        "overview",
        "Admin Operations Overview",
        "Live metrics, CSR coverage, and resolution trends for the support team.",
    )


# Credentials tab temporarily disabled
# @app.route("/admin/dashboard/credentials")
# @admin_required
# def admin_credentials():
#     return render_admin_dashboard_page(
#         "credentials",
#         "Integration Credentials",
#         "Manage widget settings, embed configuration, and generated CSR preview output.",
#     )


@app.route("/admin/dashboard/knowledge-base")
@admin_required
def admin_knowledge_base():
    return render_admin_dashboard_page(
        "knowledge-base",
        "Knowledge Base",
        "Upload buyer, organizer, and policy knowledge files using the hosted uploader form.",
    )


@app.route("/admin/dashboard/team")
@admin_required
def admin_team():
    return render_admin_dashboard_page(
        "team",
        "CSR Management",
        "Create CSR accounts, review live availability, and adjust each agent's workload controls.",
    )


@app.route("/admin/dashboard/chats")
@admin_required
def admin_chats():
    return render_admin_dashboard_page(
        "chats",
        "Chat History",
        "Browse stored conversations, review transcripts, and remove chat records when necessary.",
    )


@app.route("/admin/dashboard/chats/active")
@admin_required
def admin_chats_active():
    return render_admin_dashboard_page(
        "chats-active",
        "Active Chats",
        "Live view of queued, assigned, and in-progress chats across the support team.",
    )


@app.route("/admin/dashboard/tickets/current")
@admin_required
def admin_tickets_current():
    return render_admin_dashboard_page(
        "tickets-current",
        "Current Tickets",
        "Open and in-progress technical tickets. Create new tickets as a super admin.",
    )


@app.route("/admin/dashboard/tickets/old")
@admin_required
def admin_tickets_old():
    return render_admin_dashboard_page(
        "tickets-old",
        "Old Tickets",
        "Completed and closed technical tickets for audit and history.",
    )


@app.route("/admin/dashboard/activity")
@admin_required
def admin_activity():
    return render_admin_dashboard_page(
        "activity",
        "Activity Timeline",
        "Load the latest workflow events in small batches to keep the page fast.",
    )


@app.route("/api/admin/activity-events")
@admin_required
def admin_activity_events():
    return jsonify(
        get_admin_activity_events(
            limit=request.args.get("limit", ADMIN_ACTIVITY_DEFAULT_BATCH),
            offset=request.args.get("offset", 0),
        )
    )


@app.route("/admin/dashboard/account")
@admin_required
def admin_account():
    return render_admin_dashboard_page(
        "account",
        "Account Settings",
        "View your administrator profile and manage your session.",
    )


@app.route("/admin/dashboard/tech")
@admin_required
def admin_tech():
    return render_admin_dashboard_page(
        "tech",
        "Technical Team Management",
        "Manage technical team accounts, customize ticket statuses, and view ticket analytics.",
    )


def handle_signup(role=None):
    auth_role = normalize_role(role or request.values.get("role"), default="csr")
    if auth_role != "admin":
        flash("CSR accounts are created by an administrator from the admin dashboard.", "error")
        return redirect(url_for("csr_login"))

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
            unlimited_chats=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("CSR account created successfully! Please log in.", "success")
        return redirect(url_for("csr_login"))

    return render_template("signup.html", **auth_context(auth_role))


def portal_login_page():
    if get_current_user():
        return redirect(url_for(dashboard_endpoint_for(get_current_user())))
    if get_current_tech_user():
        return redirect(url_for("tech_dashboard"))
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    return redirect(url_for("admin_signup"))


@app.route("/admin/signup", methods=["GET", "POST"])
def admin_signup():
    return handle_signup("admin")


@app.route("/csr/signup", methods=["GET", "POST"])
def csr_signup():
    flash("CSR accounts are created by an administrator from the admin dashboard.", "error")
    return redirect(url_for("csr_login"))


@app.route("/login", methods=["GET"])
def login():
    return portal_login_page()


@app.route("/admin/forgot-password", methods=["GET", "POST"])
def admin_forgot_password():
    if get_current_admin():
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template("admin_forgot_password.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("admin_forgot_password.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("admin_forgot_password.html")

        admin = AdminAccount.query.filter_by(email=email).first()
        if not admin:
            flash("No administrator account was found for that email address.", "error")
            return render_template("admin_forgot_password.html")

        admin.set_password(password)
        db.session.commit()
        flash("Password updated successfully. You can now sign in.", "success")
        return redirect(url_for("admin_login"))

    return render_template("admin_forgot_password.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if get_current_admin():
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("admin_login.html")

        admin = AdminAccount.query.filter_by(email=email).first()
        if not admin or not admin.check_password(password):
            flash("Invalid admin email or password.", "error")
            return render_template("admin_login.html")

        admin.last_seen_at = utcnow()
        db.session.commit()
        session.permanent = True
        session["account_type"] = "admin"
        session["admin_id"] = admin.id
        session["user_email"] = admin.email
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_login.html")


@app.route("/csr/login", methods=["GET", "POST"])
def csr_login():
    if get_current_csr_user():
        return redirect(url_for("csr_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("csr_login.html")

        user = User.query.filter_by(email=email, role="csr").first()
        if not user or not user.check_password(password):
            flash("Invalid CSR email or password.", "error")
            return render_template("csr_login.html")

        user.last_seen_at = utcnow()
        user.presence_online = True
        db.session.commit()
        session.permanent = True
        session["account_type"] = "csr"
        session["csr_user_id"] = user.id
        session["user_email"] = user.email
        return redirect(url_for("csr_dashboard"))

    return render_template("csr_login.html")


@app.route("/csr/forgot-password")
def csr_forgot_password():
    """CSR accounts are provisioned and reset by administrators."""
    if get_current_csr_user():
        return redirect(url_for("csr_dashboard"))
    return render_template("csr_forgot_password.html")


@app.route("/logout")
def logout():
    # Legacy route: end only the identity that most recently opened a portal.
    role = session.get("account_type")
    if role == "tech":
        tech = get_current_tech_user()
        if tech:
            finalize_tech_presence(tech)
    elif role == "csr":
        csr = get_current_csr_user()
        if csr:
            finalize_user_presence(csr)
    elif role == "admin":
        admin = get_current_admin()
        if admin:
            finalize_admin_presence(admin)
    else:
        role = "csr" if get_current_csr_user() else "admin" if get_current_admin() else "tech"

    clear_portal_session(role)
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/csr/logout")
def csr_logout():
    csr = get_current_csr_user()
    if csr:
        finalize_user_presence(csr)
    clear_portal_session("csr")
    session.modified = True
    flash("You have been logged out of the CSR portal.", "success")
    response = redirect(url_for("csr_login"))
    # Prevent browser back/forward cache from restoring a logged-in dashboard.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Clear-Site-Data"] = '"cache"'
    return response


@app.route("/admin/logout")
def admin_logout():
    admin = get_current_admin()
    if admin:
        finalize_admin_presence(admin)
    clear_portal_session("admin")
    session.modified = True
    flash("You have been logged out of the admin portal.", "success")
    response = redirect(url_for("admin_login"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Clear-Site-Data"] = '"cache"'
    return response


@app.route("/tech/login", methods=["GET", "POST"])
def tech_login():
    if get_current_tech_user():
        return redirect(url_for("tech_dashboard"))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("tech_login.html")
        
        tech = TechTeamAccount.query.filter_by(email=email).first()
        if not tech or not tech.check_password(password):
            flash("Invalid technical team email or password.", "error")
            return render_template("tech_login.html")
        if not tech.is_active:
            flash("Your technical team account is disabled. Contact an administrator.", "error")
            return render_template("tech_login.html")
        
        tech.last_seen_at = utcnow()
        tech.presence_online = True
        db.session.commit()
        session.permanent = True
        session["account_type"] = "tech"
        session["tech_user_id"] = tech.id
        session["user_email"] = tech.email
        return redirect(url_for("tech_dashboard"))
    
    return render_template("tech_login.html")


@app.route("/tech/logout")
def tech_logout():
    tech = get_current_tech_user()
    if tech:
        finalize_tech_presence(tech)
    clear_portal_session("tech")
    session.modified = True
    flash("You have been logged out of the technical portal.", "success")
    response = redirect(url_for("tech_login"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Clear-Site-Data"] = '"cache"'
    return response


@app.route("/api/csr/heartbeat", methods=["POST"])
@csr_required
def csr_heartbeat():
    """Keep CSR presence online while dashboard is open."""
    user = get_current_csr_user()
    touch_user_presence(user, force=True)
    return jsonify({
        "success": True,
        "is_online": True,
        "last_seen_at": isoformat_or_none(user.last_seen_at),
        "online_window_seconds": CSR_ONLINE_WINDOW_SECONDS,
    })


@app.route("/api/csr/presence/offline", methods=["POST"])
def csr_presence_offline():
    """Mark CSR offline on logout or browser/tab close."""
    user = get_current_csr_user()
    if user:
        mark_user_offline(user)
    return jsonify({"success": True, "is_online": False})


@app.route("/api/tech/heartbeat", methods=["POST"])
@tech_required
def tech_heartbeat():
    """Keep technical team presence online while dashboard is open."""
    tech = get_current_tech_user()
    touch_tech_presence(tech, force=True)
    return jsonify({
        "success": True,
        "is_online": True,
        "last_seen_at": isoformat_or_none(tech.last_seen_at),
        "online_window_seconds": CSR_ONLINE_WINDOW_SECONDS,
    })


@app.route("/api/tech/presence/offline", methods=["POST"])
def tech_presence_offline():
    """Mark technical team offline on logout or browser/tab close."""
    tech = get_current_tech_user()
    if tech:
        mark_tech_offline(tech)
    return jsonify({"success": True, "is_online": False})


@app.route("/tech/dashboard")
@tech_required
def tech_dashboard():
    return render_template("tech_dashboard.html", user=get_current_tech_user())


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
    authentication = payload.get("authentication") or {}
    if not isinstance(authentication, dict):
        authentication = {}
    auth_mode = str(authentication.get("mode") or "anonymous").strip().lower()
    authenticated_user = authentication.get("user")
    if auth_mode not in {"anonymous", "authenticated"}:
        auth_mode = "anonymous"
    if not isinstance(authenticated_user, dict):
        authenticated_user = None

    if not visitor_id:
        return jsonify({"success": False, "message": "visitor_id is required"}), 400

    now = utcnow()
    chat = find_chat_by_visitor_id(visitor_id)
    reset_existing = False

    if not chat:
        chat = ChatConversation(
            external_chat_id=visitor_id,
            customer_name=(
                str(authenticated_user.get("name") or visitor_id)
                if authenticated_user
                else visitor_id
            ),
            customer_email=(
                str(authenticated_user.get("email") or "").strip() or None
                if authenticated_user
                else None
            ),
            customer_external_user_id=(
                str(authenticated_user.get("id"))
                if authenticated_user and authenticated_user.get("id") is not None
                else None
            ),
            auth_mode=auth_mode,
            authenticated_user_data=json.dumps(authenticated_user) if authenticated_user else None,
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

        if authenticated_user:
            chat.customer_name = str(authenticated_user.get("name") or chat.customer_name or visitor_id)
            chat.customer_email = str(authenticated_user.get("email") or "").strip() or chat.customer_email
            if authenticated_user.get("id") is not None:
                chat.customer_external_user_id = str(authenticated_user["id"])
            chat.authenticated_user_data = json.dumps(authenticated_user)
        else:
            chat.customer_name = chat.customer_name or visitor_id
        chat.auth_mode = auth_mode
        chat.subject = chat.subject or "Incoming QSTP widget handoff"
        chat.source = "qstp_widget"
        chat.reverted_reason = "AI escalated this conversation to a human CSR."
        chat.reverted_at = now
        chat.last_activity_at = now

    import_transcript(chat, transcript, reset_existing=reset_existing)

    latest_user_messages = [item.get("content") for item in transcript if normalize_sender_type(item.get("sender")) == "user"]
    if latest_user_messages:
        chat.last_customer_message = latest_user_messages[-1]

    # Super-CSR model: no auto-assignment. The chat stays in the shared queue
    # and is claimed by the first CSR who clicks it from their dashboard.
    if chat.status in RESOLVED_CHAT_STATUSES:
        chat.assigned_csr_id = None
        chat.assigned_at = None
        chat.status = "queued"

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
    attachments = normalize_image_attachments(payload)

    if not visitor_id or (not content and not attachments):
        return jsonify({"success": False, "message": "visitor_id and content or image are required"}), 400

    chat = find_chat_by_visitor_id(visitor_id)
    if not chat:
        return jsonify({"success": False, "message": "Chat session not found"}), 404

    append_chat_message(chat, "user", content, image_attachments=attachments)
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
    current_user = get_current_user()
    if isinstance(current_user, AdminAccount):
        return jsonify(
            build_admin_dashboard_payload(
                current_user,
                request.args.get("page"),
                chat_page=request.args.get("chat_page", 1),
                chat_per_page=request.args.get("per_page", ADMIN_CHATS_DEFAULT_PER_PAGE),
            )
        )
    return jsonify(build_csr_dashboard_payload(current_user))


@app.route("/api/csr/chats/resolved")
@login_required
def csr_resolved_chats():
    """Paginated access to closed/resolved chats for the CSR dashboard.

    Query params:
      - page (1-based, default 1)
      - per_page (default 20, max 50)
    """
    current_user = get_current_user()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", 20))
    except (TypeError, ValueError):
        per_page = 20
    per_page = max(5, min(per_page, 50))

    base_query = (
        ChatConversation.query
        .filter(ChatConversation.status.in_(RESOLVED_CHAT_STATUSES))
    )
    total = base_query.count()
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    chats = (
        base_query
        .options(joinedload(ChatConversation.assigned_csr))
        .order_by(
            ChatConversation.last_activity_at.desc(),
            ChatConversation.reverted_at.desc(),
        )
        .offset(offset)
        .limit(per_page)
        .all()
    )
    chat_counts = get_message_counts_for_chats([chat.id for chat in chats])
    latest_messages = get_latest_messages_for_chats([chat.id for chat in chats])

    return jsonify({
        "chats": [
            serialize_chat(
                chat,
                current_user,
                message_count=chat_counts.get(chat.id, 0),
                latest_message=latest_messages.get(chat.id),
            )
            for chat in chats
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        },
    })


@app.route("/api/csr/chats/others")
@csr_required
def csr_other_chats():
    """Paginated teammate chats (assigned to other CSRs) for the Others tab."""
    current_user = get_current_csr_user()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", 10))
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(5, min(per_page, 50))

    date_raw = (request.args.get("date") or "").strip()
    day_start = day_end = None
    if date_raw:
        try:
            day = datetime.strptime(date_raw, "%Y-%m-%d").date()
            day_start = datetime.combine(day, datetime.min.time())
            day_end = datetime.combine(day, datetime.max.time())
        except ValueError:
            return jsonify({"error": "Invalid date. Use YYYY-MM-DD."}), 400

    base_query = (
        ChatConversation.query
        .filter(
            ChatConversation.status.in_(ACTIVE_CHAT_STATUSES),
            ChatConversation.assigned_csr_id.is_not(None),
            ChatConversation.assigned_csr_id != current_user.id,
        )
    )
    if day_start and day_end:
        base_query = base_query.filter(
            ChatConversation.last_activity_at >= day_start,
            ChatConversation.last_activity_at <= day_end,
        )

    total = base_query.count()
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    page = min(page, total_pages) if total else 1
    offset = (page - 1) * per_page

    chats = (
        base_query
        .options(joinedload(ChatConversation.assigned_csr))
        .order_by(
            ChatConversation.last_activity_at.desc(),
            ChatConversation.reverted_at.desc(),
        )
        .offset(offset)
        .limit(per_page)
        .all()
    )
    chat_counts = get_message_counts_for_chats([chat.id for chat in chats])
    latest_messages = get_latest_messages_for_chats([chat.id for chat in chats])

    return jsonify({
        "chats": [
            serialize_chat(
                chat,
                current_user,
                message_count=chat_counts.get(chat.id, 0),
                latest_message=latest_messages.get(chat.id),
            )
            for chat in chats
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "has_more": page < total_pages,
            "date": date_raw or None,
        },
    })


@app.route("/api/chats/<int:chat_id>/messages")
@login_required
def chat_messages(chat_id):
    current_user = get_current_user()
    chat = (
        ChatConversation.query
        .options(
            joinedload(ChatConversation.assigned_csr),
            selectinload(ChatConversation.messages),
            selectinload(ChatConversation.assignment_events).joinedload(ChatAssignmentEvent.from_csr),
            selectinload(ChatConversation.assignment_events).joinedload(ChatAssignmentEvent.to_csr),
            selectinload(ChatConversation.assignment_events).joinedload(ChatAssignmentEvent.acted_by),
        )
        .filter_by(id=chat_id)
        .first()
    )
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    # Super-CSR viewing: any authenticated CSR or admin can read the transcript.
    # Ownership still gates replying and resolving on the write endpoints.
    latest_message = chat.messages[-1] if chat.messages else None
    return jsonify(
        {
            "chat": serialize_chat(
                chat,
                current_user,
                message_count=len(chat.messages),
                latest_message=latest_message,
            ),
            "messages": [serialize_message(message) for message in chat.messages],
            "events": [serialize_assignment_event(event) for event in chat.assignment_events],
        }
    )


@app.route("/api/chats/<int:chat_id>/claim", methods=["POST"])
@csr_required
def claim_chat_endpoint(chat_id):
    """Click-to-claim: the first CSR to open a queued chat becomes its owner.

    If the chat is already owned by another CSR, the claim is rejected with
    409 so the client can fall back to the read-only view.
    """
    current_user = get_current_csr_user()
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    if chat.status in RESOLVED_CHAT_STATUSES:
        return jsonify({"error": "This chat is already resolved and cannot be claimed."}), 400

    if chat.assigned_csr_id and chat.assigned_csr_id != current_user.id:
        owner = chat.assigned_csr
        return jsonify(
            {
                "error": "This chat is already claimed by another CSR.",
                "assigned_csr": serialize_user(owner) if owner else None,
                "chat": serialize_chat(chat, current_user),
            }
        ), 409

    ok, error = claim_chat(chat, current_user)
    if not ok:
        db.session.rollback()
        return jsonify({"error": error, "chat": serialize_chat(chat, current_user)}), 409

    db.session.commit()
    return jsonify(
        {
            "success": True,
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

    return jsonify({"success": True, "relay": relay_result, "dashboard": build_dashboard_payload(current_user, page=get_request_dashboard_page())})


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
            "dashboard": build_dashboard_payload(current_user, page=get_request_dashboard_page()),
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

    return jsonify({
        "success": True,
        "message": "Chat reassigned.",
        "dashboard": build_dashboard_payload(current_user, page=get_request_dashboard_page()),
    })


@app.route("/api/chats/rebalance", methods=["POST"])
@admin_required
def rebalance_chats():
    current_user = get_current_admin()
    assigned_count = rebalance_queued_chats(actor=current_user)
    return jsonify({"success": True, "assigned_count": assigned_count, "dashboard": build_dashboard_payload(current_user, page=get_request_dashboard_page())})


@app.route("/api/csrs/<int:user_id>/settings", methods=["POST"])
@admin_required
def update_csr_settings(user_id):
    current_user = get_current_admin()
    csr_user = db.session.get(User, user_id)
    if not csr_user or csr_user.role not in ASSIGNABLE_ROLES:
        return jsonify({"error": "CSR not found."}), 404

    payload = get_request_payload()
    csr_user.is_available = parse_bool(payload.get("is_available"), default=csr_user.is_available)
    # Concurrent caps removed — always keep CSRs unlimited.
    csr_user.unlimited_chats = True
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "CSR availability saved successfully.",
        "dashboard": build_dashboard_payload(current_user, page=get_request_dashboard_page()),
    })


@app.route("/api/csrs/<int:user_id>/password", methods=["POST"])
@admin_required
def reset_csr_password(user_id):
    """Allow an administrator to reset a CSR password from the roster."""
    csr_user = db.session.get(User, user_id)
    if not csr_user or csr_user.role not in ASSIGNABLE_ROLES:
        return jsonify({"error": "CSR not found."}), 404

    password = get_request_payload().get("password") or ""
    if len(password) < 6:
        return jsonify({"error": "CSR password must be at least 6 characters."}), 400

    csr_user.set_password(password)
    db.session.commit()
    return jsonify({"success": True, "message": "CSR password updated."})


@app.route("/api/admin/csrs/create", methods=["POST"])
@admin_required
def create_csr_account():
    current_admin = get_current_admin()
    payload = get_request_payload()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    display_name = (payload.get("display_name") or "").strip()
    is_available = parse_bool(payload.get("is_available"), default=True)

    if not email or not password:
        return jsonify({"error": "CSR email and password are required."}), 400

    if len(password) < 6:
        return jsonify({"error": "CSR password must be at least 6 characters."}), 400

    owner = find_email_owner(email)
    if owner:
        return jsonify({
            "error": (
                f"This email is already used by a {owner['label']} account"
                f" ({owner['display_name']}). Use a different email."
            )
        }), 400

    csr_user = User(
        email=email,
        display_name=display_name or derive_display_name(email),
        role="csr",
        is_active=True,
        is_available=is_available,
        max_concurrent_chats=DEFAULT_MAX_CONCURRENT_CHATS,
        unlimited_chats=True,
    )
    csr_user.set_password(password)
    db.session.add(csr_user)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "User added successfully.",
            "dashboard": build_dashboard_payload(current_admin, page=get_request_dashboard_page()),
        }
    )


# Credentials tab temporarily disabled
# @app.route("/api/admin/integration-settings", methods=["POST"])
# @admin_required
# def update_integration_settings():
#     current_admin = get_current_admin()
#     payload = get_request_payload()
#
#     settings = normalize_integration_settings(
#         {
#             "page_title": payload.get("page_title"),
#             "base_url": payload.get("base_url"),
#             "container_id": payload.get("container_id"),
#             "csr_key": payload.get("csr_key"),
#             "widget_title": payload.get("widget_title"),
#             "primary_color": payload.get("primary_color"),
#             "auto_activate": payload.get("auto_activate"),
#             "chat_list_poll": payload.get("chat_list_poll"),
#             "message_poll": payload.get("message_poll"),
#             "script_src": payload.get("script_src"),
#             "relay_api_url": payload.get("relay_api_url"),
#             "relay_api_key": payload.get("relay_api_key"),
#         }
#     )
#
#     if not settings["base_url"]:
#         return jsonify({"error": "Base URL is required."}), 400
#     if not settings["csr_key"]:
#         return jsonify({"error": "CSR key is required."}), 400
#     if not settings["script_src"]:
#         return jsonify({"error": "Script source is required."}), 400
#
#     sync_integration_settings_artifacts(settings)
#
#     return jsonify(
#         {
#             "success": True,
#             "message": "CSR integration settings saved to the server file.",
#             "dashboard": build_dashboard_payload(current_admin, page=get_request_dashboard_page()),
#         }
#     )


# ─── Ticket API ──────────────────────────────────────────────

def serialize_tech_account_brief(tech):
    if not tech:
        return None
    return {
        "id": tech.id,
        "email": tech.email,
        "display_name": tech.display_name or tech.email,
        "specialty": tech.specialty,
        "is_active": tech.is_active,
        "is_online": is_tech_online(tech),
        "presence_online": bool(getattr(tech, "presence_online", False)),
        "last_seen_at": isoformat_or_none(tech.last_seen_at),
    }


def serialize_ticket_log(log, tech_lookup=None):
    tech_lookup = tech_lookup or {}
    old_tech = tech_lookup.get(log.old_assigned_tech_id) if log.old_assigned_tech_id else None
    new_tech = tech_lookup.get(log.new_assigned_tech_id) if log.new_assigned_tech_id else None
    changed_by_tech = (
        tech_lookup.get(log.changed_by_user_id)
        if log.changed_by_role == "tech" and log.changed_by_user_id
        else None
    )
    is_assignment_change = log.old_assigned_tech_id != log.new_assigned_tech_id and (
        log.old_assigned_tech_id is not None or log.new_assigned_tech_id is not None
    )
    return {
        "id": log.id,
        "old_status": log.old_status,
        "new_status": log.new_status,
        "old_assigned_tech_id": log.old_assigned_tech_id,
        "new_assigned_tech_id": log.new_assigned_tech_id,
        "old_assigned_tech": serialize_tech_account_brief(old_tech),
        "new_assigned_tech": serialize_tech_account_brief(new_tech),
        "changed_by_user_id": log.changed_by_user_id,
        "changed_by_role": log.changed_by_role,
        "changed_by_name": (
            (changed_by_tech.display_name or changed_by_tech.email)
            if changed_by_tech else None
        ),
        "notes": log.notes,
        "created_at": isoformat_or_none(log.created_at),
        "is_assignment_change": is_assignment_change,
    }


def serialize_chat_ticket_ref(chat):
    if not chat:
        return None
    return {
        "id": chat.id,
        "external_chat_id": chat.external_chat_id,
        "visitor_id": chat.external_chat_id,
        "customer_name": chat.customer_name,
        "visitor_name": chat.customer_name,
        "status": chat.status,
        "customer_external_user_id": chat.customer_external_user_id,
        "auth_mode": chat.auth_mode,
        "authenticated_user_data": chat.authenticated_user_data,
    }


def resolve_ticket_origin(ticket):
    origin = (getattr(ticket, "origin", None) or "").strip().lower()
    if origin in {"csr", "admin", "tech"}:
        return origin
    if getattr(ticket, "created_by_admin_id", None):
        return "admin"
    if getattr(ticket, "created_by_tech_id", None):
        return "tech"
    return "csr"


def ticket_creator_payload(ticket):
    origin = resolve_ticket_origin(ticket)
    created_by_tech = getattr(ticket, "created_by_tech", None)
    created_by_admin = getattr(ticket, "created_by_admin", None)
    created_by_csr = getattr(ticket, "created_by_csr", None)
    if origin == "tech" and created_by_tech:
        label = created_by_tech.display_name or created_by_tech.email
        role = "tech"
    elif origin == "admin" and created_by_admin:
        label = created_by_admin.display_name or created_by_admin.email
        role = "admin"
    elif created_by_csr:
        label = created_by_csr.display_name or created_by_csr.email
        role = "csr"
    elif created_by_admin:
        label = created_by_admin.display_name or created_by_admin.email
        role = "admin"
    elif created_by_tech:
        label = created_by_tech.display_name or created_by_tech.email
        role = "tech"
    else:
        label = "Unknown"
        role = origin or None
    return {
        "origin": origin,
        "is_chat_linked": bool(ticket.chat_id) and origin == "csr",
        "created_by_csr_id": ticket.created_by_csr_id,
        "created_by_csr": serialize_user(created_by_csr) if created_by_csr else None,
        "created_by_admin_id": ticket.created_by_admin_id,
        "created_by_admin": serialize_admin(created_by_admin) if created_by_admin else None,
        "created_by_tech_id": getattr(ticket, "created_by_tech_id", None),
        "created_by_tech": serialize_tech_account_brief(created_by_tech) if created_by_tech else None,
        "created_by_label": label,
        "created_by_role": role,
    }


def serialize_ticket(ticket, include_messages=False, include_admin_details=False):
    tech_ids = {
        tech_id
        for log in (ticket.status_logs or [])
        for tech_id in (
            log.old_assigned_tech_id,
            log.new_assigned_tech_id,
            log.changed_by_user_id if log.changed_by_role == "tech" else None,
        )
        if tech_id
    }
    tech_lookup = {
        tech.id: tech
        for tech in TechTeamAccount.query.filter(TechTeamAccount.id.in_(tech_ids)).all()
    } if tech_ids else {}
    history = [serialize_ticket_log(log, tech_lookup) for log in (ticket.status_logs or [])]
    assignment_history = [item for item in history if item.get("is_assignment_change")]
    latest_message = max(
        ticket.messages or [],
        key=lambda message: (message.created_at, message.id),
        default=None,
    )
    creator = ticket_creator_payload(ticket)
    data = {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number or f"TCK_{ticket.id}",
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        **creator,
        "chat_id": ticket.chat_id if creator["is_chat_linked"] else None,
        "chat": serialize_chat_ticket_ref(ticket.chat_conversation) if creator["is_chat_linked"] else None,
        "assigned_tech_id": ticket.assigned_tech_id,
        "assigned_tech": serialize_tech_account_brief(ticket.assigned_tech),
        "history": history,
        "assignment_history": assignment_history,
        "last_assignment_update": assignment_history[0] if assignment_history else None,
        "created_at": isoformat_or_none(ticket.created_at),
        "updated_at": isoformat_or_none(ticket.updated_at),
        "resolved_at": isoformat_or_none(ticket.resolved_at),
        "message_count": len(ticket.messages) if ticket.messages else 0,
        "latest_message_id": latest_message.id if latest_message else None,
        "latest_message_sender_type": latest_message.sender_type if latest_message else None,
    }
    if include_messages:
        data["messages"] = [
            {
                "id": m.id,
                "sender_type": m.sender_type,
                "sender_id": m.sender_id,
                "sender_name": m.sender_name,
                "content": m.content,
                "created_at": isoformat_or_none(m.created_at),
            }
            for m in ticket.messages
        ]
    if include_admin_details:
        latest_log = ticket.status_logs[0] if ticket.status_logs else None
        if latest_log:
            latest_serialized_log = serialize_ticket_log(latest_log, tech_lookup)
            latest_serialized_log["at"] = latest_serialized_log["created_at"]
            data["last_status_update"] = latest_serialized_log
    return data


def get_ticket_message_counts(ticket_ids):
    if not ticket_ids:
        return {}
    rows = (
        db.session.query(TicketMessage.ticket_id, func.count(TicketMessage.id))
        .filter(TicketMessage.ticket_id.in_(list(ticket_ids)))
        .group_by(TicketMessage.ticket_id)
        .all()
    )
    return {ticket_id: count for ticket_id, count in rows}


def get_latest_ticket_messages(ticket_ids):
    if not ticket_ids:
        return {}
    latest_ids = (
        db.session.query(TicketMessage.ticket_id, func.max(TicketMessage.id).label("latest_id"))
        .filter(TicketMessage.ticket_id.in_(list(ticket_ids)))
        .group_by(TicketMessage.ticket_id)
        .subquery()
    )
    rows = (
        db.session.query(TicketMessage)
        .join(latest_ids, TicketMessage.id == latest_ids.c.latest_id)
        .all()
    )
    return {message.ticket_id: message for message in rows}


def get_latest_ticket_logs(ticket_ids, assignment_only=False):
    if not ticket_ids:
        return {}
    base_query = db.session.query(TicketStatusLog.ticket_id, func.max(TicketStatusLog.id).label("latest_id")).filter(
        TicketStatusLog.ticket_id.in_(list(ticket_ids))
    )
    if assignment_only:
        base_query = base_query.filter(
            TicketStatusLog.old_assigned_tech_id.is_distinct_from(TicketStatusLog.new_assigned_tech_id),
            or_(
                TicketStatusLog.old_assigned_tech_id.is_not(None),
                TicketStatusLog.new_assigned_tech_id.is_not(None),
            ),
        )
    latest_ids = base_query.group_by(TicketStatusLog.ticket_id).subquery()
    rows = (
        db.session.query(TicketStatusLog)
        .join(latest_ids, TicketStatusLog.id == latest_ids.c.latest_id)
        .all()
    )
    return {log.ticket_id: log for log in rows}


def serialize_ticket_summary(ticket, message_count=0, latest_message=None, latest_log=None, assignment_log=None):
    logs = [log for log in (latest_log, assignment_log) if log is not None]
    tech_ids = {
        tech_id
        for log in logs
        for tech_id in (
            log.old_assigned_tech_id,
            log.new_assigned_tech_id,
            log.changed_by_user_id if log.changed_by_role == "tech" else None,
        )
        if tech_id
    }
    tech_lookup = {
        tech.id: tech
        for tech in TechTeamAccount.query.filter(TechTeamAccount.id.in_(tech_ids)).all()
    } if tech_ids else {}
    assignment_history = [serialize_ticket_log(assignment_log, tech_lookup)] if assignment_log else []
    creator = ticket_creator_payload(ticket)
    data = {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number or f"TCK_{ticket.id}",
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        **creator,
        "chat_id": ticket.chat_id if creator["is_chat_linked"] else None,
        "chat": serialize_chat_ticket_ref(ticket.chat_conversation) if creator["is_chat_linked"] else None,
        "assigned_tech_id": ticket.assigned_tech_id,
        "assigned_tech": serialize_tech_account_brief(ticket.assigned_tech),
        "assignment_history": assignment_history,
        "last_assignment_update": assignment_history[0] if assignment_history else None,
        "created_at": isoformat_or_none(ticket.created_at),
        "updated_at": isoformat_or_none(ticket.updated_at),
        "resolved_at": isoformat_or_none(ticket.resolved_at),
        "message_count": message_count,
        "latest_message_id": latest_message.id if latest_message else None,
        "latest_message_sender_type": latest_message.sender_type if latest_message else None,
    }
    if latest_log:
        latest_serialized_log = serialize_ticket_log(latest_log, tech_lookup)
        latest_serialized_log["at"] = latest_serialized_log["created_at"]
        data["last_status_update"] = latest_serialized_log
    return data


def ticket_query_with_relations():
    return Ticket.query.options(
        joinedload(Ticket.created_by_csr),
        joinedload(Ticket.created_by_admin),
        joinedload(Ticket.created_by_tech),
        joinedload(Ticket.chat_conversation),
        joinedload(Ticket.assigned_tech),
        joinedload(Ticket.messages),
        joinedload(Ticket.status_logs),
    )


def resolved_ticket_status_names(statuses=None):
    rows = statuses if statuses is not None else TicketStatus.query.all()
    names = {s.name for s in rows if s.is_resolved}
    return names | {"resolved", "closed"}


def build_admin_ticket_stats(tickets, statuses):
    resolved_statuses = {s.name for s in statuses if s.is_resolved}
    closed_like = resolved_statuses | {"closed", "resolved"}
    return {
        "total": len(tickets),
        "open": sum(1 for t in tickets if t.status == "open"),
        "in_progress": sum(1 for t in tickets if t.status == "in_progress"),
        "waiting_parts": sum(1 for t in tickets if t.status == "waiting_parts"),
        "closed": sum(1 for t in tickets if t.status in closed_like),
        "unassigned": sum(1 for t in tickets if not t.assigned_tech_id and t.status not in closed_like),
    }


def build_tech_workload(tickets, tech_accounts):
    now = utcnow()
    workload = {
        t.id: {
            "tech_id": t.id,
            "display_name": t.display_name or t.email,
            "email": t.email,
            "specialty": t.specialty,
            "is_active": t.is_active,
            "is_online": is_tech_online(t, now=now),
            "last_seen_at": isoformat_or_none(t.last_seen_at),
            "total_assigned": 0,
            "open": 0,
            "in_progress": 0,
            "active": 0,
        }
        for t in tech_accounts
    }
    active_statuses = {"open", "in_progress", "waiting_parts"}
    for ticket in tickets:
        if not ticket.assigned_tech_id:
            continue
        row = workload.get(ticket.assigned_tech_id)
        if not row:
            continue
        row["total_assigned"] += 1
        if ticket.status == "open":
            row["open"] += 1
        if ticket.status == "in_progress":
            row["in_progress"] += 1
        if ticket.status in active_statuses:
            row["active"] += 1
    return sorted(workload.values(), key=lambda item: (-item["active"], item["display_name"]))


def serialize_ticket_status(status):
    return {
        "id": status.id,
        "name": status.name,
        "label": normalize_ticket_status_label(status.label),
        "color": status.color,
        "sort_order": status.sort_order,
        "is_default": status.is_default,
        "is_resolved": status.is_resolved,
    }


def serialize_integration_ticket(ticket):
    """Ticket payload safe for buyer/organizer integrations."""
    origin = resolve_ticket_origin(ticket)
    linked_chat = ticket.chat_conversation if origin == "csr" else None
    assigned_tech = ticket.assigned_tech
    creator_account = {
        "csr": ticket.created_by_csr,
        "admin": ticket.created_by_admin,
        "tech": ticket.created_by_tech,
    }.get(origin)
    creator_name = getattr(creator_account, "display_name", None) or {
        "csr": "Customer Support",
        "admin": "Admin",
        "tech": "Technical Team",
    }.get(origin, "Unknown")
    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number or f"TCK_{ticket.id}",
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "origin": origin,
        "is_admin_generated": origin == "admin",
        "is_chat_linked": bool(linked_chat),
        "chat_id": linked_chat.id if linked_chat else None,
        "customer_external_user_id": (
            linked_chat.customer_external_user_id if linked_chat else None
        ),
        "created_by": {
            "role": origin,
            "name": creator_name,
        },
        "assigned_tech": (
            {
                "id": assigned_tech.id,
                "name": assigned_tech.display_name or "Technical Team",
                "specialty": assigned_tech.specialty,
            }
            if assigned_tech
            else None
        ),
        "created_at": isoformat_or_none(ticket.created_at),
        "updated_at": isoformat_or_none(ticket.updated_at),
        "resolved_at": isoformat_or_none(ticket.resolved_at),
    }


def integration_ticket_query():
    return Ticket.query.options(
        joinedload(Ticket.created_by_csr),
        joinedload(Ticket.created_by_admin),
        joinedload(Ticket.created_by_tech),
        joinedload(Ticket.chat_conversation),
        joinedload(Ticket.assigned_tech),
    )


def tickets_linked_to_external_user(query, external_user_id):
    """Find CSR chat tickets for a widget/FLT user id."""
    external_user_id = str(external_user_id or "").strip()
    id_values = {external_user_id}
    if external_user_id.isdigit():
        id_values.add(str(int(external_user_id)))

    json_matchers = []
    for user_id in id_values:
        json_matchers.extend(
            [
                ChatConversation.authenticated_user_data.contains(f'"id": "{user_id}"'),
                ChatConversation.authenticated_user_data.contains(f'"id": {user_id}'),
                ChatConversation.authenticated_user_data.contains(f'"id":{user_id}'),
            ]
        )

    return query.join(ChatConversation, Ticket.chat_id == ChatConversation.id).filter(
        Ticket.origin == "csr",
        or_(
            ChatConversation.customer_external_user_id.in_(list(id_values)),
            *json_matchers,
        ),
    )


def external_user_id_candidates(external_user_id):
    value = str(external_user_id or "").strip()
    candidates = {value} if value else set()
    if value.isdigit():
        candidates.add(str(int(value)))
    return candidates


def load_ticket_by_ref(ticket_ref):
    ticket_ref = str(ticket_ref or "").strip()
    if not ticket_ref:
        return None
    if ticket_ref.isdigit():
        ticket = db.session.get(Ticket, int(ticket_ref))
        if ticket:
            return ticket
    return Ticket.query.filter(func.lower(Ticket.ticket_number) == ticket_ref.lower()).first()


def ticket_belongs_to_external_user(ticket, external_user_id):
    if not ticket or resolve_ticket_origin(ticket) != "csr":
        return False
    chat = ticket.chat_conversation
    if not chat:
        return False
    id_values = external_user_id_candidates(external_user_id)
    if chat.customer_external_user_id in id_values:
        return True
    raw = chat.authenticated_user_data or ""
    return any(
        f'"id": "{user_id}"' in raw or f'"id": {user_id}' in raw or f'"id":{user_id}' in raw
        for user_id in id_values
    )


def resolve_named_ticket_status(status_value):
    raw = (status_value or "").strip()
    if not raw:
        return None
    slug = raw.lower().replace(" ", "_").replace("-", "_")
    for row in TicketStatus.query.all():
        if row.name.lower() == slug:
            return row
        if normalize_ticket_status_label(row.label).lower() == raw.lower():
            return row
    return None


def integration_ticket_response(query, filters=None):
    try:
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "limit and offset must be integers."}), 400

    limit = max(1, min(limit, 300))
    offset = max(0, offset)
    status_filter = (request.args.get("status") or "").strip()
    if status_filter:
        query = query.filter(Ticket.status == status_filter)

    total = query.order_by(None).count()
    tickets = (
        query.order_by(Ticket.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return jsonify({
        "tickets": [serialize_integration_ticket(ticket) for ticket in tickets],
        "filters": filters or {},
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(tickets) < total,
        },
    })


@app.route("/api/integration/tickets", methods=["GET"])
@tickets_api_required
def integration_get_all_tickets():
    """Return tickets for a trusted organizer/backend integration.

    Optional filters:
    - user_id: FLT widget user id (buyer/organizer), e.g. 139006
    - origin: csr | admin | tech
    """
    query = integration_ticket_query()
    filters = {}
    user_id = (
        request.args.get("user_id")
        or request.args.get("customer_external_user_id")
        or ""
    ).strip()
    origin = (request.args.get("origin") or "").strip().lower()

    if user_id:
        query = tickets_linked_to_external_user(query, user_id)
        filters["customer_external_user_id"] = user_id
    elif origin in {"csr", "admin", "tech"}:
        query = query.filter(Ticket.origin == origin)
        filters["origin"] = origin

    return integration_ticket_response(query, filters)


@app.route("/api/integration/tickets/users/<string:external_user_id>", methods=["GET"])
@tickets_api_required
def integration_get_user_tickets(external_user_id):
    """Return tickets linked to an authenticated external user through chats."""
    external_user_id = external_user_id.strip()
    if not external_user_id:
        return jsonify({"error": "external_user_id is required."}), 400

    query = tickets_linked_to_external_user(integration_ticket_query(), external_user_id)
    return integration_ticket_response(
        query,
        filters={"customer_external_user_id": external_user_id},
    )


@app.route("/api/integration/tickets/admin-generated", methods=["GET"])
@tickets_api_required
def integration_get_admin_tickets():
    """Return tickets created independently by administrators."""
    query = integration_ticket_query().filter(Ticket.origin == "admin")
    return integration_ticket_response(query, filters={"origin": "admin"})


@app.route("/api/integration/tickets/<string:ticket_ref>/status", methods=["POST"])
@tickets_api_required
def integration_update_user_ticket_status(ticket_ref):
    """Let a buyer/organizer update status only on a ticket linked to their user id."""
    payload = get_request_payload()
    user_id = str(
        payload.get("user_id")
        or payload.get("customer_external_user_id")
        or request.args.get("user_id")
        or request.args.get("customer_external_user_id")
        or ""
    ).strip()
    new_status = str(payload.get("status") or "").strip()
    notes = str(payload.get("notes") or "").strip()

    if not user_id:
        return jsonify({"error": "user_id is required."}), 400
    if not new_status:
        return jsonify({"error": "status is required."}), 400

    ticket = load_ticket_by_ref(ticket_ref)
    if not ticket:
        return jsonify({"error": "Ticket not found."}), 404
    if not ticket_belongs_to_external_user(ticket, user_id):
        return jsonify({"error": "This ticket does not belong to this user."}), 403

    status_obj = resolve_named_ticket_status(new_status)
    if not status_obj:
        return jsonify({"error": f"Invalid status: {new_status}"}), 400

    old_status = ticket.status
    if old_status == status_obj.name:
        return jsonify({
            "success": True,
            "message": f"Ticket already has status {status_obj.label}.",
            "ticket": serialize_integration_ticket(ticket),
        })

    ticket.status = status_obj.name
    ticket.updated_at = utcnow()
    if status_obj.is_resolved:
        ticket.resolved_at = utcnow()
    else:
        ticket.resolved_at = None

    changed_by_user_id = int(user_id) if user_id.isdigit() else None
    db.session.add(
        TicketStatusLog(
            ticket_id=ticket.id,
            old_status=old_status,
            new_status=status_obj.name,
            old_assigned_tech_id=ticket.assigned_tech_id,
            new_assigned_tech_id=ticket.assigned_tech_id,
            changed_by_user_id=changed_by_user_id,
            changed_by_role="user",
            notes=notes or f"Status updated by user {user_id}.",
        )
    )
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Ticket status updated to {status_obj.label}.",
        "ticket": serialize_integration_ticket(ticket),
    })


@app.route("/api/tickets", methods=["GET"])
@login_required
def get_tickets():
    """Get tickets based on user role."""
    tech_user = get_current_tech_user()
    admin_user = get_current_admin()
    csr_user = get_current_csr_user()
    status_filter = request.args.get("status")
    chat_id_filter = request.args.get("chat_id", type=int)

    if tech_user:
        # Tech users can see every ticket. Client-side tabs (Queue / Mine / All)
        # handle filtering, so the API always returns the full list to keep the
        # "All" tab and the counts accurate. An optional status filter is still
        # honored when explicitly requested.
        query = ticket_query_with_relations()
        if status_filter:
            query = query.filter(Ticket.status == status_filter)
        tickets = query.order_by(Ticket.updated_at.desc()).all()
    elif admin_user:
        query = ticket_query_with_relations()
        if status_filter and status_filter != "all":
            query = query.filter(Ticket.status == status_filter)
        tickets = query.order_by(Ticket.updated_at.desc()).all()
    elif csr_user:
        query = ticket_query_with_relations()
        if chat_id_filter:
            query = query.filter(Ticket.chat_id == chat_id_filter)
        tickets = query.order_by(Ticket.updated_at.desc()).all()
    else:
        return jsonify({"error": "Unauthorized."}), 403

    statuses = TicketStatus.query.order_by(TicketStatus.sort_order.asc()).all()
    include_admin = bool(admin_user)

    return jsonify({
        "tickets": [serialize_ticket(t, include_admin_details=include_admin) for t in tickets],
        "statuses": [serialize_ticket_status(s) for s in statuses],
    })


@app.route("/api/chats/<int:chat_id>/tickets", methods=["GET"])
@csr_required
def get_chat_tickets(chat_id):
    """Return technical tickets linked to a customer chat."""
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    tickets = (
        ticket_query_with_relations()
        .filter(Ticket.chat_id == chat_id)
        .order_by(Ticket.updated_at.desc())
        .all()
    )
    statuses = TicketStatus.query.order_by(TicketStatus.sort_order.asc()).all()
    return jsonify({
        "chat": serialize_chat_ticket_ref(chat),
        "tickets": [serialize_ticket(t) for t in tickets],
        "statuses": [serialize_ticket_status(s) for s in statuses],
    })


@app.route("/api/admin/tickets", methods=["GET"])
@admin_required
def admin_get_tickets():
    """Admin overview: tickets (optionally scoped), stats, and per-tech workload."""
    status_filter = (request.args.get("status") or "all").strip()
    lifecycle = (request.args.get("lifecycle") or "all").strip().lower()
    include_workload = (request.args.get("include_workload") or "1").strip() != "0"
    include_stats = (request.args.get("include_stats") or "1").strip() != "0"
    try:
        ticket_offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        ticket_offset = 0
    try:
        ticket_limit = int(request.args.get("limit", 300))
    except (TypeError, ValueError):
        ticket_limit = 300
    ticket_limit = max(1, min(ticket_limit, 300))

    statuses = TicketStatus.query.order_by(TicketStatus.sort_order.asc()).all()
    resolved_names = resolved_ticket_status_names(statuses)
    want_list = lifecycle in {"current", "old"} or status_filter not in {"", "all"} or not (include_stats or include_workload)

    all_tickets = None
    if include_stats or include_workload:
        all_tickets = (
            Ticket.query
            .options(joinedload(Ticket.assigned_tech))
            .order_by(Ticket.updated_at.desc())
            .all()
        )

    tickets = []
    ticket_total = 0
    if want_list or not (include_stats or include_workload):
        list_query = Ticket.query.options(
            joinedload(Ticket.created_by_csr),
            joinedload(Ticket.created_by_admin),
            joinedload(Ticket.created_by_tech),
            joinedload(Ticket.assigned_tech),
        )
        # An explicit status selection is authoritative. This lets the
        # Current Tickets page show a selected Closed/Resolved record instead
        # of applying the page's default active-ticket scope and producing an
        # empty intersection. With "All statuses", retain each page's normal
        # lifecycle scope (active on Current, completed on Old).
        if status_filter and status_filter != "all":
            list_query = list_query.filter(Ticket.status == status_filter)
        elif lifecycle == "current":
            list_query = list_query.filter(~Ticket.status.in_(list(resolved_names)))
        elif lifecycle == "old":
            list_query = list_query.filter(Ticket.status.in_(list(resolved_names)))
        ticket_total = list_query.order_by(None).count()
        tickets = list_query.order_by(Ticket.updated_at.desc()).offset(ticket_offset).limit(ticket_limit).all()

    ticket_ids = [ticket.id for ticket in tickets]
    message_counts = get_ticket_message_counts(ticket_ids)
    latest_messages = get_latest_ticket_messages(ticket_ids)
    latest_logs = get_latest_ticket_logs(ticket_ids)
    latest_assignment_logs = get_latest_ticket_logs(ticket_ids, assignment_only=True)

    payload = {
        "tickets": [
            serialize_ticket_summary(
                ticket,
                message_count=message_counts.get(ticket.id, 0),
                latest_message=latest_messages.get(ticket.id),
                latest_log=latest_logs.get(ticket.id),
                assignment_log=latest_assignment_logs.get(ticket.id),
            )
            for ticket in tickets
        ],
        "statuses": [serialize_ticket_status(s) for s in statuses],
        "lifecycle": lifecycle,
        "pagination": {
            "offset": ticket_offset,
            "limit": ticket_limit,
            "total": ticket_total,
            "has_more": ticket_offset + len(tickets) < ticket_total,
        },
    }
    if include_stats:
        payload["stats"] = build_admin_ticket_stats(all_tickets or tickets, statuses)
    if include_workload:
        tech_accounts = TechTeamAccount.query.order_by(TechTeamAccount.display_name.asc()).all()
        payload["tech_workload"] = build_tech_workload(all_tickets or tickets, tech_accounts)
    return jsonify(payload)


@app.route("/api/admin/tickets", methods=["POST"])
@admin_required
def admin_create_ticket():
    """Super-admin creates an independent technical ticket (not linked to CSR chats)."""
    current_admin = get_current_admin()
    payload = get_request_payload()

    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    priority = (payload.get("priority") or "normal").strip().lower() or "normal"

    if not title:
        return jsonify({"error": "Ticket title is required."}), 400
    if priority not in {"low", "normal", "high", "urgent"}:
        priority = "normal"

    # Admin tickets are independent of CSR chat tickets.
    ticket = Ticket(
        ticket_number=generate_unique_ticket_number(),
        title=title,
        description=description,
        priority=priority,
        status="open",
        origin="admin",
        created_by_csr_id=None,
        created_by_admin_id=current_admin.id,
        created_by_tech_id=None,
        chat_id=None,
    )
    db.session.add(ticket)
    db.session.flush()

    log = TicketStatusLog(
        ticket_id=ticket.id,
        old_status=None,
        new_status="open",
        changed_by_user_id=None,
        changed_by_role="admin",
        notes=f"Independent admin ticket {ticket.ticket_number} created by {current_admin.display_name or current_admin.email}.",
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Ticket {ticket.ticket_number} created successfully.",
        "ticket": serialize_ticket(ticket, include_admin_details=True),
    })


@app.route("/api/tech/tech-accounts", methods=["GET"])
@tech_required
def get_active_tech_accounts_for_handoff():
    """Return active technical team accounts for ticket referral."""
    techs = (
        TechTeamAccount.query
        .filter_by(is_active=True)
        .order_by(TechTeamAccount.display_name.asc(), TechTeamAccount.email.asc())
        .all()
    )
    return jsonify({"techs": [serialize_tech_account_brief(t) for t in techs]})


@app.route("/api/tech/tickets", methods=["POST"])
@tech_required
def tech_create_ticket():
    """Technical team creates an independent ticket (not linked to a CSR chat)."""
    tech_user = get_current_tech_user()
    payload = get_request_payload()

    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    priority = (payload.get("priority") or "normal").strip().lower() or "normal"
    assign_mode = (payload.get("assign_mode") or "me").strip().lower()
    notes = (payload.get("notes") or "").strip()

    if not title:
        return jsonify({"error": "Ticket title is required."}), 400
    if priority not in {"low", "normal", "high", "urgent"}:
        priority = "normal"
    if assign_mode not in {"me", "queue", "tech"}:
        assign_mode = "me"

    assigned_tech = None
    if assign_mode == "me":
        assigned_tech = tech_user
    elif assign_mode == "tech":
        try:
            target_id = int(payload.get("assign_tech_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Select a technical person to assign."}), 400
        assigned_tech = db.session.get(TechTeamAccount, target_id)
        if not assigned_tech or not assigned_tech.is_active:
            return jsonify({"error": "Selected technical person is not active."}), 400

    status = "in_progress" if assigned_tech else "open"
    ticket = Ticket(
        ticket_number=generate_unique_ticket_number(),
        title=title,
        description=description,
        priority=priority,
        status=status,
        origin="tech",
        created_by_csr_id=None,
        created_by_admin_id=None,
        created_by_tech_id=tech_user.id,
        chat_id=None,
        assigned_tech_id=assigned_tech.id if assigned_tech else None,
    )
    db.session.add(ticket)
    db.session.flush()

    creator_name = tech_user.display_name or tech_user.email
    create_notes = notes or f"Independent tech ticket created by {creator_name}."
    db.session.add(
        TicketStatusLog(
            ticket_id=ticket.id,
            old_status=None,
            new_status="open",
            old_assigned_tech_id=None,
            new_assigned_tech_id=None,
            changed_by_user_id=tech_user.id,
            changed_by_role="tech",
            notes=create_notes,
        )
    )
    if assigned_tech:
        assign_name = assigned_tech.display_name or assigned_tech.email
        if assigned_tech.id == tech_user.id:
            assign_note = f"Self-assigned by {creator_name}."
        else:
            assign_note = f"Assigned by {creator_name} to {assign_name}."
        db.session.add(
            TicketStatusLog(
                ticket_id=ticket.id,
                old_status="open",
                new_status=status,
                old_assigned_tech_id=None,
                new_assigned_tech_id=assigned_tech.id,
                changed_by_user_id=tech_user.id,
                changed_by_role="tech",
                notes=assign_note,
            )
        )

    db.session.commit()
    return jsonify({
        "success": True,
        "message": f"Ticket {ticket.ticket_number} created successfully.",
        "ticket": serialize_ticket(ticket),
    })


@app.route("/api/tickets", methods=["POST"])
@csr_required
def create_ticket():
    """CSR creates a chat-linked ticket for a specific customer conversation."""
    current_user = get_current_csr_user()
    payload = get_request_payload()
    
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    priority = payload.get("priority", "normal")
    chat_id = payload.get("chat_id")
    
    if not title:
        return jsonify({"error": "Ticket title is required."}), 400
    if chat_id in (None, "", 0, "0"):
        return jsonify({"error": "CSR tickets must be linked to a specific chat."}), 400

    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid chat_id."}), 400
    chat = db.session.get(ChatConversation, chat_id)
    if not chat:
        return jsonify({"error": "Linked chat not found."}), 404
    
    ticket = Ticket(
        ticket_number=generate_unique_ticket_number(),
        title=title,
        description=description,
        priority=priority,
        status="open",
        origin="csr",
        created_by_csr_id=current_user.id,
        created_by_admin_id=None,
        created_by_tech_id=None,
        chat_id=chat.id,
    )
    db.session.add(ticket)
    db.session.flush()
    
    # Log the creation
    log = TicketStatusLog(
        ticket_id=ticket.id,
        old_status=None,
        new_status="open",
        changed_by_user_id=current_user.id,
        changed_by_role="csr",
        notes=f"CSR chat ticket {ticket.ticket_number} created for chat {chat.external_chat_id}.",
    )
    db.session.add(log)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Ticket {ticket.ticket_number} created successfully.",
        "ticket": serialize_ticket(ticket),
    })


@app.route("/api/tickets/<int:ticket_id>/claim", methods=["POST"])
@tech_required
def claim_ticket(ticket_id):
    """Technical team member claims an open ticket."""
    tech_user = get_current_tech_user()
    # Lock the ticket while assigning it. This makes simultaneous button clicks
    # safe and avoids a valid technician receiving a misleading denial.
    ticket = Ticket.query.filter_by(id=ticket_id).with_for_update().first()
    
    if not ticket:
        return jsonify({"error": "Ticket not found."}), 404
    
    if ticket.assigned_tech_id:
        if ticket.assigned_tech_id == tech_user.id:
            return jsonify({
                "success": True,
                "message": "This ticket is already assigned to you.",
                "ticket": serialize_ticket(ticket),
            })
        return jsonify({"error": "This ticket has already been claimed by another technical team member."}), 409

    if ticket.status != "open":
        return jsonify({"error": "This ticket is no longer open and cannot be claimed."}), 409
    
    old_status = ticket.status
    ticket.assigned_tech_id = tech_user.id
    ticket.status = "in_progress"
    
    log = TicketStatusLog(
        ticket_id=ticket.id,
        old_status=old_status,
        new_status="in_progress",
        old_assigned_tech_id=None,
        new_assigned_tech_id=tech_user.id,
        changed_by_user_id=tech_user.id,
        changed_by_role="tech",
        notes=f"Claimed by {tech_user.display_name or tech_user.email}",
    )
    db.session.add(log)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "Ticket claimed successfully.",
        "ticket": serialize_ticket(ticket),
    })


@app.route("/api/tickets/<int:ticket_id>/refer", methods=["POST"])
@tech_required
def refer_ticket(ticket_id):
    """Refer a ticket from the assigned tech to another active tech."""
    tech_user = get_current_tech_user()
    ticket = db.session.get(Ticket, ticket_id)

    if not ticket:
        return jsonify({"error": "Ticket not found."}), 404

    if ticket.assigned_tech_id != tech_user.id:
        return jsonify({"error": "You can only refer tickets assigned to you."}), 403

    payload = get_request_payload()
    target_tech_id = payload.get("target_tech_id")
    notes = (payload.get("notes") or "").strip()

    try:
        target_tech_id = int(target_tech_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Select the technical person to refer this ticket to."}), 400

    if target_tech_id == tech_user.id:
        return jsonify({"error": "Choose a different technical person."}), 400

    target_tech = db.session.get(TechTeamAccount, target_tech_id)
    if not target_tech or not target_tech.is_active:
        return jsonify({"error": "Selected technical person is not active."}), 400

    status_obj = TicketStatus.query.filter_by(name=ticket.status).first()
    if status_obj and status_obj.is_resolved:
        return jsonify({"error": "Resolved tickets cannot be referred."}), 400

    previous_tech_id = ticket.assigned_tech_id
    previous_name = tech_user.display_name or tech_user.email
    target_name = target_tech.display_name or target_tech.email
    ticket.assigned_tech_id = target_tech.id
    ticket.updated_at = utcnow()

    log = TicketStatusLog(
        ticket_id=ticket.id,
        old_status=ticket.status,
        new_status=ticket.status,
        old_assigned_tech_id=previous_tech_id,
        new_assigned_tech_id=target_tech.id,
        changed_by_user_id=tech_user.id,
        changed_by_role="tech",
        notes=notes or f"Ticket referred from {previous_name} to {target_name}.",
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": f"Ticket referred to {target_name}.",
        "ticket": serialize_ticket(ticket),
    })


@app.route("/api/tickets/<int:ticket_id>/status", methods=["POST"])
@tech_required
def update_ticket_status(ticket_id):
    """Update ticket status (tech team only, and only for their claimed tickets)."""
    tech_user = get_current_tech_user()
    ticket = db.session.get(Ticket, ticket_id)
    
    if not ticket:
        return jsonify({"error": "Ticket not found."}), 404
    
    if ticket.assigned_tech_id != tech_user.id:
        return jsonify({"error": "You can only update tickets assigned to you."}), 403
    
    payload = get_request_payload()
    new_status = (payload.get("status") or "").strip()
    notes = (payload.get("notes") or "").strip()
    
    if not new_status:
        return jsonify({"error": "Status is required."}), 400

    if not notes:
        return jsonify({"error": "Notes are required when updating ticket status."}), 400
    
    # Verify status exists
    status_exists = TicketStatus.query.filter_by(name=new_status).first()
    if not status_exists:
        return jsonify({"error": f"Invalid status: {new_status}"}), 400
    
    old_status = ticket.status
    ticket.status = new_status
    
    if status_exists.is_resolved:
        ticket.resolved_at = utcnow()
    
    log = TicketStatusLog(
        ticket_id=ticket.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_user_id=tech_user.id,
        changed_by_role="tech",
        notes=notes,
    )
    db.session.add(log)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Ticket status updated to {status_exists.label}.",
        "ticket": serialize_ticket(ticket),
    })


def serialize_ticket_message(message):
    return {
        "id": message.id,
        "ticket_id": message.ticket_id,
        "sender_type": message.sender_type,
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "content": message.content,
        "created_at": isoformat_or_none(message.created_at),
    }


def ticket_chat_actor(ticket):
    """Return (allowed, actor, sender_type) for ticket CSR↔tech chat."""
    tech_user = get_current_tech_user()
    csr_user = get_current_csr_user()
    preferred_role = (request.headers.get("X-Portal") or session.get("account_type") or "").strip().lower()

    # Respect the portal that made the request when both identities are
    # present in one browser session. Otherwise a CSR tab can accidentally
    # write a message as the technical user (or vice versa).
    if preferred_role == "tech" and tech_user:
        return True, tech_user, "tech"
    if preferred_role == "csr" and csr_user:
        return True, csr_user, "csr"
    if tech_user:
        return True, tech_user, "tech"
    if csr_user:
        return True, csr_user, "csr"
    return False, None, None


@app.route("/api/tickets/<int:ticket_id>/messages", methods=["GET"])
@login_required
def get_ticket_messages(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found."}), 404

    allowed, _, _ = ticket_chat_actor(ticket)
    if not allowed:
        return jsonify({"error": "You do not have access to this ticket."}), 403

    messages = (
        TicketMessage.query.filter_by(ticket_id=ticket.id)
        .order_by(TicketMessage.created_at.asc())
        .all()
    )
    return jsonify({
        "ticket": serialize_ticket(ticket),
        "messages": [serialize_ticket_message(m) for m in messages],
    })


@app.route("/api/tickets/<int:ticket_id>/messages", methods=["POST"])
@login_required
def send_ticket_message(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found."}), 404

    allowed, actor, sender_type = ticket_chat_actor(ticket)
    if not allowed:
        return jsonify({"error": "You do not have access to this ticket."}), 403

    payload = get_request_payload()
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Message content is required."}), 400

    message = TicketMessage(
        ticket_id=ticket.id,
        sender_type=sender_type,
        sender_id=actor.id,
        sender_name=actor_display_name(actor),
        content=content,
    )
    db.session.add(message)
    ticket.updated_at = utcnow()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": serialize_ticket_message(message),
    })


@app.route("/api/ticket-statuses", methods=["GET"])
@login_required
def get_ticket_statuses():
    """Get all available ticket statuses."""
    statuses = TicketStatus.query.order_by(TicketStatus.sort_order.asc()).all()
    return jsonify({
        "statuses": [serialize_ticket_status(s) for s in statuses],
    })


@app.route("/api/admin/ticket-statuses", methods=["POST"])
@admin_required
def create_ticket_status():
    """Admin creates a new ticket status."""
    payload = get_request_payload()
    name = (payload.get("name") or "").strip().lower()
    label = normalize_ticket_status_label(payload.get("label"))
    color = (payload.get("color") or "#64748b").strip()
    sort_order = parse_int(payload.get("sort_order"), 10)
    is_resolved = parse_bool(payload.get("is_resolved"), default=False)
    
    if not name or not label:
        return jsonify({"error": "Name and label are required."}), 400
    
    if TicketStatus.query.filter_by(name=name).first():
        return jsonify({"error": f"Status '{name}' already exists."}), 400
    
    status = TicketStatus(
        name=name,
        label=label,
        color=color,
        sort_order=sort_order,
        is_default=False,
        is_resolved=is_resolved,
    )
    db.session.add(status)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Status '{label}' created successfully.",
        "status": serialize_ticket_status(status),
    })


@app.route("/api/admin/tech-accounts", methods=["POST"])
@admin_required
def create_tech_account():
    """Admin creates a technical team account."""
    payload = get_request_payload()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    display_name = (payload.get("display_name") or "").strip()
    specialty = (payload.get("specialty") or "General").strip()
    
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    
    owner = find_email_owner(email)
    if owner:
        return jsonify({
            "error": (
                f"This email is already used by a {owner['label']} account"
                f" ({owner['display_name']}). Use a different email."
            )
        }), 400
    
    tech = TechTeamAccount(
        email=email,
        display_name=display_name or derive_display_name(email),
        specialty=specialty,
        is_active=True,
    )
    tech.set_password(password)
    db.session.add(tech)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "This email is already used by another technical team account."}), 400
    
    return jsonify({
        "success": True,
        "message": "User added successfully.",
        "tech": {
            "id": tech.id,
            "email": tech.email,
            "display_name": tech.display_name,
            "specialty": tech.specialty,
            "is_active": tech.is_active,
            "is_online": False,
            "last_seen_at": None,
        },
    })


@app.route("/api/admin/tech-accounts/<int:tech_id>", methods=["PUT"])
@admin_required
def update_tech_account(tech_id):
    """Admin updates a technical team account."""
    tech = db.session.get(TechTeamAccount, tech_id)
    if not tech:
        return jsonify({"error": "Technical team account not found."}), 404
    
    payload = get_request_payload()
    if "display_name" in payload:
        tech.display_name = (payload.get("display_name") or "").strip()
    if "specialty" in payload:
        tech.specialty = (payload.get("specialty") or "General").strip()
    if "is_active" in payload:
        tech.is_active = parse_bool(payload.get("is_active"), default=True)
        if not tech.is_active:
            tech.presence_online = False
            tech.last_seen_at = utcnow()
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": "Technical team account updated.",
    })


@app.route("/api/admin/tech-accounts/<int:tech_id>", methods=["DELETE"])
@admin_required
def delete_tech_account(tech_id):
    """Admin deletes a technical team account without orphaning tickets."""
    tech = db.session.get(TechTeamAccount, tech_id)
    if not tech:
        return jsonify({"error": "Technical team account not found."}), 404

    # Keep ticket history, but release this technician's active work back to
    # the queue and clear nullable creator/assignment references before the
    # account row is removed. Without this, the database FK can reject the
    # delete and the UI only receives a generic request failure.
    assigned_tickets = Ticket.query.filter_by(assigned_tech_id=tech_id).all()
    created_tickets = Ticket.query.filter_by(created_by_tech_id=tech_id).all()
    for ticket in assigned_tickets:
        ticket.assigned_tech_id = None
        if ticket.status in {"assigned", "in_progress"}:
            ticket.status = "open"
            ticket.resolved_at = None
        ticket.updated_at = utcnow()
    for ticket in created_tickets:
        ticket.created_by_tech_id = None

    db.session.delete(tech)
    db.session.commit()

    released_count = len({ticket.id for ticket in assigned_tickets})
    message = "Technical team account deleted."
    if released_count:
        message += f" {released_count} ticket{' was' if released_count == 1 else 's were'} returned to the queue."
    return jsonify({
        "success": True,
        "message": message,
    })


@app.route("/api/admin/presence", methods=["GET"])
@admin_required
def admin_presence_snapshot():
    """Lightweight live Online/Offline snapshot for CSR and technical team."""
    now = utcnow()
    csrs = User.query.filter(User.role.in_(ASSIGNABLE_ROLES)).all()
    techs = TechTeamAccount.query.all()
    return jsonify({
        "csrs": [
            {
                "id": user.id,
                "is_online": is_user_online(user, now=now),
                "last_seen_at": isoformat_or_none(user.last_seen_at),
            }
            for user in csrs
        ],
        "techs": [
            {
                "id": tech.id,
                "is_online": is_tech_online(tech, now=now),
                "last_seen_at": isoformat_or_none(tech.last_seen_at),
            }
            for tech in techs
        ],
        "summary": {
            "online_csrs": sum(1 for user in csrs if is_user_online(user, now=now)),
            "available_csrs": sum(
                1
                for user in csrs
                if user.is_active and user.is_available and is_user_online(user, now=now)
            ),
            "online_techs": sum(1 for tech in techs if is_tech_online(tech, now=now)),
        },
        "online_window_seconds": CSR_ONLINE_WINDOW_SECONDS,
    })


@app.route("/api/admin/tech-accounts", methods=["GET"])
@admin_required
def get_tech_accounts():
    """Get all technical team accounts with live online presence."""
    techs = TechTeamAccount.query.order_by(TechTeamAccount.created_at.desc()).all()
    now = utcnow()
    return jsonify({
        "techs": [
            {
                "id": t.id,
                "email": t.email,
                "display_name": t.display_name,
                "specialty": t.specialty,
                "is_active": bool(t.is_active),
                "is_online": is_tech_online(t, now=now),
                "last_seen_at": isoformat_or_none(t.last_seen_at),
                "created_at": isoformat_or_none(t.created_at),
            }
            for t in techs
        ],
        "online_window_seconds": CSR_ONLINE_WINDOW_SECONDS,
    })


# ─── Startup ─────────────────────────────────────────────────
with app.app_context():
    ensure_schema()
    bootstrap_users()
    sync_integration_settings_artifacts(load_integration_settings())
    # Initialize default ticket statuses if none exist
    if TicketStatus.query.count() == 0:
        for status_data in TicketStatus.get_default_statuses():
            existing = TicketStatus.query.filter_by(name=status_data["name"]).first()
            if not existing:
                status = TicketStatus(**status_data)
                db.session.add(status)
        db.session.commit()

    # Repair a legacy label once in storage, while serialization also protects
    # any future imported record that uses the compact "onhold" spelling.
    legacy_on_hold_statuses = TicketStatus.query.filter(func.lower(TicketStatus.label) == "onhold").all()
    if legacy_on_hold_statuses:
        for status in legacy_on_hold_statuses:
            status.label = "On Hold"
        db.session.commit()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
