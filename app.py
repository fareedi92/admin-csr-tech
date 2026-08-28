import base64
import hashlib
import json
import os
import secrets
import uuid
from datetime import date, datetime, time
from functools import wraps
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
    Response,
)
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, MetaData, Table, Time, delete, func, inspect, select, text, update
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
load_dotenv(os.path.join(BASE_DIR, ".env"))


def resolve_database_url(env_key, default_path):
    """Use default SQLite URI when env is missing, empty, or invalid."""
    raw = (os.environ.get(env_key) or "").strip()
    default_uri = f"sqlite:///{default_path}"
    if not raw:
        return default_uri
    if raw.startswith("file:") and not raw.startswith("sqlite:"):
        return default_uri
    try:
        from sqlalchemy.engine import make_url

        make_url(raw)
        return raw
    except Exception:
        return default_uri

DEFAULT_WEBHOOK_URL = os.environ.get(
    "DEFAULT_WEBHOOK_URL",
    "https://aidevv.3utilities.com/webhook/65350c02-df88-49d9-983d-8aaf691d7ad1/chat",
).strip()
DEFAULT_INSTANCE_ID = os.environ.get(
    "DEFAULT_N8N_INSTANCE_ID",
    "0d120a8625980c6399396b35943a7a9e81902ca30dc8b7df12b06110cad66c23",
)
DEFAULT_CSR_API_URL = os.environ.get("DEFAULT_CSR_API_URL", "").rstrip("/")
DEFAULT_CHATBOT_VERIFY_BASE_URL = os.environ.get(
    "CHATBOT_VERIFY_BASE_URL",
    "https://beta-tj1.frontlineticketing.com",
).rstrip("/")
DEFAULT_CHATBOT_SERVICE_SECRET = os.environ.get(
    "CHATBOT_SERVICE_SECRET",
    "682be0af23d4bdf216504fa2778398475c75214670adf8dabac4a3bd4158fceb",
).strip()
# Enable real FLT token verification by default. Set WIDGET_TOKEN_AUTH_ENABLED=false to bypass while beta auth is broken.
WIDGET_TOKEN_AUTH_ENABLED = os.environ.get("WIDGET_TOKEN_AUTH_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WIDGET_ASSET_DIR = os.path.join(BASE_DIR, "static", "js")
CHAT_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "chat")
CSR_RESOLVED_MESSAGE = "You are connected back to AI. How can I help you?"
MAX_IMAGE_ATTACHMENTS = 3
MAX_IMAGE_DATA_URL_LENGTH = 3_000_000
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
IMAGE_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "chat-widget-manager-dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = resolve_database_url(
    "DATABASE_URL",
    os.path.join(INSTANCE_DIR, "widget_manager.db"),
)
app.config["SQLALCHEMY_BINDS"] = {
    "csr": resolve_database_url(
        "CSR_DATABASE_URL",
        os.path.join(INSTANCE_DIR, "widget_manager_csr.db"),
    ),
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

CORS(
    app,
    resources={
        r"/api/*": {"origins": "*"},
        r"/validate_widget": {"origins": "*"},
        r"/embed/*": {"origins": "*"},
        r"/widget-assets/*": {"origins": "*"},
    },
)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    company = db.Column(db.String(255))
    phone = db.Column(db.String(32))
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    businesses = db.relationship("Business", backref="owner", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    website = db.Column(db.String(255))
    phone = db.Column(db.String(32))
    authorized_domains = db.Column(db.Text)
    widget_key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    csr_key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    widget_title = db.Column(db.String(255))
    welcome_message = db.Column(db.Text)
    primary_color = db.Column(db.String(32), default="#5B50E7")
    button_color = db.Column(db.String(32), default="#5B50E7")
    header_background = db.Column(db.String(255), default="linear-gradient(to right, #5D5CFF, #7A2EE6)")
    background_color = db.Column(db.String(32), default="#121826")
    message_area_bg_color = db.Column(db.String(32), default="#0d1520")
    agent_icon = db.Column(
        db.String(500),
        default="https://beta-tj1.frontlineticketing.com/images/logo.png",
    )
    namespace_override = db.Column(db.String(255))
    n8n_webhook_url = db.Column(db.String(500), default=DEFAULT_WEBHOOK_URL)
    n8n_instance_id = db.Column(db.String(255), default=DEFAULT_INSTANCE_ID)
    external_csr_api_endpoint = db.Column(db.String(500), default=DEFAULT_CSR_API_URL)
    chatbot_verify_base_url = db.Column(db.String(500), default=DEFAULT_CHATBOT_VERIFY_BASE_URL)
    chatbot_service_secret = db.Column(db.String(255), default=DEFAULT_CHATBOT_SERVICE_SECRET)
    api_timeout_seconds = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chat_sessions = db.relationship("ChatSession", backref="business", lazy=True, cascade="all, delete-orphan")
    api_logs = db.relationship("WidgetApiLog", backref="business", lazy=True, cascade="all, delete-orphan")

    def namespace(self):
        if self.namespace_override:
            return self.namespace_override
        safe_name = (self.name or "business").strip().replace(" ", "_")
        return f"{self.user_id}_{safe_name}"

    def allowed_domains(self):
        domains = []
        for raw in (self.authorized_domains or "").split(","):
            raw = raw.strip().lower()
            if raw and raw not in {"none", "null", "nil", "n/a"}:
                domains.append(raw.replace("www.", "", 1) if raw.startswith("www.") else raw)

        if self.website:
            website_domain = normalize_domain(self.website)
            if website_domain and website_domain not in domains:
                domains.append(website_domain)

        return domains

    def widget_config(self):
        visitor_suffix = self.widget_key[:8]
        return {
            "position": "bottom-right",
            "width": "380px",
            "height": "min(640px, calc(100vh - 100px))",
            "mobileWidth": "100%",
            "mobileHeight": "100%",
            "widgetTitle": self.widget_title or f"{self.name} Support",
            "welcomeMessage": self.welcome_message or "Hello! How can we help you today?",
            "csrResolvedMessage": CSR_RESOLVED_MESSAGE,
            "userTypePrompt": "Are you a Buyer or Organizer?",
            "buyerLabel": "Buyer",
            "organizerLabel": "Organizer",
            "userTypePlaceholder": "Select Buyer or Organizer to start chatting",
            "userAvatar": "user",
            "aiAvatar": "bot",
            "primaryColor": self.primary_color or "#5B50E7",
            "buttonColor": self.button_color or self.primary_color or "#5B50E7",
            "headerBackground": self.header_background or "linear-gradient(to right, #5D5CFF, #7A2EE6)",
            "backgroundColor": self.background_color or "#121826",
            "messageAreaBgColor": self.message_area_bg_color or "#0d1520",
            "textColor": "#ffffff",
            "userMessageColor": "#fcb41a",
            "userMessageTextColor": "#15253e",
            "aiMessageColor": "#1A2332",
            "aiMessageTextColor": "#e2e8f0",
            "csrMessageColor": "#1A2332",
            "csrMessageTextColor": "#e2e8f0",
            "inputBgColor": "#1A2332",
            "inputTextColor": "#ffffff",
            "inputPlaceholderColor": "#64748b",
            "borderColor": "#2a3444",
            "shadowColor": "rgba(0, 0, 0, 0.3)",
            "fontFamily": '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
            "fontSize": "14px",
            "headerFontSize": "16px",
            "agentIcon": self.agent_icon or "bot",
            "agentIconSize": "32px",
            "agentIconFallback": "user",
            "sendButtonIcon": "send",
            "closeButtonIcon": "close",
            "toggleButtonIcon": "chat",
            "autoOpen": False,
            "openDelay": 1000,
            "closeOnOutsideClick": True,
            "focusInputOnOpen": True,
            "clearChatOnReload": True,
            "apiUrl": "/api/chat",
            "pollUrl": "/api/chat/poll",
            "pollInterval": 3000,
            "requestTimeout": (self.api_timeout_seconds or 30) * 1000,
            "mobileBreakpoint": "768px",
            "animationDuration": "0.3s",
            "enableAnimations": True,
            "externalCsrApiEndpoint": (self.external_csr_api_endpoint or "").rstrip("/"),
            "visitorIdKey": f"chat_visitor_id_{visitor_suffix}",
            "storageKey": f"chat_history_{visitor_suffix}",
        }


class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("business.id"), nullable=False, index=True)
    user_identifier = db.Column(db.String(120), nullable=False, index=True)
    domain = db.Column(db.String(255))
    status = db.Column(db.String(32), default="active_ai", nullable=False)
    user_type = db.Column(db.String(32))
    auth_mode = db.Column(db.String(20), default="anonymous", nullable=False)
    authenticated_user_id = db.Column(db.String(120), index=True)
    authenticated_user_data = db.Column(db.Text)
    auth_token_fingerprint = db.Column(db.String(64))
    csr_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    csr = db.relationship("User", backref=db.backref("assigned_chat_sessions", lazy=True))
    messages = db.relationship("ChatMessage", backref="chat_session", lazy=True, cascade="all, delete-orphan")
    api_logs = db.relationship("WidgetApiLog", backref="chat_session", lazy=True)


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=False, index=True)
    sender_type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_attachments = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)


class WidgetApiLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("business.id"), index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), index=True)
    endpoint = db.Column(db.String(255), nullable=False)
    http_method = db.Column(db.String(16), nullable=False, default="POST")
    request_payload = db.Column(db.Text)
    response_payload = db.Column(db.Text)
    status_code = db.Column(db.Integer, nullable=False, default=200)
    visitor_id = db.Column(db.String(120), index=True)
    domain = db.Column(db.String(255))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class CsrBusiness(db.Model):
    __bind_key__ = "csr"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    linked_business_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    business_name = db.Column(db.String(255), nullable=False)
    csr_widget_key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    widget_title = db.Column(db.String(255), default="Live Chat")
    primary_color = db.Column(db.String(32), default="#2563EB")
    container_id = db.Column(db.String(128), default="csr-console")
    auto_activate = db.Column(db.Boolean, default=True, nullable=False)
    chat_list_poll = db.Column(db.Integer, default=5000)
    message_poll = db.Column(db.Integer, default=3000)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    conversations = db.relationship("CsrConversation", backref="csr_business", lazy=True, cascade="all, delete-orphan")
    api_logs = db.relationship("CsrWidgetApiLog", backref="csr_business", lazy=True, cascade="all, delete-orphan")


class CsrConversation(db.Model):
    __bind_key__ = "csr"

    id = db.Column(db.Integer, primary_key=True)
    csr_business_id = db.Column(db.Integer, db.ForeignKey("csr_business.id"), nullable=False, index=True)
    linked_chat_session_id = db.Column(db.Integer, nullable=False, index=True)
    visitor_id = db.Column(db.String(120), nullable=False, index=True)
    domain = db.Column(db.String(255))
    status = db.Column(db.String(32), default="pending_csr", nullable=False)
    user_type = db.Column(db.String(32))
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    messages = db.relationship("CsrConversationMessage", backref="conversation", lazy=True, cascade="all, delete-orphan")
    api_logs = db.relationship("CsrWidgetApiLog", backref="conversation", lazy=True)


class CsrConversationMessage(db.Model):
    __bind_key__ = "csr"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("csr_conversation.id"), nullable=False, index=True)
    linked_chat_message_id = db.Column(db.Integer, index=True)
    sender_type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_attachments = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class CsrWidgetApiLog(db.Model):
    __bind_key__ = "csr"

    id = db.Column(db.Integer, primary_key=True)
    csr_business_id = db.Column(db.Integer, db.ForeignKey("csr_business.id"), index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("csr_conversation.id"), index=True)
    endpoint = db.Column(db.String(255), nullable=False)
    http_method = db.Column(db.String(16), nullable=False, default="POST")
    request_payload = db.Column(db.Text)
    response_payload = db.Column(db.Text)
    status_code = db.Column(db.Integer, nullable=False, default=200)
    visitor_id = db.Column(db.String(120), index=True)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            target_path = request.path
            if request.query_string:
                target_path = f"{target_path}?{request.query_string.decode('utf-8', errors='ignore')}"
            return redirect(url_for("login", next=target_path))
        return view_func(*args, **kwargs)

    return wrapper


def get_safe_post_login_redirect(default_endpoint="dashboard"):
    raw_target = (request.values.get("next") or "").strip()
    if not raw_target:
        return url_for(default_endpoint)

    parsed = urlparse(raw_target)
    if parsed.scheme or parsed.netloc or not raw_target.startswith("/"):
        return url_for(default_endpoint)

    return raw_target


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def normalize_user_type(value):
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"buyer", "organizer"}:
        return normalized
    return None


def normalize_auth_payload(payload):
    """Resolve visitor auth. Missing/empty token always becomes anonymous."""
    if not isinstance(payload, dict):
        return "anonymous", None, None

    raw_auth = payload.get("auth")
    if raw_auth is None:
        raw_auth = payload.get("authentication")
    if raw_auth is None:
        raw_auth = {}
    if not isinstance(raw_auth, dict):
        return None, None, "auth must be an object"

    token = str(raw_auth.get("token") or payload.get("token") or "").strip()
    mode = str(raw_auth.get("mode") or payload.get("mode") or "anonymous").strip().lower()

    # No token => anonymous, regardless of requested mode.
    if not token:
        return "anonymous", None, None

    if mode not in {"anonymous", "authenticated"}:
        return None, None, "auth.mode must be anonymous or authenticated"

    if mode == "anonymous":
        return "anonymous", None, None

    return "authenticated", token, None


def token_fingerprint(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def deserialize_authenticated_user(raw_user):
    if not raw_user:
        return None
    try:
        user = json.loads(raw_user)
    except (TypeError, ValueError):
        return None
    return user if isinstance(user, dict) else None


def resolve_chatbot_verify_base_url(business=None):
    if business and getattr(business, "chatbot_verify_base_url", None):
        return str(business.chatbot_verify_base_url).rstrip("/")
    return DEFAULT_CHATBOT_VERIFY_BASE_URL


def build_chatbot_verify_url(base_url):
    normalized_url = str(base_url or "").strip().rstrip("/")
    if normalized_url.endswith("/api/chatbot/verify"):
        return normalized_url
    if normalized_url.endswith("/api"):
        return f"{normalized_url}/chatbot/verify"
    return f"{normalized_url}/api/chatbot/verify"


def fetch_chatbot_token(business, user_bearer_token):
    """Exchange a logged-in user's session token for a chatbot token from FLT."""
    token_base_url = resolve_chatbot_verify_base_url(business)
    token_url = f"{token_base_url}/api/chatbot/token"
    try:
        response = requests.post(
            token_url,
            headers={
                "Authorization": f"Bearer {user_bearer_token}",
                "Accept": "application/json",
            },
            timeout=min(business.api_timeout_seconds or 30, 10) if business else 10,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Token service unavailable") from exc

    if not response.ok:
        raise RuntimeError("Token authentication failed")

    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("Token service returned invalid JSON")

    token = payload.get("chatbot_token") or payload.get("token")
    if not token:
        raise RuntimeError("Token service did not return a chatbot_token")
    return token


def resolve_chatbot_service_secret(business=None):
    if business and getattr(business, "chatbot_service_secret", None):
        secret = str(business.chatbot_service_secret).strip()
        if secret:
            return secret
    return DEFAULT_CHATBOT_SERVICE_SECRET


def normalize_verified_user(response_payload):
    if not isinstance(response_payload, dict):
        return None

    user = response_payload.get("user")
    if not isinstance(user, dict):
        user = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else {}
        if "user" in user and isinstance(user.get("user"), dict):
            user = user["user"]

    user_id = (
        user.get("id")
        or user.get("user_id")
        or user.get("userId")
        or response_payload.get("id")
        or response_payload.get("user_id")
        or response_payload.get("userId")
    )
    if user_id is None:
        return None

    name = (
        user.get("name")
        or user.get("full_name")
        or user.get("fullName")
        or " ".join(
            part
            for part in [
                str(user.get("first_name") or user.get("firstName") or "").strip(),
                str(user.get("last_name") or user.get("lastName") or "").strip(),
            ]
            if part
        ).strip()
        or response_payload.get("name")
        or f"User {user_id}"
    )
    email = user.get("email") or response_payload.get("email")
    metadata = {
        key: value
        for key, value in user.items()
        if key not in {"id", "user_id", "userId", "name", "full_name", "fullName", "email", "first_name", "firstName", "last_name", "lastName"}
    }
    return {
        "id": str(user_id),
        "name": str(name),
        "email": str(email).strip() if email else None,
        "metadata": metadata,
    }


def is_successful_verify_response(response, response_payload):
    if not isinstance(response_payload, dict):
        return False
    if response_payload.get("authenticated") is True:
        return True
    if response_payload.get("valid") is True:
        return True
    if response.ok and normalize_verified_user(response_payload):
        # Some FLT builds return the user payload without an explicit valid/authenticated flag.
        return "user" in response_payload or "id" in response_payload or "user_id" in response_payload
    return False


def _cached_authenticated_user(cached_session, fingerprint):
    if not (
        cached_session
        and cached_session.auth_mode == "authenticated"
        and cached_session.auth_token_fingerprint == fingerprint
    ):
        return None
    return deserialize_authenticated_user(cached_session.authenticated_user_data)


def verify_widget_identity(business, payload, cached_session=None, allow_cached=False):
    mode, token, validation_error = normalize_auth_payload(payload)
    if not WIDGET_TOKEN_AUTH_ENABLED:
        # Keep widget usable while FLT /api/chatbot/verify is unavailable.
        return "anonymous", None, None, None

    if validation_error:
        return None, None, validation_error, 400

    if mode == "anonymous":
        if cached_session and cached_session.auth_mode == "authenticated":
            return None, None, "Authenticated session credentials are required", 401
        return mode, None, None, None

    fingerprint = token_fingerprint(token)
    cached_user = _cached_authenticated_user(cached_session, fingerprint)
    # Verify once per visitor token: reuse cached identity on later chat/poll calls.
    if allow_cached and cached_user:
        return mode, cached_user, None, None

    verify_base_url = resolve_chatbot_verify_base_url(business)
    service_secret = resolve_chatbot_service_secret(business)
    if not verify_base_url or not service_secret:
        if cached_user:
            return mode, cached_user, None, None
        return None, None, "Authenticated widget mode is not configured", 503

    verify_url = build_chatbot_verify_url(verify_base_url)
    try:
        response = requests.post(
            verify_url,
            json={"token": token},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Service-Secret": service_secret,
            },
            timeout=min(business.api_timeout_seconds or 30, 10) if business else 10,
        )
    except requests.RequestException:
        if cached_user:
            return mode, cached_user, None, None
        return None, None, "Authentication service unavailable", 503

    try:
        response_payload = response.json()
    except ValueError:
        response_payload = {}

    # Distinguish FLT outage / missing route from an invalid visitor token.
    if response.status_code in {404, 405, 502, 503, 504} or (
        response.status_code >= 500 and not isinstance(response_payload, dict)
    ):
        if cached_user:
            return mode, cached_user, None, None
        return None, None, "Authentication service unavailable", 503

    if not response_payload and response.status_code != 401:
        if cached_user:
            return mode, cached_user, None, None
        return None, None, "Authentication service unavailable", 503

    if response.status_code == 401:
        # Keep an already-verified session alive if the same token fingerprint matches.
        if cached_user:
            return mode, cached_user, None, None
        return None, None, "Token authentication failed", 401

    if not is_successful_verify_response(response, response_payload):
        if cached_user:
            return mode, cached_user, None, None
        return None, None, "Token authentication failed", 401

    user = normalize_verified_user(response_payload)
    if not user:
        if cached_user:
            return mode, cached_user, None, None
        return None, None, "Token authentication failed", 401

    # Keep the upstream payload for temporary in-widget verification/debugging.
    user["verification_response"] = response_payload
    return mode, user, None, None


def apply_identity_to_chat_session(chat_session, mode, token, authenticated_user):
    chat_session.auth_mode = mode
    if mode == "authenticated":
        chat_session.authenticated_user_id = str(authenticated_user["id"])
        chat_session.authenticated_user_data = json.dumps(authenticated_user)
        chat_session.auth_token_fingerprint = token_fingerprint(token)
    else:
        chat_session.authenticated_user_id = None
        chat_session.authenticated_user_data = None
        chat_session.auth_token_fingerprint = None


def redact_sensitive_payload(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in {"token", "secret", "service_secret", "chatbot_service_secret"}:
                redacted[key] = "[REDACTED]" if item else item
            else:
                redacted[key] = redact_sensitive_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]
    return value


def normalize_domain(domain):
    if not domain:
        return ""
    try:
        raw = domain.strip()
        if "://" not in raw:
            raw = f"http://{raw}"
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def generate_unique_business_token(field_name):
    token = secrets.token_urlsafe(32)
    while Business.query.filter(getattr(Business, field_name) == token).first():
        token = secrets.token_urlsafe(32)
    return token


def ensure_business_tokens(business):
    if not business.widget_key:
        business.widget_key = generate_unique_business_token("widget_key")
    if not business.csr_key:
        business.csr_key = generate_unique_business_token("csr_key")


def record_widget_log(
    endpoint,
    http_method,
    request_payload,
    response_payload,
    status_code,
    business=None,
    chat_session=None,
    visitor_id=None,
    domain=None,
    error_message=None,
):
    try:
        log = WidgetApiLog(
            business_id=business.id if business else None,
            session_id=chat_session.id if chat_session else None,
            endpoint=endpoint,
            http_method=http_method,
            request_payload=json.dumps(redact_sensitive_payload(request_payload), default=str) if request_payload is not None else None,
            response_payload=json.dumps(response_payload, default=str) if response_payload is not None else None,
            status_code=status_code,
            visitor_id=visitor_id,
            domain=domain,
            error_message=error_message,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def record_csr_widget_log(
    endpoint,
    http_method,
    request_payload,
    response_payload,
    status_code,
    csr_business=None,
    conversation=None,
    visitor_id=None,
    error_message=None,
):
    try:
        log = CsrWidgetApiLog(
            csr_business_id=csr_business.id if csr_business else None,
            conversation_id=conversation.id if conversation else None,
            endpoint=endpoint,
            http_method=http_method,
            request_payload=json.dumps(request_payload, default=str) if request_payload is not None else None,
            response_payload=json.dumps(response_payload, default=str) if response_payload is not None else None,
            status_code=status_code,
            visitor_id=visitor_id,
            error_message=error_message,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def save_image_data_url(data_url, mime_type, base_url):
    if not base_url:
        return None
    try:
        _, encoded = data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        return None

    os.makedirs(CHAT_UPLOAD_DIR, exist_ok=True)
    extension = IMAGE_EXTENSION_BY_MIME.get(mime_type, ".png")
    filename = f"{uuid.uuid4().hex}{extension}"
    file_path = os.path.join(CHAT_UPLOAD_DIR, filename)
    with open(file_path, "wb") as image_file:
        image_file.write(image_bytes)

    return f"{base_url.rstrip('/')}/static/uploads/chat/{filename}"


def normalize_image_attachments(raw_attachments, base_url=None):
    if not raw_attachments:
        return []
    if not isinstance(raw_attachments, list):
        raw_attachments = [raw_attachments]

    normalized = []
    for raw_attachment in raw_attachments[:MAX_IMAGE_ATTACHMENTS]:
        if not isinstance(raw_attachment, dict):
            continue

        data_url = str(raw_attachment.get("data_url") or raw_attachment.get("dataUrl") or "").strip()
        image_url = str(
            raw_attachment.get("image_url")
            or raw_attachment.get("imageUrl")
            or raw_attachment.get("url")
            or ""
        ).strip()
        mime_type = str(raw_attachment.get("mime_type") or raw_attachment.get("type") or "").strip().lower()
        name = str(raw_attachment.get("name") or "uploaded-image").strip()[:160]

        if data_url:
            if not data_url.startswith("data:image/") or ";base64," not in data_url:
                continue
            detected_mime = data_url[5:data_url.find(";base64,")].lower()
            mime_type = mime_type or detected_mime
            if mime_type not in ALLOWED_IMAGE_MIME_TYPES or detected_mime != mime_type:
                continue
            if len(data_url) > MAX_IMAGE_DATA_URL_LENGTH:
                continue
            image_url = image_url or save_image_data_url(data_url, mime_type, base_url)
        elif image_url.startswith(("http://", "https://")):
            mime_type = mime_type if mime_type in ALLOWED_IMAGE_MIME_TYPES else "image/png"
        else:
            continue

        display_url = image_url or data_url

        normalized.append(
            {
                "name": name,
                "mime_type": mime_type,
                "data_url": data_url,
                "image_url": display_url,
                "imageUrl": display_url,
                "url": display_url,
            }
        )

    return normalized


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


def message_to_payload(message, include_id=True):
    attachments = deserialize_image_attachments(getattr(message, "image_attachments", None))
    payload = add_image_payload_fields(
        {
            "content": message.content,
            "sender": "csr" if message.sender_type == "csr" else ("user" if message.sender_type == "user" else "ai"),
            "timestamp": message.timestamp.isoformat() + "Z",
        },
        attachments,
    )
    if include_id:
        payload["id"] = message.id
    return payload


def message_to_transcript_payload(message):
    attachments = deserialize_image_attachments(getattr(message, "image_attachments", None))
    return add_image_payload_fields(
        {
            "sender": message.sender_type,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
        },
        attachments,
    )


def image_urls_for_payload(attachments):
    urls = []
    for attachment in attachments or []:
        url = attachment.get("image_url") or attachment.get("imageUrl") or attachment.get("url") or attachment.get("data_url")
        if url:
            urls.append(url)
    return urls


def add_image_payload_fields(payload, attachments):
    urls = image_urls_for_payload(attachments)
    payload["images"] = attachments
    payload["image_urls"] = urls
    if urls:
        payload["image_url"] = urls[0]
        payload["imageUrl"] = urls[0]
    return payload


def message_preview(message):
    if not message:
        return ""
    images = deserialize_image_attachments(getattr(message, "image_attachments", None))
    if message.content and images:
        return f"{message.content} [image]"
    if images:
        return "[image]"
    return message.content or ""


def find_business_for_user(business_id, user):
    return Business.query.filter_by(id=business_id, user_id=user.id).first()


def find_csr_business_for_user(business_id, user):
    return CsrBusiness.query.filter_by(linked_business_id=business_id, user_id=user.id).first()


def ensure_csr_business_for_business(business):
    if not business.csr_key:
        business.csr_key = generate_unique_business_token("csr_key")

    csr_business = CsrBusiness.query.filter_by(linked_business_id=business.id).first()
    if not csr_business:
        csr_business = CsrBusiness(
            user_id=business.user_id,
            linked_business_id=business.id,
            business_name=business.name,
            csr_widget_key=business.csr_key,
            widget_title=f"{business.name} CSR Console",
            primary_color=business.primary_color or "#2563EB",
            is_active=business.is_active,
        )
        db.session.add(csr_business)
    else:
        csr_business.user_id = business.user_id
        csr_business.linked_business_id = business.id
        csr_business.business_name = business.name
        csr_business.csr_widget_key = business.csr_key
        csr_business.is_active = business.is_active
        if not csr_business.primary_color:
            csr_business.primary_color = business.primary_color or "#2563EB"
        if not csr_business.widget_title:
            csr_business.widget_title = f"{business.name} CSR Console"
        if not csr_business.container_id:
            csr_business.container_id = "csr-console"

    return csr_business


def get_or_create_csr_conversation(chat_session, business):
    csr_business = ensure_csr_business_for_business(business)
    conversation = CsrConversation.query.filter_by(linked_chat_session_id=chat_session.id).first()
    if not conversation:
        conversation = CsrConversation(
            csr_business_id=csr_business.id,
            linked_chat_session_id=chat_session.id,
            visitor_id=chat_session.user_identifier,
            domain=chat_session.domain,
            status=chat_session.status,
            user_type=chat_session.user_type,
            summary=chat_session.summary,
        )
        db.session.add(conversation)
    else:
        conversation.csr_business_id = csr_business.id
        conversation.visitor_id = chat_session.user_identifier
        conversation.domain = chat_session.domain
        conversation.status = chat_session.status
        conversation.user_type = chat_session.user_type
        conversation.summary = chat_session.summary

    db.session.flush()
    return csr_business, conversation


def sync_chat_session_to_csr(chat_session, business):
    csr_business, conversation = get_or_create_csr_conversation(chat_session, business)

    existing_ids = {
        message.linked_chat_message_id
        for message in CsrConversationMessage.query.filter_by(conversation_id=conversation.id).all()
        if message.linked_chat_message_id is not None
    }

    messages = ChatMessage.query.filter_by(session_id=chat_session.id).order_by(ChatMessage.id.asc()).all()
    for message in messages:
        if message.id in existing_ids:
            continue
        db.session.add(
            CsrConversationMessage(
                conversation_id=conversation.id,
                linked_chat_message_id=message.id,
                sender_type=message.sender_type,
                content=message.content,
                image_attachments=message.image_attachments,
                timestamp=message.timestamp,
            )
        )

    conversation.status = chat_session.status
    conversation.user_type = chat_session.user_type
    conversation.summary = chat_session.summary
    conversation.updated_at = datetime.utcnow()
    db.session.commit()
    return csr_business, conversation


def get_chat_business_and_session_for_csr_conversation(conversation):
    business = Business.query.get(conversation.linked_business_id) if hasattr(conversation, "linked_business_id") else None
    if business is None:
        business = Business.query.get(conversation.csr_business.linked_business_id) if conversation.csr_business else None
    chat_session = ChatSession.query.get(conversation.linked_chat_session_id)
    return business, chat_session


def csr_conversation_authentication_payload(conversation):
    """Expose verified visitor identity for CSR dashboard list/detail views."""
    chat_session = ChatSession.query.get(conversation.linked_chat_session_id) if conversation else None
    if not chat_session:
        return {
            "mode": "anonymous",
            "user": None,
            "user_id": None,
            "user_name": None,
        }

    auth_mode = (chat_session.auth_mode or "anonymous").strip().lower()
    user = deserialize_authenticated_user(chat_session.authenticated_user_data)
    if auth_mode != "authenticated":
        user = None

    user_id = None
    user_name = None
    if isinstance(user, dict):
        user_id = user.get("id") or chat_session.authenticated_user_id
        user_name = user.get("name")
        # Prefer the raw FLT verification response when present (matches widget debug).
        verification_response = user.get("verification_response")
        if isinstance(verification_response, dict):
            display_user = verification_response.get("user")
            if isinstance(display_user, dict):
                user_id = display_user.get("id", user_id)
                user_name = display_user.get("name", user_name)

    return {
        "mode": auth_mode if auth_mode in {"anonymous", "authenticated"} else "anonymous",
        "user": user,
        "user_id": str(user_id) if user_id is not None else None,
        "user_name": str(user_name) if user_name else None,
    }


def serialize_csr_chat_list_item(conversation):
    last_message = (
        CsrConversationMessage.query.filter_by(conversation_id=conversation.id)
        .order_by(CsrConversationMessage.timestamp.desc())
        .first()
    )
    authentication = csr_conversation_authentication_payload(conversation)
    return {
        "id": conversation.id,
        "visitor_id": conversation.visitor_id,
        "status": conversation.status,
        "last_message": message_preview(last_message),
        "timestamp": conversation.updated_at.isoformat() + "Z",
        "summary": conversation.summary,
        "user_type": conversation.user_type,
        "auth_mode": authentication["mode"],
        "authenticated_user_id": authentication["user_id"],
        "authenticated_user_name": authentication["user_name"],
        "authentication": authentication,
    }


def create_csr_reply(conversation, message, acting_user=None):
    business = Business.query.get(conversation.csr_business.linked_business_id)
    chat_session = ChatSession.query.get(conversation.linked_chat_session_id)
    if not business or not chat_session:
        raise ValueError("Linked chat session not found.")

    if chat_session.status == "pending_csr":
        chat_session.status = "active_csr"
        if acting_user:
            chat_session.csr_id = acting_user.id

    main_msg = ChatMessage(session_id=chat_session.id, sender_type="csr", content=message, timestamp=datetime.utcnow())
    db.session.add(main_msg)
    db.session.flush()

    conversation.status = "active_csr"
    conversation.updated_at = datetime.utcnow()
    db.session.add(
        CsrConversationMessage(
            conversation_id=conversation.id,
            linked_chat_message_id=main_msg.id,
            sender_type="csr",
            content=message,
            image_attachments=main_msg.image_attachments,
            timestamp=main_msg.timestamp,
        )
    )
    chat_session.updated_at = datetime.utcnow()
    db.session.commit()
    return main_msg


def resolve_csr_conversation(conversation):
    business = Business.query.get(conversation.csr_business.linked_business_id)
    chat_session = ChatSession.query.get(conversation.linked_chat_session_id)
    if not business or not chat_session:
        raise ValueError("Linked chat session not found.")

    chat_session.status = "active_ai"
    chat_session.csr_id = None
    chat_session.updated_at = datetime.utcnow()
    system_msg = ChatMessage(
        session_id=chat_session.id,
        sender_type="ai",
        content=CSR_RESOLVED_MESSAGE,
        timestamp=datetime.utcnow(),
    )
    db.session.add(system_msg)
    db.session.flush()

    conversation.status = "resolved"
    conversation.updated_at = datetime.utcnow()
    db.session.add(
        CsrConversationMessage(
            conversation_id=conversation.id,
            linked_chat_message_id=system_msg.id,
            sender_type="ai",
            content=CSR_RESOLVED_MESSAGE,
            image_attachments=system_msg.image_attachments,
            timestamp=system_msg.timestamp,
        )
    )
    db.session.commit()
    return system_msg


def get_or_create_chat_session(
    business,
    visitor_id,
    requested_user_type=None,
    domain=None,
    auth_mode="anonymous",
    auth_token=None,
    authenticated_user=None,
):
    # Always prefer the most recently updated session so a resolved CSR chat
    # (status active_ai) is not shadowed by an older pending_csr row.
    chat_session = (
        ChatSession.query.filter_by(
            user_identifier=visitor_id,
            business_id=business.id,
        )
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .first()
    )

    if not chat_session:
        chat_session = ChatSession(
            business_id=business.id,
            user_identifier=visitor_id,
            status="active_ai",
            user_type=requested_user_type,
            domain=domain,
        )
        apply_identity_to_chat_session(chat_session, auth_mode, auth_token, authenticated_user)
        db.session.add(chat_session)
        db.session.commit()
    else:
        updated = False
        if requested_user_type and not chat_session.user_type:
            chat_session.user_type = requested_user_type
            updated = True
        if domain and chat_session.domain != domain:
            chat_session.domain = domain
            updated = True
        if auth_mode == "authenticated":
            apply_identity_to_chat_session(chat_session, auth_mode, auth_token, authenticated_user)
            updated = True
        if updated:
            db.session.commit()

    return chat_session


def business_is_authorized_for_domain(business, domain):
    normalized = normalize_domain(domain)
    allowed_domains = business.allowed_domains()
    is_authorized = normalized in allowed_domains

    if normalized in {
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "52.74.227.205",
        "flt-frontend-web-sigma.vercel.app",
        "beta-ja.frontlineticketing.com",
    }:
        is_authorized = True

    if normalized.endswith(".vercel.app"):
        is_authorized = True

    if not allowed_domains:
        is_authorized = True

    return is_authorized, normalized


def authenticate_csr_request():
    payload = request.get_json(silent=True) or {}
    csr_key = request.args.get("csr_key") or payload.get("csr_key")
    if not csr_key:
        return None, jsonify({"error": "CSR key required"}), 401

    csr_business = CsrBusiness.query.filter_by(csr_widget_key=csr_key, is_active=True).first()
    if not csr_business:
        return None, jsonify({"error": "Invalid CSR key"}), 401

    return csr_business, None, None


def get_engine_for_db_key(db_key="main"):
    return db.engine if db_key != "csr" else db.engines["csr"]


def get_database_label(db_key="main"):
    return "CSR Widget Database" if db_key == "csr" else "Chat Widget Database"


def get_reflected_table(table_name, db_key="main"):
    metadata = MetaData()
    return Table(table_name, metadata, autoload_with=get_engine_for_db_key(db_key))


def get_single_primary_key(table):
    primary_keys = list(table.primary_key.columns)
    return primary_keys[0] if len(primary_keys) == 1 else None


def parse_column_value(raw_value, column, allow_primary_key=False):
    if raw_value == "__NULL__":
        return None

    if raw_value == "" and column.nullable and (allow_primary_key or not column.primary_key):
        return None

    column_type = column.type

    if isinstance(column_type, Boolean):
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(column_type, Integer):
        return int(raw_value)
    if isinstance(column_type, Float):
        return float(raw_value)
    if isinstance(column_type, DateTime):
        normalized = str(raw_value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    if isinstance(column_type, Date):
        return date.fromisoformat(str(raw_value).strip())
    if isinstance(column_type, Time):
        return time.fromisoformat(str(raw_value).strip())

    return raw_value


def stringify_db_value(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def get_database_details(db_key="main"):
    if db_key == "main":
        database_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    else:
        database_uri = app.config["SQLALCHEMY_BINDS"]["csr"]

    engine = get_engine_for_db_key(db_key)
    details = {
        "key": db_key,
        "label": get_database_label(db_key),
        "uri": database_uri,
        "driver": engine.url.drivername,
        "database": engine.url.database,
        "file_exists": False,
        "file_size_bytes": None,
    }

    if engine.url.drivername.startswith("sqlite") and engine.url.database:
        db_path = engine.url.database
        details["file_exists"] = os.path.exists(db_path)
        if details["file_exists"]:
            details["file_size_bytes"] = os.path.getsize(db_path)

    return details


def ensure_column_exists(db_key, table_name, column_name, column_definition):
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))


def get_table_schema_summary(table_name, db_key="main"):
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    table = get_reflected_table(table_name, db_key)
    with engine.connect() as connection:
        row_count = connection.execute(select(func.count()).select_from(table)).scalar_one()

    columns = inspector.get_columns(table_name)
    foreign_keys = inspector.get_foreign_keys(table_name)
    indexes = inspector.get_indexes(table_name)

    return {
        "name": table_name,
        "row_count": row_count,
        "columns": columns,
        "foreign_keys": foreign_keys,
        "indexes": indexes,
        "primary_key": get_single_primary_key(table),
    }


def get_database_options():
    return [
        {"key": "main", "label": get_database_label("main"), "details": get_database_details("main")},
        {"key": "csr", "label": get_database_label("csr"), "details": get_database_details("csr")},
    ]


def build_business_integration_config(business, base_url):
    config = business.widget_config().copy()
    config.update(
        {
            "widgetKey": business.widget_key,
            "baseUrl": base_url.rstrip("/"),
            "apiUrl": "/api/chat",
            "pollUrl": "/api/chat/poll",
            "requestTimeout": (business.api_timeout_seconds or 30) * 1000,
        }
    )
    return config


def build_csr_integration_config(csr_business, base_url):
    return {
        "baseUrl": base_url.rstrip("/"),
        "csrKey": csr_business.csr_widget_key,
        "containerId": csr_business.container_id or "csr-console",
        "primaryColor": csr_business.primary_color or "#2563EB",
        "chatListPoll": csr_business.chat_list_poll or 5000,
        "messagePoll": csr_business.message_poll or 3000,
        "autoActivate": bool(csr_business.auto_activate),
        "widgetTitle": csr_business.widget_title or "Live Chat",
    }


@app.context_processor
def inject_global_template_values():
    return {"current_user": current_user(), "app_base_url": request.url_root.rstrip("/")}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        company = request.form.get("company", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([first_name, last_name, email, password]):
            flash("Please fill all required fields.", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("This email is already registered.", "error")
            return render_template("register.html")

        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            company=company,
            phone=phone,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = get_safe_post_login_redirect()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("login.html", next_url=next_url)

        session["user_id"] = user.id
        flash("Welcome back.", "success")
        return redirect(next_url)

    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    businesses = Business.query.filter_by(user_id=user.id).order_by(Business.updated_at.desc()).all()
    csr_business_count = CsrBusiness.query.filter_by(user_id=user.id).count()
    csr_conversation_count = (
        CsrConversation.query.join(CsrBusiness)
        .filter(CsrBusiness.user_id == user.id)
        .count()
    )

    total_sessions = (
        ChatSession.query.join(Business)
        .filter(Business.user_id == user.id)
        .count()
    )
    total_messages = (
        ChatMessage.query.join(ChatSession).join(Business)
        .filter(Business.user_id == user.id)
        .count()
    )
    total_api_calls = (
        WidgetApiLog.query.join(Business)
        .filter(Business.user_id == user.id)
        .count()
    )
    recent_logs = (
        WidgetApiLog.query.join(Business)
        .filter(Business.user_id == user.id)
        .order_by(WidgetApiLog.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "dashboard.html",
        businesses=businesses,
        csr_business_count=csr_business_count,
        csr_conversation_count=csr_conversation_count,
        total_sessions=total_sessions,
        total_messages=total_messages,
        total_api_calls=total_api_calls,
        recent_logs=recent_logs,
    )


@app.route("/business/new", methods=["GET", "POST"])
@login_required
def business_new():
    user = current_user()
    business = Business(user_id=user.id, name="", is_active=True)
    ensure_business_tokens(business)
    return handle_business_form(business, is_new=True)


@app.route("/business/<int:business_id>/edit", methods=["GET", "POST"])
@login_required
def business_edit(business_id):
    user = current_user()
    business = find_business_for_user(business_id, user)
    if not business:
        flash("Business not found.", "error")
        return redirect(url_for("dashboard"))
    return handle_business_form(business, is_new=False)


def handle_business_form(business, is_new):
    integration_config = None
    embed_script_url = None
    csr_business = None
    csr_integration_config = None
    csr_embed_script_url = None
    if not is_new and business.widget_key:
        csr_business = ensure_csr_business_for_business(business)
        db.session.commit()
        integration_config = build_business_integration_config(business, request.url_root.rstrip("/"))
        embed_script_url = f"{request.url_root.rstrip('/')}{url_for('embed_widget_js', widget_key=business.widget_key)}"
        csr_integration_config = build_csr_integration_config(csr_business, request.url_root.rstrip("/"))
        csr_embed_script_url = f"{request.url_root.rstrip('/')}{url_for('embed_csr_widget_js', csr_key=csr_business.csr_widget_key)}"

    if request.method == "POST":
        business.name = request.form.get("name", "").strip()
        business.description = request.form.get("description", "").strip()
        business.website = request.form.get("website", "").strip()
        business.phone = request.form.get("phone", "").strip()
        business.authorized_domains = request.form.get("authorized_domains", "").strip()
        business.widget_title = request.form.get("widget_title", "").strip()
        business.welcome_message = request.form.get("welcome_message", "").strip()
        business.primary_color = request.form.get("primary_color", "#5B50E7").strip() or "#5B50E7"
        business.button_color = request.form.get("button_color", "#5B50E7").strip() or "#5B50E7"
        business.header_background = request.form.get(
            "header_background",
            "linear-gradient(to right, #5D5CFF, #7A2EE6)",
        ).strip() or "linear-gradient(to right, #5D5CFF, #7A2EE6)"
        business.background_color = request.form.get("background_color", "#121826").strip() or "#121826"
        business.message_area_bg_color = request.form.get("message_area_bg_color", "#0d1520").strip() or "#0d1520"
        business.agent_icon = request.form.get("agent_icon", "").strip()
        business.namespace_override = request.form.get("namespace_override", "").strip()
        business.n8n_webhook_url = DEFAULT_WEBHOOK_URL
        business.n8n_instance_id = request.form.get("n8n_instance_id", DEFAULT_INSTANCE_ID).strip()
        business.external_csr_api_endpoint = request.form.get("external_csr_api_endpoint", "").strip().rstrip("/")
        submitted_verify_base = request.form.get("chatbot_verify_base_url", "").strip().rstrip("/")
        if submitted_verify_base:
            business.chatbot_verify_base_url = submitted_verify_base
        elif not business.chatbot_verify_base_url:
            business.chatbot_verify_base_url = DEFAULT_CHATBOT_VERIFY_BASE_URL
        submitted_service_secret = request.form.get("chatbot_service_secret", "").strip()
        if submitted_service_secret:
            business.chatbot_service_secret = submitted_service_secret
        elif not business.chatbot_service_secret:
            business.chatbot_service_secret = DEFAULT_CHATBOT_SERVICE_SECRET
        business.api_timeout_seconds = int(request.form.get("api_timeout_seconds", 30) or 30)
        business.is_active = request.form.get("is_active") == "on"
        ensure_business_tokens(business)

        if not business.name:
            flash("Business name is required.", "error")
            return render_template(
                "business_form.html",
                business=business,
                is_new=is_new,
                integration_config=integration_config,
                embed_script_url=embed_script_url,
                csr_business=csr_business,
                csr_integration_config=csr_integration_config,
                csr_embed_script_url=csr_embed_script_url,
                default_webhook_url=DEFAULT_WEBHOOK_URL,
            )

        if is_new:
            db.session.add(business)

        db.session.commit()
        csr_business = ensure_csr_business_for_business(business)
        csr_business.widget_title = request.form.get("csr_widget_title", "").strip() or f"{business.name} CSR Console"
        csr_business.primary_color = request.form.get("csr_primary_color", business.primary_color or "#2563EB").strip() or "#2563EB"
        csr_business.container_id = request.form.get("csr_container_id", "csr-console").strip() or "csr-console"
        csr_business.chat_list_poll = int(request.form.get("csr_chat_list_poll", 5000) or 5000)
        csr_business.message_poll = int(request.form.get("csr_message_poll", 3000) or 3000)
        csr_business.auto_activate = request.form.get("csr_auto_activate") == "on"
        csr_business.is_active = request.form.get("csr_is_active") == "on" if "csr_is_active" in request.form else business.is_active
        business.csr_key = csr_business.csr_widget_key
        db.session.commit()
        flash("Business saved successfully.", "success")
        return redirect(url_for("business_edit", business_id=business.id))

    return render_template(
        "business_form.html",
        business=business,
        is_new=is_new,
        integration_config=integration_config,
        embed_script_url=embed_script_url,
        csr_business=csr_business,
        csr_integration_config=csr_integration_config,
        csr_embed_script_url=csr_embed_script_url,
        default_webhook_url=DEFAULT_WEBHOOK_URL,
    )


@app.route("/business/<int:business_id>/rotate-widget-key", methods=["POST"])
@login_required
def business_rotate_widget_key(business_id):
    user = current_user()
    business = find_business_for_user(business_id, user)
    if not business:
        flash("Business not found.", "error")
        return redirect(url_for("dashboard"))

    business.widget_key = generate_unique_business_token("widget_key")
    db.session.commit()
    flash("Widget key rotated successfully.", "success")
    return redirect(url_for("business_edit", business_id=business.id))


@app.route("/business/<int:business_id>/rotate-csr-key", methods=["POST"])
@login_required
def business_rotate_csr_key(business_id):
    user = current_user()
    business = find_business_for_user(business_id, user)
    if not business:
        flash("Business not found.", "error")
        return redirect(url_for("dashboard"))

    business.csr_key = generate_unique_business_token("csr_key")
    csr_business = ensure_csr_business_for_business(business)
    csr_business.csr_widget_key = business.csr_key
    db.session.commit()
    flash("CSR key rotated successfully.", "success")
    return redirect(url_for("business_edit", business_id=business.id))


@app.route("/business/<int:business_id>/delete", methods=["POST"])
@login_required
def business_delete(business_id):
    user = current_user()
    business = find_business_for_user(business_id, user)
    if not business:
        flash("Business not found.", "error")
        return redirect(url_for("dashboard"))

    csr_business = CsrBusiness.query.filter_by(linked_business_id=business.id).first()
    if csr_business:
        db.session.delete(csr_business)
    db.session.delete(business)
    db.session.commit()
    flash("Business deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/generate_widget_key", methods=["POST"])
@login_required
def generate_widget_key():
    user = current_user()
    business_id = request.form.get("business_id") or (request.get_json(silent=True) or {}).get("business_id")
    if not business_id:
        return jsonify({"success": False, "message": "business_id is required"}), 400

    business = find_business_for_user(int(business_id), user)
    if not business:
        return jsonify({"success": False, "message": "Business not found"}), 404

    business.widget_key = generate_unique_business_token("widget_key")
    db.session.commit()
    return jsonify({"success": True, "widget_key": business.widget_key})


@app.route("/logs")
@login_required
def logs_page():
    user = current_user()
    selected_business_id = request.args.get("business_id", type=int)
    visitor_id = request.args.get("visitor_id", "").strip()

    businesses = Business.query.filter_by(user_id=user.id).order_by(Business.name.asc()).all()

    sessions_query = ChatSession.query.join(Business).filter(Business.user_id == user.id)
    logs_query = WidgetApiLog.query.join(Business).filter(Business.user_id == user.id)

    if selected_business_id:
        sessions_query = sessions_query.filter(ChatSession.business_id == selected_business_id)
        logs_query = logs_query.filter(WidgetApiLog.business_id == selected_business_id)

    if visitor_id:
        sessions_query = sessions_query.filter(ChatSession.user_identifier.ilike(f"%{visitor_id}%"))
        logs_query = logs_query.filter(WidgetApiLog.visitor_id.ilike(f"%{visitor_id}%"))

    sessions = sessions_query.order_by(ChatSession.updated_at.desc()).limit(50).all()
    api_logs = logs_query.order_by(WidgetApiLog.created_at.desc()).limit(100).all()

    return render_template(
        "logs.html",
        businesses=businesses,
        selected_business_id=selected_business_id,
        visitor_id=visitor_id,
        sessions=sessions,
        api_logs=api_logs,
    )


@app.route("/sessions/<int:session_id>")
@login_required
def session_detail(session_id):
    user = current_user()
    chat_session = (
        ChatSession.query.join(Business)
        .filter(ChatSession.id == session_id, Business.user_id == user.id)
        .first()
    )
    if not chat_session:
        flash("Session not found.", "error")
        return redirect(url_for("logs_page"))

    messages = ChatMessage.query.filter_by(session_id=chat_session.id).order_by(ChatMessage.timestamp.asc()).all()
    api_logs = WidgetApiLog.query.filter_by(session_id=chat_session.id).order_by(WidgetApiLog.created_at.desc()).all()
    return render_template("session_detail.html", chat_session=chat_session, messages=messages, api_logs=api_logs)


@app.route("/tester")
@login_required
def tester():
    user = current_user()
    businesses = Business.query.filter_by(user_id=user.id, is_active=True).order_by(Business.name.asc()).all()
    selected_business_id = request.args.get("business_id", type=int)
    selected_business = None
    if selected_business_id:
        selected_business = find_business_for_user(selected_business_id, user)
    if not selected_business and businesses:
        selected_business = businesses[0]

    return render_template("tester.html", businesses=businesses, selected_business=selected_business)


@app.route("/tester/preview/<int:business_id>")
@login_required
def tester_preview(business_id):
    user = current_user()
    business = find_business_for_user(business_id, user)
    if not business:
        return "Business not found", 404
    return render_template("widget_preview.html", business=business)


@app.route("/tester/csr-preview/<int:business_id>")
@login_required
def tester_csr_preview(business_id):
    user = current_user()
    business = find_business_for_user(business_id, user)
    if not business:
        return "Business not found", 404
    csr_business = ensure_csr_business_for_business(business)
    db.session.commit()
    return render_template("csr_widget_preview.html", business=business, csr_business=csr_business)


@app.route("/database-admin")
@login_required
def database_admin():
    db_key = "csr" if request.args.get("db_key") == "csr" else "main"
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    table_summaries = [get_table_schema_summary(table_name, db_key) for table_name in table_names]
    return render_template(
        "database_admin.html",
        selected_db_key=db_key,
        database_options=get_database_options(),
        database_details=get_database_details(db_key),
        table_summaries=table_summaries,
    )


@app.route("/database-admin/<table_name>")
@login_required
def database_table_detail(table_name):
    db_key = "csr" if request.args.get("db_key") == "csr" else "main"
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        flash("Table not found.", "error")
        return redirect(url_for("database_admin", db_key=db_key))

    table = get_reflected_table(table_name, db_key)
    primary_key = get_single_primary_key(table)
    limit = max(1, min(request.args.get("limit", 50, type=int), 200))
    offset = max(request.args.get("offset", 0, type=int), 0)

    query = select(table).limit(limit).offset(offset)
    if primary_key is not None:
        query = query.order_by(primary_key.asc())

    with engine.connect() as connection:
        rows = [dict(row) for row in connection.execute(query).mappings().all()]

    row_dicts = []
    for row in rows:
        row_dicts.append(
            {
                "values": row,
                "display_values": {key: stringify_db_value(value) for key, value in row.items()},
                "primary_key_value": stringify_db_value(row.get(primary_key.name)) if primary_key is not None else None,
            }
        )

    total_rows = get_table_schema_summary(table_name, db_key)["row_count"]
    columns = list(table.columns)

    return render_template(
        "database_table_detail.html",
        db_key=db_key,
        table_name=table_name,
        table_summary=get_table_schema_summary(table_name, db_key),
        columns=columns,
        rows=row_dicts,
        primary_key=primary_key,
        limit=limit,
        offset=offset,
        total_rows=total_rows,
    )


@app.route("/database-admin/<table_name>/row/<row_id>/edit", methods=["GET", "POST"])
@login_required
def database_row_edit(table_name, row_id):
    db_key = "csr" if request.args.get("db_key") == "csr" else "main"
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        flash("Table not found.", "error")
        return redirect(url_for("database_admin", db_key=db_key))

    table = get_reflected_table(table_name, db_key)
    primary_key = get_single_primary_key(table)
    if primary_key is None:
        flash("Editing is only supported for tables with a single primary key.", "error")
        return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))

    try:
        parsed_row_id = parse_column_value(row_id, primary_key, allow_primary_key=True)
    except (TypeError, ValueError) as exc:
        flash(f"Invalid row id: {exc}", "error")
        return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))

    with engine.connect() as connection:
        row = connection.execute(
            select(table).where(primary_key == parsed_row_id)
        ).mappings().first()

    if row is None:
        flash("Row not found.", "error")
        return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))

    row = dict(row)

    if request.method == "POST":
        try:
            values_to_update = {}
            for column in table.columns:
                if column.primary_key:
                    continue
                form_value = request.form.get(column.name, "")
                values_to_update[column.name] = parse_column_value(form_value, column)
        except (TypeError, ValueError) as exc:
            flash(f"Invalid value: {exc}", "error")
            editable_columns = []
            for column in table.columns:
                editable_columns.append(
                    {
                        "name": column.name,
                        "type": str(column.type),
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "value": request.form.get(column.name, stringify_db_value(row.get(column.name))),
                    }
                )
            return render_template(
                "database_row_edit.html",
                db_key=db_key,
                table_name=table_name,
                row_id=row_id,
                primary_key=primary_key,
                editable_columns=editable_columns,
            )

        with engine.begin() as connection:
            connection.execute(
                update(table)
                .where(primary_key == parsed_row_id)
                .values(**values_to_update)
            )

        flash(f"Updated row in {table_name}.", "success")
        return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))

    editable_columns = []
    for column in table.columns:
        editable_columns.append(
            {
                "name": column.name,
                "type": str(column.type),
                "nullable": column.nullable,
                "primary_key": column.primary_key,
                "value": stringify_db_value(row.get(column.name)),
            }
        )

    return render_template(
        "database_row_edit.html",
        db_key=db_key,
        table_name=table_name,
        row_id=row_id,
        primary_key=primary_key,
        editable_columns=editable_columns,
    )


@app.route("/database-admin/<table_name>/row/<row_id>/delete", methods=["POST"])
@login_required
def database_row_delete(table_name, row_id):
    db_key = "csr" if request.args.get("db_key") == "csr" else "main"
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        flash("Table not found.", "error")
        return redirect(url_for("database_admin", db_key=db_key))

    table = get_reflected_table(table_name, db_key)
    primary_key = get_single_primary_key(table)
    if primary_key is None:
        flash("Deleting rows is only supported for tables with a single primary key.", "error")
        return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))

    try:
        parsed_row_id = parse_column_value(row_id, primary_key, allow_primary_key=True)
    except (TypeError, ValueError) as exc:
        flash(f"Invalid row id: {exc}", "error")
        return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))

    with engine.begin() as connection:
        connection.execute(delete(table).where(primary_key == parsed_row_id))

    flash(f"Deleted row {row_id} from {table_name}.", "success")
    return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))


@app.route("/database-admin/<table_name>/clear", methods=["POST"])
@login_required
def database_table_clear(table_name):
    db_key = "csr" if request.args.get("db_key") == "csr" else "main"
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        flash("Table not found.", "error")
        return redirect(url_for("database_admin", db_key=db_key))

    table = get_reflected_table(table_name, db_key)
    with engine.begin() as connection:
        connection.execute(delete(table))

    flash(f"Deleted all rows from {table_name}.", "success")
    return redirect(url_for("database_table_detail", table_name=table_name, db_key=db_key))


@app.route("/database-admin/<table_name>/drop", methods=["POST"])
@login_required
def database_table_drop(table_name):
    db_key = "csr" if request.args.get("db_key") == "csr" else "main"
    engine = get_engine_for_db_key(db_key)
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        flash("Table not found.", "error")
        return redirect(url_for("database_admin", db_key=db_key))

    table = get_reflected_table(table_name, db_key)
    table.drop(bind=engine)
    flash(f"Dropped table {table_name}.", "success")
    return redirect(url_for("database_admin", db_key=db_key))


@app.route("/embed/<widget_key>.js")
def embed_widget_js(widget_key):
    business = Business.query.filter_by(widget_key=widget_key, is_active=True).first()
    if not business:
        return Response("console.error('Invalid widget key');", mimetype="application/javascript", status=404)

    base_url = request.url_root.rstrip("/")
    integration_config = build_business_integration_config(business, base_url)
    script = f"""
(function() {{
  window.AuthenticatedChatWidgetConfig = Object.assign(
    {{}},
    {json.dumps(integration_config)},
    window.AuthenticatedChatWidgetConfig || {{}}
  );

  var existing = document.querySelector('script[data-widget-key="{business.widget_key}"]');
  if (existing) return;

  var script = document.createElement('script');
  script.src = {json.dumps(base_url + url_for('widget_assets', filename='authenticated-chat-widget.js') + '?v=20260825g')};
  script.async = true;
  script.dataset.widgetKey = {json.dumps(business.widget_key)};
  document.head.appendChild(script);
}})();
""".strip()
    return Response(script, mimetype="application/javascript")


@app.route("/embed/csr/<csr_key>.js")
def embed_csr_widget_js(csr_key):
    csr_business = CsrBusiness.query.filter_by(csr_widget_key=csr_key, is_active=True).first()
    if not csr_business:
        return Response("console.error('Invalid CSR widget key');", mimetype="application/javascript", status=404)

    base_url = request.url_root.rstrip("/")
    integration_config = build_csr_integration_config(csr_business, base_url)
    container_id = integration_config["containerId"]
    script = f"""
(function() {{
  window.CSRDashboardWidgetConfig = Object.assign(
    {{}},
    {json.dumps(integration_config)},
    window.CSRDashboardWidgetConfig || {{}}
  );

  if (!document.getElementById({json.dumps(container_id)})) {{
    var container = document.createElement('div');
    container.id = {json.dumps(container_id)};
    container.style.width = '100%';
    container.style.minHeight = '720px';
    container.style.height = '100vh';
    document.body.appendChild(container);
  }}

  var existing = document.querySelector('script[data-csr-key="{csr_key}"]');
  if (existing) return;

  var script = document.createElement('script');
  script.src = {json.dumps(base_url + url_for('widget_assets', filename='csr-dashboard-widget.js'))};
  script.async = true;
  script.dataset.csrKey = {json.dumps(csr_key)};
  script.dataset.baseUrl = {json.dumps(base_url)};
  script.dataset.containerId = {json.dumps(container_id)};
  script.dataset.primaryColor = {json.dumps(csr_business.primary_color or '#2563EB')};
  script.dataset.chatListPoll = {json.dumps(str(csr_business.chat_list_poll or 5000))};
  script.dataset.messagePoll = {json.dumps(str(csr_business.message_poll or 3000))};
  script.dataset.autoActivate = {json.dumps('true' if csr_business.auto_activate else 'false')};
  script.dataset.csrKey = {json.dumps(csr_key)};
  script.setAttribute('data-csr-key', {json.dumps(csr_key)});
  document.head.appendChild(script);
}})();
""".strip()
    return Response(script, mimetype="application/javascript")


@app.route("/widget-assets/<path:filename>")
def widget_assets(filename):
    if filename not in {
        "chat-widget.js",
        "authenticated-chat-widget.js",
        "csr-dashboard-widget.js",
        "host-csr-console-widget.js",
    }:
        return "Not found", 404
    return send_from_directory(WIDGET_ASSET_DIR, filename)


@app.route("/get_user_namespace")
def get_user_namespace():
    widget_key = request.args.get("widget_key")
    if widget_key:
        business = Business.query.filter_by(widget_key=widget_key, is_active=True).first()
        if business:
            return jsonify({"namespace": business.namespace()})

    user = current_user()
    if user:
        business = Business.query.filter_by(user_id=user.id).first()
        if business:
            return jsonify({"namespace": business.namespace()})

    return jsonify({"namespace": "default"})


@app.route("/validate_widget", methods=["POST"])
def validate_widget():
    payload = request.get_json(silent=True) or {}
    widget_key = payload.get("widget_key")
    domain = payload.get("domain")
    visitor_id = payload.get("visitor_id")
    business = Business.query.filter_by(widget_key=widget_key, is_active=True).first() if widget_key else None

    if not widget_key or not domain:
        response_payload = {"valid": False, "message": "Missing widget key or domain."}
        record_widget_log(
            "/validate_widget",
            "POST",
            payload,
            response_payload,
            400,
            business=business,
            visitor_id=visitor_id,
            domain=normalize_domain(domain),
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 400

    if not business:
        response_payload = {"valid": False, "message": "Invalid widget key."}
        record_widget_log(
            "/validate_widget",
            "POST",
            payload,
            response_payload,
            404,
            visitor_id=visitor_id,
            domain=normalize_domain(domain),
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 404

    is_authorized, parsed_domain = business_is_authorized_for_domain(business, domain)
    if not is_authorized:
        response_payload = {"valid": False, "message": "Domain not authorized."}
        record_widget_log(
            "/validate_widget",
            "POST",
            payload,
            response_payload,
            403,
            business=business,
            visitor_id=visitor_id,
            domain=parsed_domain,
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 403

    chat_session = None
    session_mode = "active_ai"
    if visitor_id:
        chat_session = ChatSession.query.filter_by(
            user_identifier=visitor_id,
            business_id=business.id,
        ).order_by(ChatSession.updated_at.desc()).first()
        if chat_session:
            session_mode = chat_session.status

    auth_mode, authenticated_user, auth_error, auth_status = verify_widget_identity(
        business,
        payload,
        cached_session=chat_session,
        allow_cached=True,
    )
    if auth_error:
        response_payload = {"valid": False, "message": auth_error}
        record_widget_log(
            "/validate_widget",
            "POST",
            payload,
            response_payload,
            auth_status,
            business=business,
            chat_session=chat_session,
            visitor_id=visitor_id,
            domain=parsed_domain,
            error_message=auth_error,
        )
        return jsonify(response_payload), auth_status

    # Persist verified identity once so later chat/poll calls reuse the cache.
    if visitor_id:
        _, auth_token, _ = normalize_auth_payload(payload)
        chat_session = get_or_create_chat_session(
            business,
            visitor_id,
            chat_session.user_type if chat_session else None,
            parsed_domain,
            auth_mode=auth_mode,
            auth_token=auth_token,
            authenticated_user=authenticated_user,
        )
        session_mode = chat_session.status

    response_payload = {
        "valid": True,
        "business_name": business.name,
        "session_mode": session_mode,
        "user_type": chat_session.user_type if chat_session else None,
        "authentication": {
            "mode": auth_mode,
            "user": authenticated_user,
        },
        "widget_config": business.widget_config(),
    }
    record_widget_log(
        "/validate_widget",
        "POST",
        payload,
        response_payload,
        200,
        business=business,
        chat_session=chat_session,
        visitor_id=visitor_id,
        domain=parsed_domain,
    )
    return jsonify(response_payload)


@app.route("/api/chatbot/token", methods=["POST"])
def api_chatbot_token():
    """Proxy endpoint: exchange a logged-in user's Bearer token for a FLT chatbot token."""
    business = None
    try:
        payload = request.get_json(silent=True) or {}
        widget_key = payload.get("widget_key")
        business = Business.query.filter_by(widget_key=widget_key, is_active=True).first() if widget_key else None

        auth_header = request.headers.get("Authorization") or ""
        if not auth_header.startswith("Bearer "):
            response_payload = {"error": "Authorization header must be Bearer <token>"}
            record_widget_log(
                "/api/chatbot/token",
                "POST",
                payload,
                response_payload,
                401,
                business=business,
                error_message="Missing or invalid Authorization header",
            )
            return jsonify(response_payload), 401

        user_bearer_token = auth_header[7:].strip()
        if not user_bearer_token:
            response_payload = {"error": "Bearer token is required"}
            record_widget_log(
                "/api/chatbot/token",
                "POST",
                payload,
                response_payload,
                401,
                business=business,
                error_message="Empty bearer token",
            )
            return jsonify(response_payload), 401

        if not business:
            response_payload = {"error": "Invalid widget key"}
            record_widget_log(
                "/api/chatbot/token",
                "POST",
                payload,
                response_payload,
                404,
                business=business,
                error_message="Invalid widget key",
            )
            return jsonify(response_payload), 404

        chatbot_token = fetch_chatbot_token(business, user_bearer_token)
        response_payload = {"chatbot_token": chatbot_token}
        record_widget_log(
            "/api/chatbot/token",
            "POST",
            payload,
            response_payload,
            200,
            business=business,
        )
        return jsonify(response_payload)
    except RuntimeError as exc:
        response_payload = {"error": "Token authentication failed", "message": str(exc)}
        record_widget_log(
            "/api/chatbot/token",
            "POST",
            payload if 'payload' in locals() else {},
            response_payload,
            401,
            business=business if 'business' in locals() else None,
            error_message=str(exc),
        )
        return jsonify(response_payload), 401
    except Exception as exc:
        response_payload = {"error": "Token service error", "message": str(exc)}
        record_widget_log(
            "/api/chatbot/token",
            "POST",
            payload if 'payload' in locals() else {},
            response_payload,
            500,
            business=business if 'business' in locals() else None,
            error_message=str(exc),
        )
        return jsonify(response_payload), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.get_json(silent=True) or {}
    business = None
    chat_session = None
    visitor_id = payload.get("visitor_id") or request.remote_addr
    domain = normalize_domain(request.headers.get("Origin") or request.headers.get("Referer") or "")

    try:
        raw_image_attachments = payload.get("images") or payload.get("image_attachments")
        has_image_attachments = bool(raw_image_attachments)
        if "message" not in payload and not has_image_attachments:
            response_payload = {"error": "No message provided"}
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                400,
                visitor_id=visitor_id,
                domain=domain,
                error_message="No message provided",
            )
            return jsonify(response_payload), 400

        message = str(payload.get("message") or "").strip()
        widget_key = payload.get("widget_key")
        requested_user_type = normalize_user_type(
            payload.get("user_type") or payload.get("userType") or payload.get("usertype")
        )

        if not widget_key:
            response_payload = {"error": "Widget key required"}
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                401,
                visitor_id=visitor_id,
                domain=domain,
                error_message="Widget key required",
            )
            return jsonify(response_payload), 401

        business = Business.query.filter_by(widget_key=widget_key, is_active=True).first()
        if not business:
            response_payload = {"error": "Invalid widget key"}
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                401,
                visitor_id=visitor_id,
                domain=domain,
                error_message="Invalid widget key",
            )
            return jsonify(response_payload), 401

        cached_session = ChatSession.query.filter_by(
            user_identifier=visitor_id,
            business_id=business.id,
        ).order_by(ChatSession.updated_at.desc()).first()
        # Reuse the one-time FLT verify result for this visitor token.
        auth_mode, authenticated_user, auth_error, auth_status = verify_widget_identity(
            business,
            payload,
            cached_session=cached_session,
            allow_cached=True,
        )
        if auth_error:
            response_payload = {"error": "Authentication failed", "message": auth_error}
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                auth_status,
                business=business,
                chat_session=cached_session,
                visitor_id=visitor_id,
                domain=domain,
                error_message=auth_error,
            )
            return jsonify(response_payload), auth_status

        _, auth_token, _ = normalize_auth_payload(payload)
        chat_session = get_or_create_chat_session(
            business,
            visitor_id,
            requested_user_type,
            domain,
            auth_mode=auth_mode,
            auth_token=auth_token,
            authenticated_user=authenticated_user,
        )
        session_user_type = chat_session.user_type or requested_user_type
        if has_image_attachments and chat_session.status != "active_csr":
            response_payload = {
                "error": "Image upload unavailable",
                "message": "Image upload is available after you are connected to an agent.",
                "mode": chat_session.status,
                "auth_mode": chat_session.auth_mode,
                "authentication": {
                    "mode": chat_session.auth_mode,
                    "user": authenticated_user,
                },
                "user_type": session_user_type,
            }
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                400,
                business=business,
                chat_session=chat_session,
                visitor_id=visitor_id,
                domain=domain,
                error_message=response_payload["message"],
            )
            return jsonify(response_payload), 400

        image_attachments = normalize_image_attachments(
            raw_image_attachments,
            request.url_root.rstrip("/"),
        )

        user_msg = ChatMessage(
            session_id=chat_session.id,
            sender_type="user",
            content=message,
            image_attachments=serialize_image_attachments(image_attachments),
        )
        db.session.add(user_msg)
        db.session.commit()

        if chat_session.status in ["pending_csr", "active_csr"]:
            sync_chat_session_to_csr(chat_session, business)
            external_url = (business.external_csr_api_endpoint or "").rstrip("/")
            if external_url:
                try:
                    csr_payload = add_image_payload_fields(
                        {
                            "visitor_id": chat_session.user_identifier,
                            "content": message,
                            "user_type": session_user_type,
                            "authentication": {
                                "mode": chat_session.auth_mode,
                                "user": authenticated_user,
                            },
                        },
                        image_attachments,
                    )
                    requests.post(
                        f"{external_url}/send",
                        json=csr_payload,
                        timeout=3,
                    )
                except Exception:
                    pass

            response_payload = {
                "output": "",
                "mode": chat_session.status,
                "auth_mode": chat_session.auth_mode,
                "authentication": {
                    "mode": chat_session.auth_mode,
                    "user": authenticated_user,
                },
                "user_msg_id": user_msg.id,
                "user_type": session_user_type,
                "images": image_attachments,
            }
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                200,
                business=business,
                chat_session=chat_session,
                visitor_id=visitor_id,
                domain=domain,
            )
            return jsonify(response_payload)

        # Temporary fallback while AI webhook is unavailable:
        # visitor phrases like "talk to agent" escalate to CSR directly.
        message_lower = message.lower()
        user_csr_request_phrases = [
            "talk to agent",
            "talk to an agent",
            "talk to a agent",
            "talk with agent",
            "talk with an agent",
            "talk to human",
            "talk to a human",
            "talk to csr",
            "connect to csr",
            "connect to agent",
            "connect me to agent",
            "connect me with agent",
            "connect me to a human",
            "speak to agent",
            "speak to a human",
            "speak to human",
            "real agent",
            "live agent",
            "human agent",
            "i want csr",
            "i wants to connect to csr",
            "i want to connect to csr",
        ]
        user_requests_csr = any(phrase in message_lower for phrase in user_csr_request_phrases)

        if user_requests_csr and chat_session.status == "active_ai":
            ai_output = "You will be connected by our agent shortly."
            ai_msg = ChatMessage(session_id=chat_session.id, sender_type="ai", content=ai_output)
            db.session.add(ai_msg)
            chat_session.status = "pending_csr"
            previous_messages = ChatMessage.query.filter_by(session_id=chat_session.id).order_by(ChatMessage.timestamp).all()
            transcript = "\n".join(f"{msg.sender_type}: {msg.content}" for msg in previous_messages)
            auth_label = ""
            if chat_session.auth_mode == "authenticated" and authenticated_user:
                auth_label = (
                    f" Authenticated user: {authenticated_user.get('name')} "
                    f"(ID {authenticated_user.get('id')})."
                )
            chat_session.summary = (
                f"Visitor requested human agent.{auth_label} Transcript preview: {transcript[:200]}..."
            )
            db.session.commit()
            sync_chat_session_to_csr(chat_session, business)

            csr_relayed = False
            csr_relay_error = None
            csr_assignment = None
            relay_payload = None
            external_url = (business.external_csr_api_endpoint or "").rstrip("/")

            if external_url:
                try:
                    current_messages = [
                        message_to_transcript_payload(msg)
                        for msg in previous_messages
                        if msg.sender_type != "csr"
                    ]
                    relay_payload = {
                        "visitor_id": chat_session.user_identifier,
                        "transcript": current_messages,
                        "user_type": session_user_type,
                        "authentication": {
                            "mode": chat_session.auth_mode,
                            "user": authenticated_user,
                        },
                    }
                    relay_response = requests.post(f"{external_url}/init", json=relay_payload, timeout=5)
                    relay_json = {}
                    try:
                        relay_json = relay_response.json()
                    except ValueError:
                        relay_json = {}
                    if relay_response.ok:
                        csr_relayed = True
                        csr_assignment = {
                            "chat_id": relay_json.get("chat_id"),
                            "assigned_csr_id": relay_json.get("assigned_csr_id"),
                            "assigned_csr_name": relay_json.get("assigned_csr_name"),
                            "status": relay_json.get("status"),
                        }
                    else:
                        csr_relay_error = f"{relay_response.status_code}: {relay_response.text}"
                except Exception as exc:
                    csr_relay_error = str(exc)

            response_payload = {
                "output": ai_output,
                "mode": "pending_csr",
                "auth_mode": chat_session.auth_mode,
                "authentication": {
                    "mode": chat_session.auth_mode,
                    "user": authenticated_user,
                },
                "user_msg_id": user_msg.id,
                "ai_msg_id": ai_msg.id,
                "user_type": session_user_type,
                "csr_relayed": csr_relayed,
                "csr_relay_error": csr_relay_error,
                "csr_assignment": csr_assignment,
                "csr_relay_endpoint": f"{external_url}/init" if external_url else None,
                "csr_relay_payload": relay_payload if relay_payload and not csr_relayed else None,
            }
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                200,
                business=business,
                chat_session=chat_session,
                visitor_id=visitor_id,
                domain=domain,
            )
            return jsonify(response_payload)

        headers = {"Content-Type": "application/json"}
        instance_id = (business.n8n_instance_id or "").strip() or DEFAULT_INSTANCE_ID
        if instance_id:
            headers["X-Instance-Id"] = instance_id

        webhook_url = (business.n8n_webhook_url or "").strip() or DEFAULT_WEBHOOK_URL
        webhook_payload = add_image_payload_fields(
            {
                "action": "sendMessage",
                "chatInput": message,
                "prompt": message,
                "namespace": business.namespace(),
                "sessionId": chat_session.user_identifier,
                "mode": chat_session.status,
                "user_type": session_user_type,
                "authentication": {
                    "mode": chat_session.auth_mode,
                    "user": authenticated_user,
                },
            },
            image_attachments,
        )

        ai_output = None
        webhook_error = None
        try:
            response = requests.post(
                webhook_url,
                json=webhook_payload,
                headers=headers,
                timeout=business.api_timeout_seconds or 30,
            )
            if response.status_code == 200:
                result = response.json()
                ai_output = result.get("output", "")
                if not ai_output:
                    webhook_error = "AI webhook returned empty output"
            else:
                webhook_error = f"AI webhook HTTP {response.status_code}: {response.text[:300]}"
        except Exception as exc:
            ai_output = None
            webhook_error = f"AI webhook error: {exc}"

        if webhook_error:
            print(f"[AI WEBHOOK] {webhook_url} -> {webhook_error}")

        if not ai_output:
            ai_output = "I'm sorry, I'm having trouble processing your request. Please try again."

        ai_msg = ChatMessage(session_id=chat_session.id, sender_type="ai", content=ai_output)
        db.session.add(ai_msg)
        db.session.commit()

        ai_lower = ai_output.lower()
        csr_trigger_phrases = [
            "connected by our agent",
            "connected with our agent",
            "connected to our agent",
            "connect you with an agent",
            "connect you to an agent",
            "connect you with a human",
            "transfer you to",
            "transferring you to",
            "connecting you to",
            "connecting you with",
            "agent will be with you",
            "agent shortly",
            "human agent",
            "live agent",
            "support agent will",
            "representative will",
            "escalating to",
            "escalate your request",
            "handing over to",
            "hand you over to",
        ]
        ai_triggers_csr = any(phrase in ai_lower for phrase in csr_trigger_phrases)

        if ai_triggers_csr and chat_session.status == "active_ai":
            chat_session.status = "pending_csr"
            previous_messages = ChatMessage.query.filter_by(session_id=chat_session.id).order_by(ChatMessage.timestamp).all()
            transcript = "\n".join(f"{msg.sender_type}: {msg.content}" for msg in previous_messages)
            auth_label = ""
            if chat_session.auth_mode == "authenticated" and authenticated_user:
                auth_label = (
                    f" Authenticated user: {authenticated_user.get('name')} "
                    f"(ID {authenticated_user.get('id')})."
                )
            chat_session.summary = (
                f"AI escalated to human agent.{auth_label} Transcript preview: {transcript[:200]}..."
            )
            db.session.commit()
            sync_chat_session_to_csr(chat_session, business)

            csr_relayed = False
            csr_relay_error = None
            csr_assignment = None
            relay_payload = None
            external_url = (business.external_csr_api_endpoint or "").rstrip("/")

            if external_url:
                try:
                    current_messages = [
                        message_to_transcript_payload(msg)
                        for msg in previous_messages
                        if msg.sender_type != "csr"
                    ]
                    relay_payload = {
                        "visitor_id": chat_session.user_identifier,
                        "transcript": current_messages,
                        "user_type": session_user_type,
                        "authentication": {
                            "mode": chat_session.auth_mode,
                            "user": authenticated_user,
                        },
                    }
                    relay_response = requests.post(f"{external_url}/init", json=relay_payload, timeout=5)
                    relay_json = {}
                    try:
                        relay_json = relay_response.json()
                    except ValueError:
                        relay_json = {}
                    if relay_response.ok:
                        csr_relayed = True
                        csr_assignment = {
                            "chat_id": relay_json.get("chat_id"),
                            "assigned_csr_id": relay_json.get("assigned_csr_id"),
                            "assigned_csr_name": relay_json.get("assigned_csr_name"),
                            "status": relay_json.get("status"),
                        }
                    else:
                        csr_relay_error = f"{relay_response.status_code}: {relay_response.text}"
                except Exception as exc:
                    csr_relay_error = str(exc)

            response_payload = {
                "output": ai_output,
                "mode": "pending_csr",
                "auth_mode": chat_session.auth_mode,
                "authentication": {
                    "mode": chat_session.auth_mode,
                    "user": authenticated_user,
                },
                "user_msg_id": user_msg.id,
                "ai_msg_id": ai_msg.id,
                "user_type": session_user_type,
                "csr_relayed": csr_relayed,
                "csr_relay_error": csr_relay_error,
                "csr_assignment": csr_assignment,
                "csr_relay_endpoint": f"{external_url}/init" if external_url else None,
                "csr_relay_payload": relay_payload if relay_payload and not csr_relayed else None,
            }
            record_widget_log(
                "/api/chat",
                "POST",
                payload,
                response_payload,
                200,
                business=business,
                chat_session=chat_session,
                visitor_id=visitor_id,
                domain=domain,
            )
            return jsonify(response_payload)

        response_payload = {
            "output": ai_output,
            "mode": chat_session.status,
            "auth_mode": chat_session.auth_mode,
                "authentication": {
                    "mode": chat_session.auth_mode,
                    "user": authenticated_user,
                },
            "session_id": chat_session.id,
            "user_msg_id": user_msg.id,
            "ai_msg_id": ai_msg.id,
            "user_type": session_user_type,
            "timestamp": ai_msg.timestamp.isoformat() + "Z",
        }
        record_widget_log(
            "/api/chat",
            "POST",
            payload,
            response_payload,
            200,
            business=business,
            chat_session=chat_session,
            visitor_id=visitor_id,
            domain=domain,
        )
        return jsonify(response_payload)

    except Exception as exc:
        db.session.rollback()
        response_payload = {
            "error": str(exc),
            "message": "Sorry, I encountered an error. Please try again.",
        }
        record_widget_log(
            "/api/chat",
            "POST",
            payload,
            response_payload,
            500,
            business=business,
            chat_session=chat_session,
            visitor_id=visitor_id,
            domain=domain,
            error_message=str(exc),
        )
        return jsonify(response_payload), 500


@app.route("/api/chat/poll", methods=["POST"])
def api_chat_poll():
    payload = request.get_json(silent=True) or {}
    visitor_id = payload.get("visitor_id")
    since_id = payload.get("since_id", 0)
    widget_key = payload.get("widget_key")
    business = Business.query.filter_by(widget_key=widget_key, is_active=True).first() if widget_key else None

    try:
        if not visitor_id:
            response_payload = {"error": "Visitor ID required"}
            record_widget_log(
                "/api/chat/poll",
                "POST",
                payload,
                response_payload,
                400,
                business=business,
                error_message="Visitor ID required",
            )
            return jsonify(response_payload), 400

        if not business:
            response_payload = {"error": "Valid widget key required"}
            record_widget_log(
                "/api/chat/poll",
                "POST",
                payload,
                response_payload,
                401,
                visitor_id=visitor_id,
                error_message=response_payload["error"],
            )
            return jsonify(response_payload), 401

        session_query = ChatSession.query.filter(ChatSession.user_identifier == visitor_id)
        session_query = session_query.filter(ChatSession.business_id == business.id)

        # Most recently updated session wins — otherwise an older pending_csr row
        # can hide a resolved chat that was switched back to active_ai.
        chat_session = session_query.order_by(
            ChatSession.updated_at.desc(),
            ChatSession.id.desc(),
        ).first()

        if not chat_session:
            response_payload = {"messages": [], "session_status": "none"}
            record_widget_log(
                "/api/chat/poll",
                "POST",
                payload,
                response_payload,
                200,
                business=business,
                visitor_id=visitor_id,
            )
            return jsonify(response_payload)

        auth_mode, authenticated_user, auth_error, auth_status = verify_widget_identity(
            business,
            payload,
            cached_session=chat_session,
            allow_cached=True,
        )
        if auth_error:
            response_payload = {"error": "Authentication failed", "message": auth_error}
            record_widget_log(
                "/api/chat/poll",
                "POST",
                payload,
                response_payload,
                auth_status,
                business=business,
                chat_session=chat_session,
                visitor_id=visitor_id,
                domain=chat_session.domain,
                error_message=auth_error,
            )
            return jsonify(response_payload), auth_status

        messages_query = ChatMessage.query.filter_by(session_id=chat_session.id)
        if since_id:
            messages_query = messages_query.filter(ChatMessage.id > since_id)
        messages = messages_query.order_by(ChatMessage.id.asc()).all()

        response_payload = {
            "messages": [message_to_payload(msg) for msg in messages],
            "session_status": chat_session.status,
            "user_type": chat_session.user_type,
            "authentication": {
                "mode": auth_mode,
                "user": authenticated_user,
            },
        }
        record_widget_log(
            "/api/chat/poll",
            "POST",
            payload,
            response_payload,
            200,
            business=chat_session.business,
            chat_session=chat_session,
            visitor_id=visitor_id,
            domain=chat_session.domain,
        )
        return jsonify(response_payload)

    except Exception as exc:
        db.session.rollback()
        response_payload = {"error": str(exc)}
        record_widget_log(
            "/api/chat/poll",
            "POST",
            payload,
            response_payload,
            500,
            business=business,
            visitor_id=visitor_id,
            error_message=str(exc),
        )
        return jsonify(response_payload), 500


@app.route("/api/csr/external_message", methods=["POST"])
def api_csr_external_message():
    payload = request.get_json(silent=True) or {}
    visitor_id = payload.get("visitor_id")
    message = payload.get("message")
    widget_key = payload.get("widget_key")
    csr_key = payload.get("csr_key")

    business = None
    if widget_key:
        business = Business.query.filter_by(widget_key=widget_key, is_active=True).first()
    if not business and csr_key:
        business = Business.query.filter_by(csr_key=csr_key, is_active=True).first()

    if not visitor_id or not message:
        response_payload = {"success": False, "message": "Missing required fields"}
        record_widget_log(
            "/api/csr/external_message",
            "POST",
            payload,
            response_payload,
            400,
            business=business,
            visitor_id=visitor_id,
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 400

    if not business:
        response_payload = {"success": False, "message": "Invalid widget or CSR key"}
        record_widget_log(
            "/api/csr/external_message",
            "POST",
            payload,
            response_payload,
            401,
            visitor_id=visitor_id,
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 401

    chat_session = ChatSession.query.filter(
        ChatSession.user_identifier == visitor_id,
        ChatSession.business_id == business.id,
        ChatSession.status.in_(["pending_csr", "active_csr"]),
    ).order_by(ChatSession.updated_at.desc()).first()

    if not chat_session:
        response_payload = {"success": False, "message": "No active CSR session"}
        record_widget_log(
            "/api/csr/external_message",
            "POST",
            payload,
            response_payload,
            404,
            business=business,
            visitor_id=visitor_id,
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 404

    if chat_session.status == "pending_csr":
        chat_session.status = "active_csr"

    msg_obj = ChatMessage(session_id=chat_session.id, sender_type="csr", content=message)
    db.session.add(msg_obj)
    chat_session.updated_at = datetime.utcnow()
    db.session.commit()
    sync_chat_session_to_csr(chat_session, business)

    response_payload = {"success": True, "msg_id": msg_obj.id}
    record_widget_log(
        "/api/csr/external_message",
        "POST",
        payload,
        response_payload,
        200,
        business=business,
        chat_session=chat_session,
        visitor_id=visitor_id,
    )
    return jsonify(response_payload)


@app.route("/api/csr/transfer", methods=["POST"])
def api_csr_transfer():
    payload = request.get_json(silent=True) or {}
    visitor_id = payload.get("visitor_id")
    transcript = payload.get("transcript", [])
    summary = payload.get("summary", "")
    widget_key = payload.get("widget_key")
    csr_key = payload.get("csr_key")

    business = None
    if widget_key:
        business = Business.query.filter_by(widget_key=widget_key, is_active=True).first()
    if not business and csr_key:
        business = Business.query.filter_by(csr_key=csr_key, is_active=True).first()

    if not visitor_id:
        response_payload = {"success": False, "message": "Missing visitor_id"}
        record_widget_log(
            "/api/csr/transfer",
            "POST",
            payload,
            response_payload,
            400,
            business=business,
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 400

    if not business:
        response_payload = {"success": False, "message": "Invalid widget or CSR key"}
        record_widget_log(
            "/api/csr/transfer",
            "POST",
            payload,
            response_payload,
            401,
            visitor_id=visitor_id,
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 401

    chat_session = ChatSession.query.filter(
        ChatSession.user_identifier == visitor_id,
        ChatSession.business_id == business.id,
        ChatSession.status.in_(["pending_csr", "active_csr"]),
    ).order_by(ChatSession.updated_at.desc()).first()

    if not chat_session:
        response_payload = {"success": False, "message": "No active CSR session found"}
        record_widget_log(
            "/api/csr/transfer",
            "POST",
            payload,
            response_payload,
            404,
            business=business,
            visitor_id=visitor_id,
            error_message=response_payload["message"],
        )
        return jsonify(response_payload), 404

    for msg in transcript:
        sender = msg.get("sender", "user")
        content = msg.get("content", "")
        if sender == "csr":
            existing = ChatMessage.query.filter_by(
                session_id=chat_session.id,
                sender_type="csr",
                content=content,
            ).first()
            if not existing:
                db.session.add(ChatMessage(session_id=chat_session.id, sender_type="csr", content=content))

    chat_session.status = "active_ai"
    chat_session.csr_id = None
    chat_session.summary = summary or chat_session.summary
    chat_session.updated_at = datetime.utcnow()
    db.session.commit()

    # Avoid duplicate "connected back to AI" notices if resolve is retried.
    recent_ai = (
        ChatMessage.query.filter_by(session_id=chat_session.id, sender_type="ai")
        .order_by(ChatMessage.id.desc())
        .first()
    )
    if not recent_ai or recent_ai.content != CSR_RESOLVED_MESSAGE:
        system_msg = ChatMessage(
            session_id=chat_session.id,
            sender_type="ai",
            content=CSR_RESOLVED_MESSAGE,
        )
        db.session.add(system_msg)
        db.session.commit()
    sync_chat_session_to_csr(chat_session, business)

    response_payload = {"success": True}
    record_widget_log(
        "/api/csr/transfer",
        "POST",
        payload,
        response_payload,
        200,
        business=business,
        chat_session=chat_session,
        visitor_id=visitor_id,
    )
    return jsonify(response_payload)


@app.route("/api/v1/external/csr/chats", methods=["GET"])
def external_api_csr_chats():
    csr_business, error_response, status_code = authenticate_csr_request()
    if error_response:
        return error_response, status_code

    conversations = CsrConversation.query.filter(
        CsrConversation.status.in_(["pending_csr", "active_csr"]),
        CsrConversation.csr_business_id == csr_business.id,
    ).order_by(CsrConversation.updated_at.desc()).all()

    chats = [serialize_csr_chat_list_item(conversation) for conversation in conversations]

    response_payload = {"chats": chats}
    record_csr_widget_log(
        "/api/v1/external/csr/chats",
        "GET",
        dict(request.args),
        response_payload,
        200,
        csr_business=csr_business,
    )
    return jsonify(response_payload)


@app.route("/api/v1/external/csr/messages/<int:session_id>", methods=["GET"])
def external_api_csr_messages(session_id):
    csr_business, error_response, status_code = authenticate_csr_request()
    if error_response:
        return error_response, status_code

    conversation = CsrConversation.query.get(session_id)
    if not conversation or conversation.csr_business_id != csr_business.id:
        response_payload = {"error": "Session not found or unauthorized"}
        record_csr_widget_log(
            f"/api/v1/external/csr/messages/{session_id}",
            "GET",
            dict(request.args),
            response_payload,
            404,
            csr_business=csr_business,
            error_message=response_payload["error"],
        )
        return jsonify(response_payload), 404

    messages = CsrConversationMessage.query.filter_by(conversation_id=session_id).order_by(CsrConversationMessage.timestamp.asc()).all()
    authentication = csr_conversation_authentication_payload(conversation)
    response_payload = {
        "messages": [
            message_to_payload(msg)
            for msg in messages
        ],
        "session_status": conversation.status,
        "visitor_id": conversation.visitor_id,
        "user_type": conversation.user_type,
        "auth_mode": authentication["mode"],
        "authenticated_user_id": authentication["user_id"],
        "authenticated_user_name": authentication["user_name"],
        "authentication": authentication,
    }
    record_csr_widget_log(
        f"/api/v1/external/csr/messages/{session_id}",
        "GET",
        dict(request.args),
        response_payload,
        200,
        csr_business=csr_business,
        conversation=conversation,
        visitor_id=conversation.visitor_id,
    )
    return jsonify(response_payload)


@app.route("/api/v1/external/csr/reply", methods=["POST"])
def external_api_csr_reply():
    csr_business, error_response, status_code = authenticate_csr_request()
    if error_response:
        return error_response, status_code

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    message = payload.get("message")
    conversation = CsrConversation.query.get(session_id) if session_id else None

    if not session_id or not message:
        response_payload = {"error": "Session ID and message required"}
        record_csr_widget_log(
            "/api/v1/external/csr/reply",
            "POST",
            payload,
            response_payload,
            400,
            csr_business=csr_business,
            error_message=response_payload["error"],
        )
        return jsonify(response_payload), 400

    if not conversation or conversation.csr_business_id != csr_business.id:
        response_payload = {"error": "Session not found or unauthorized"}
        record_csr_widget_log(
            "/api/v1/external/csr/reply",
            "POST",
            payload,
            response_payload,
            404,
            csr_business=csr_business,
            error_message=response_payload["error"],
        )
        return jsonify(response_payload), 404

    msg_obj = create_csr_reply(conversation, message)

    response_payload = {"success": True, "message_id": msg_obj.id}
    record_csr_widget_log(
        "/api/v1/external/csr/reply",
        "POST",
        payload,
        response_payload,
        200,
        csr_business=csr_business,
        conversation=conversation,
        visitor_id=conversation.visitor_id,
    )
    return jsonify(response_payload)


@app.route("/api/v1/external/csr/close", methods=["POST"])
def external_api_csr_close():
    csr_business, error_response, status_code = authenticate_csr_request()
    if error_response:
        return error_response, status_code

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    conversation = CsrConversation.query.get(session_id) if session_id else None

    if not session_id:
        response_payload = {"error": "Session ID required"}
        record_csr_widget_log(
            "/api/v1/external/csr/close",
            "POST",
            payload,
            response_payload,
            400,
            csr_business=csr_business,
            error_message=response_payload["error"],
        )
        return jsonify(response_payload), 400

    if not conversation or conversation.csr_business_id != csr_business.id:
        response_payload = {"error": "Session not found or unauthorized"}
        record_csr_widget_log(
            "/api/v1/external/csr/close",
            "POST",
            payload,
            response_payload,
            404,
            csr_business=csr_business,
            error_message=response_payload["error"],
        )
        return jsonify(response_payload), 404

    resolve_csr_conversation(conversation)

    response_payload = {"success": True, "message": "Chat resolved and returned to AI"}
    record_csr_widget_log(
        "/api/v1/external/csr/close",
        "POST",
        payload,
        response_payload,
        200,
        csr_business=csr_business,
        conversation=conversation,
        visitor_id=conversation.visitor_id,
    )
    return jsonify(response_payload)


@app.route("/api/csr/chats", methods=["GET"])
@login_required
def api_csr_chats():
    user = current_user()
    conversations = (
        CsrConversation.query.join(CsrBusiness)
        .filter(
            CsrBusiness.user_id == user.id,
            CsrConversation.status.in_(["pending_csr", "active_csr"]),
        )
        .order_by(CsrConversation.updated_at.desc())
        .all()
    )
    chats = [serialize_csr_chat_list_item(conversation) for conversation in conversations]
    return jsonify({"chats": chats})


@app.route("/api/csr/messages/<int:session_id>", methods=["GET"])
@login_required
def api_csr_messages(session_id):
    user = current_user()
    conversation = CsrConversation.query.join(CsrBusiness).filter(
        CsrConversation.id == session_id,
        CsrBusiness.user_id == user.id,
    ).first()
    if not conversation:
        return jsonify({"error": "Session not found"}), 404

    messages = CsrConversationMessage.query.filter_by(conversation_id=session_id).order_by(CsrConversationMessage.timestamp.asc()).all()
    authentication = csr_conversation_authentication_payload(conversation)
    return jsonify(
        {
            "messages": [
                message_to_payload(msg, include_id=False)
                for msg in messages
            ],
            "session_status": conversation.status,
            "visitor_id": conversation.visitor_id,
            "user_type": conversation.user_type,
            "auth_mode": authentication["mode"],
            "authenticated_user_id": authentication["user_id"],
            "authenticated_user_name": authentication["user_name"],
            "authentication": authentication,
        }
    )


@app.route("/api/csr/reply", methods=["POST"])
@login_required
def api_csr_reply():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    message = payload.get("message")
    conversation = CsrConversation.query.join(CsrBusiness).filter(
        CsrConversation.id == session_id,
        CsrBusiness.user_id == user.id,
    ).first()

    if not session_id or not message:
        return jsonify({"error": "Session ID and message required"}), 400
    if not conversation:
        return jsonify({"error": "Session not found"}), 404

    msg_obj = create_csr_reply(conversation, message, acting_user=user)

    return jsonify({"success": True, "message_id": msg_obj.id})


@app.route("/api/csr/close", methods=["POST"])
@login_required
def api_csr_close():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    conversation = CsrConversation.query.join(CsrBusiness).filter(
        CsrConversation.id == session_id,
        CsrBusiness.user_id == user.id,
    ).first()

    if not session_id:
        return jsonify({"error": "Session ID required"}), 400
    if not conversation:
        return jsonify({"error": "Session not found"}), 404

    resolve_csr_conversation(conversation)
    return jsonify({"success": True, "message": "Chat resolved and returned to AI"})


def init_db():
    with app.app_context():
        db.create_all()
        ensure_column_exists("main", "business", "chatbot_verify_base_url", "VARCHAR(500)")
        ensure_column_exists("main", "business", "chatbot_service_secret", "VARCHAR(255)")
        ensure_column_exists("main", "chat_session", "auth_mode", "VARCHAR(20) NOT NULL DEFAULT 'anonymous'")
        ensure_column_exists("main", "chat_session", "authenticated_user_id", "VARCHAR(120)")
        ensure_column_exists("main", "chat_session", "authenticated_user_data", "TEXT")
        ensure_column_exists("main", "chat_session", "auth_token_fingerprint", "VARCHAR(64)")
        ensure_column_exists("main", "chat_message", "image_attachments", "TEXT")
        ensure_column_exists("csr", "csr_conversation_message", "image_attachments", "TEXT")
        for business in Business.query.all():
            business.n8n_webhook_url = DEFAULT_WEBHOOK_URL
            if not (business.chatbot_verify_base_url or "").strip():
                business.chatbot_verify_base_url = DEFAULT_CHATBOT_VERIFY_BASE_URL
            if not (business.chatbot_service_secret or "").strip():
                business.chatbot_service_secret = DEFAULT_CHATBOT_SERVICE_SECRET
            ensure_csr_business_for_business(business)
        db.session.commit()
        active_csr_sessions = ChatSession.query.filter(ChatSession.status.in_(["pending_csr", "active_csr"])).all()
        for chat_session in active_csr_sessions:
            business = Business.query.get(chat_session.business_id)
            if business:
                sync_chat_session_to_csr(chat_session, business)


if __name__ == "__main__":
    init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5004")), debug=debug_mode, use_reloader=debug_mode)
