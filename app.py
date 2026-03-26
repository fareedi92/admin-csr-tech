from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'csr-widget-app-secret-key-2024'

# SQLite Database Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

db = SQLAlchemy(app)

# Enable CORS for all routes
CORS(app, resources={
    r"/*": {
        "origins": [
            r"http://127\.0\.0\.1:\d+",
            r"http://localhost:\d+",
            r"https://.*\.vercel\.app",
            "https://flt-frontend-web-sigma.vercel.app",
            "http://52.74.227.205:5003"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})


# ─── User Model ───────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# ─── Login Required Decorator ─────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ─── Routes ───────────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    """Render the CSR Dashboard widget page (protected)"""
    user = db.session.get(User, session['user_id'])
    return render_template('csr_dashboard.html', user=user)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration page"""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        if not email or not password or not confirm_password:
            flash('All fields are required.', 'error')
            return render_template('signup.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('signup.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('signup.html')

        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'error')
            return render_template('signup.html')

        # Create user
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html')

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return render_template('login.html')

        # Set session
        session.permanent = True
        session['user_id'] = user.id
        session['user_email'] = user.email

        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Clear session and redirect to login"""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/health')
def health():
    """Health check endpoint (no auth required)"""
    return {'status': 'healthy', 'service': 'CSR Widget App'}, 200


# ─── Create tables on startup ────────────────────────────────
with app.app_context():
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
    db.create_all()


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5002,
        debug=False,
        threaded=True
    )
