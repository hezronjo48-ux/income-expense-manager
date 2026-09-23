import os
import shutil
import json
import io
import time
import threading
import urllib.request
import secrets
import hashlib
from collections import defaultdict
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, session, make_response
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

app = Flask(__name__)

# ---------------------------------------------------------------------------
# BASE DIR & SECRET KEY (must be defined before any file-based config)
# ---------------------------------------------------------------------------
_base_dir = os.path.dirname(os.path.abspath(__file__))

_secret_key_file = os.path.join(_base_dir, 'secret_key.txt')
if os.path.exists(_secret_key_file):
    with open(_secret_key_file) as f:
        app.config['SECRET_KEY'] = f.read().strip()
else:
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    with open(_secret_key_file, 'w') as f:
        f.write(app.config['SECRET_KEY'])

# ---------------------------------------------------------------------------
# DATABASE PATH: configurable via config.json for shared network use
# ---------------------------------------------------------------------------
_config_path = os.path.join(_base_dir, 'config.json')
if os.path.exists(_config_path):
    with open(_config_path, 'r') as f:
        _cfg = json.load(f)
    _db_path = _cfg.get('db_path', '')
    if _db_path:
        # Support both absolute paths and UNC network paths
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{_db_path}'
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# ---------------------------------------------------------------------------
# CSRF PROTECTION & LOGIN RATE LIMITING (no extra packages required)
# ---------------------------------------------------------------------------

_login_attempts = defaultdict(list)

@app.before_request
def session_csrf():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)

@app.before_request
def check_login_rate():
    if request.endpoint == 'login' and request.method == 'POST':
        ip = request.remote_addr or 'unknown'
        now = datetime.now()
        _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < timedelta(minutes=15)]
        if len(_login_attempts[ip]) >= 10:
            return 'Too many login attempts. Try again later.', 429
        _login_attempts[ip].append(now)

@app.before_request
def check_csrf():
    if request.method == 'POST':
        token = request.form.get('csrf_token', '')
        if not token or token != session.get('csrf_token'):
            return 'CSRF token missing or invalid.', 400


# ---------------------------------------------------------------------------
# MAINTENANCE MODE CHECK
# ---------------------------------------------------------------------------

@app.before_request
def check_maintenance():
    if request.endpoint in ('static', 'robots_txt', 'sitemap_xml', 'login', 'maintenance_page'):
        return
    try:
        if get_setting('maintenance_mode') == '1':
            # Logged-out visitors are sent to the login page so an administrator
            # can always sign in during maintenance. Only admins get past it.
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.role != 'admin':
                return render_template('maintenance.html',
                    message=get_setting('maintenance_message',
                        'System is currently under maintenance. Please check back later.')), 503
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CUSTOM JINJA2 FILTERS
# ---------------------------------------------------------------------------

@app.template_filter('currency')
def currency_filter(value):
    """Format a number with 2 decimals and comma separators."""
    try:
        return f'{float(value):,.2f}'
    except (ValueError, TypeError):
        return '0.00'


# ---------------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), default='')
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='TZS')
    usd_to_tzs_rate = db.Column(db.Float, nullable=True)
    tzs_equivalent = db.Column(db.Float, nullable=True)
    recorded_by = db.Column(db.String(100), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), default='')
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='TZS')
    usd_to_tzs_rate = db.Column(db.Float, nullable=True)
    tzs_equivalent = db.Column(db.Float, nullable=True)
    recorded_by = db.Column(db.String(100), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80))
    action = db.Column(db.String(50), nullable=False)
    table_name = db.Column(db.String(50))
    record_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, default='')
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(500), default='')


# ---------------------------------------------------------------------------
# MONITORING MODELS
# ---------------------------------------------------------------------------

class MonitoringError(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    error_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    endpoint = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80))
    severity = db.Column(db.String(20), default='medium')
    status = db.Column(db.String(20), default='unresolved')
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MonitoringPerformance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cpu_usage = db.Column(db.Float, default=0)
    ram_usage = db.Column(db.Float, default=0)
    ram_total = db.Column(db.Float, default=0)
    storage_usage = db.Column(db.Float, default=0)
    storage_total = db.Column(db.Float, default=0)
    db_response_time = db.Column(db.Float, default=0)
    api_response_time = db.Column(db.Float, default=0)
    avg_page_load_time = db.Column(db.Float, default=0)
    active_users = db.Column(db.Integer, default=0)
    total_requests = db.Column(db.Integer, default=0)
    failed_requests = db.Column(db.Integer, default=0)
    slow_requests = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MonitoringSecurity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80))
    ip_address = db.Column(db.String(50))
    browser = db.Column(db.String(100))
    device = db.Column(db.String(100))
    os = db.Column(db.String(100))
    details = db.Column(db.Text)
    status = db.Column(db.String(20), default='info')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MonitoringActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80))
    action = db.Column(db.String(50), nullable=False)
    module = db.Column(db.String(50))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MonitoringNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# TZS / USD ACCOUNT MODELS
# ---------------------------------------------------------------------------

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TzsIncome(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), default='Other Income')
    payment_method = db.Column(db.String(50), default='Cash')
    note = db.Column(db.Text, default='')
    description = db.Column(db.String(200), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    customer = db.relationship('Customer', backref=db.backref('tzs_incomes', lazy=True))


class TzsExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), default='Other')
    payment_method = db.Column(db.String(50), default='Cash')
    note = db.Column(db.Text, default='')
    description = db.Column(db.String(200), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    customer = db.relationship('Customer', backref=db.backref('tzs_expenses', lazy=True))


class UsdIncome(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), default='Other Income')
    payment_method = db.Column(db.String(50), default='Cash')
    note = db.Column(db.Text, default='')
    description = db.Column(db.String(200), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    customer = db.relationship('Customer', backref=db.backref('usd_incomes', lazy=True))


class UsdExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), default='Other')
    payment_method = db.Column(db.String(50), default='Cash')
    note = db.Column(db.Text, default='')
    description = db.Column(db.String(200), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    customer = db.relationship('Customer', backref=db.backref('usd_expenses', lazy=True))


PAYMENT_METHODS = ['Cash', 'Bank Transfer', 'Mobile Money', 'Cheque', 'Credit Card', 'Other']
INCOME_CATEGORIES = sorted(['Services', 'FLIGHT TICKET(I)', 'Director Income', 'Other Income'])
EXPENSE_CATEGORIES = sorted(['NSSF', 'Salary', 'Rent', 'Internet', 'Fuel', 'Stationary', 'FLIGHT TICKET(E)', 'Payee', 'Insurance', 'Transportation', 'VAT', 'Utilities', 'Loan', 'Apart-Hotel', 'CIP', 'Director Expenses', 'Refund'])
TZS_INCOME_CATEGORIES = INCOME_CATEGORIES
TZS_EXPENSE_CATEGORIES = EXPENSE_CATEGORIES
USD_INCOME_CATEGORIES = INCOME_CATEGORIES
USD_EXPENSE_CATEGORIES = EXPENSE_CATEGORIES


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def log_audit(action, table_name=None, record_id=None, details=''):
    try:
        log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            username=current_user.username if current_user.is_authenticated else 'system',
            action=action,
            table_name=table_name,
            record_id=record_id,
            details=str(details)[:500],
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_setting(key, default=''):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default


def get_dashboard_data():
    today = date.today()
    start_of_month = today.replace(day=1)

    today_income = db.session.query(func.coalesce(func.sum(Income.tzs_equivalent), 0))\
        .filter(Income.date == today).scalar()
    today_expense = db.session.query(func.coalesce(func.sum(Expense.tzs_equivalent), 0))\
        .filter(Expense.date == today).scalar()

    month_income = db.session.query(func.coalesce(func.sum(Income.tzs_equivalent), 0))\
        .filter(Income.date >= start_of_month, Income.date <= today).scalar()
    month_expense = db.session.query(func.coalesce(func.sum(Expense.tzs_equivalent), 0))\
        .filter(Expense.date >= start_of_month, Expense.date <= today).scalar()

    total_income = db.session.query(func.coalesce(func.sum(Income.tzs_equivalent), 0)).scalar()
    total_expense = db.session.query(func.coalesce(func.sum(Expense.tzs_equivalent), 0)).scalar()

    # Main TZS Account balance (TZS currency only)
    main_tzs_income = db.session.query(func.coalesce(func.sum(Income.tzs_equivalent), 0))\
        .filter(db.or_(Income.currency == 'TZS', Income.currency.is_(None))).scalar()
    main_tzs_expense = db.session.query(func.coalesce(func.sum(Expense.tzs_equivalent), 0))\
        .filter(db.or_(Expense.currency == 'TZS', Expense.currency.is_(None))).scalar()
    main_balance = float(main_tzs_income) - float(main_tzs_expense)

    # TZS Account balances
    tzs_income_total = db.session.query(func.coalesce(func.sum(TzsIncome.amount), 0)).scalar()
    tzs_expense_total = db.session.query(func.coalesce(func.sum(TzsExpense.amount), 0)).scalar()
    tzs_balance = float(tzs_income_total) - float(tzs_expense_total)

    # USD Account balances
    usd_income_total = db.session.query(func.coalesce(func.sum(UsdIncome.amount), 0)).scalar()
    usd_expense_total = db.session.query(func.coalesce(func.sum(UsdExpense.amount), 0)).scalar()
    usd_balance = float(usd_income_total) - float(usd_expense_total)

    # General Dollar Account balance (general ledger USD records)
    dollar_income_total = db.session.query(func.coalesce(func.sum(Income.amount), 0))\
        .filter(Income.currency == '$').scalar()
    dollar_expense_total = db.session.query(func.coalesce(func.sum(Expense.amount), 0))\
        .filter(Expense.currency == '$').scalar()
    dollar_balance = float(dollar_income_total) - float(dollar_expense_total)

    # Chart data: last 12 months
    chart_labels = []
    chart_income = []
    chart_expense = []
    for i in range(11, -1, -1):
        m = today.month - i
        y = today.year
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        start = date(y, m, 1)
        if m == 12:
            end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(y, m + 1, 1) - timedelta(days=1)
        inc = db.session.query(func.coalesce(func.sum(Income.tzs_equivalent), 0))\
            .filter(Income.date >= start, Income.date <= end).scalar()
        exp = db.session.query(func.coalesce(func.sum(Expense.tzs_equivalent), 0))\
            .filter(Expense.date >= start, Expense.date <= end).scalar()
        chart_labels.append(f'{start.strftime("%b")}')
        chart_income.append(float(inc))
        chart_expense.append(float(exp))

    return {
        'today_income': float(today_income),
        'today_expense': float(today_expense),
        'month_income': float(month_income),
        'month_expense': float(month_expense),
        'total_income': float(total_income),
        'total_expense': float(total_expense),
        'balance': main_balance,
        'main_tzs_income': float(main_tzs_income),
        'dollar_income_total': float(dollar_income_total),
        'tzs_balance': tzs_balance,
        'usd_balance': usd_balance,
        'dollar_balance': dollar_balance,
        'chart_labels': json.dumps(chart_labels),
        'chart_income': json.dumps(chart_income),
        'chart_expense': json.dumps(chart_expense),
    }


# ---------------------------------------------------------------------------
# MONITORING HELPERS
# ---------------------------------------------------------------------------

def log_monitoring_error(error_type, description, endpoint=None, severity='medium'):
    try:
        err = MonitoringError(
            error_type=error_type, description=str(description)[:1000],
            endpoint=endpoint or request.path,
            user_id=current_user.id if current_user.is_authenticated else None,
            username=current_user.username if current_user.is_authenticated else 'system',
            severity=severity, ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:300]
        )
        db.session.add(err)
        db.session.commit()
        # Auto-create notification for critical errors
        if severity in ('critical', 'high'):
            create_notification(
                f'{error_type.replace("_", " ").title()} Error',
                str(description)[:200],
                'SERVER_ERROR', severity
            )
    except Exception:
        db.session.rollback()


def log_monitoring_security(event_type, username=None, details=None, status='info'):
    try:
        ua = request.headers.get('User-Agent', '')
        browser = 'Unknown'
        device = 'Desktop'
        os_ = 'Unknown'
        if 'Chrome' in ua: browser = 'Chrome'
        elif 'Firefox' in ua: browser = 'Firefox'
        elif 'Safari' in ua: browser = 'Safari'
        elif 'Edge' in ua: browser = 'Edge'
        if 'Mobile' in ua: device = 'Mobile'
        elif 'Tablet' in ua: device = 'Tablet'
        if 'Windows' in ua: os_ = 'Windows'
        elif 'Linux' in ua: os_ = 'Linux'
        elif 'Mac' in ua: os_ = 'macOS'
        elif 'Android' in ua: os_ = 'Android'
        elif 'iOS' in ua or 'iPhone' in ua: os_ = 'iOS'

        event = MonitoringSecurity(
            event_type=event_type,
            user_id=current_user.id if current_user.is_authenticated else None,
            username=username or (current_user.username if current_user.is_authenticated else 'system'),
            ip_address=request.remote_addr, browser=browser, device=device, os=os_,
            details=str(details)[:500] if details else '', status=status
        )
        db.session.add(event)
        db.session.commit()
    except Exception:
        db.session.rollback()


def log_monitoring_activity(username, action, module=None, old_value=None, new_value=None):
    try:
        act = MonitoringActivity(
            username=username or 'system', action=action, module=module,
            old_value=str(old_value)[:500] if old_value else None,
            new_value=str(new_value)[:500] if new_value else None,
            ip_address=request.remote_addr
        )
        db.session.add(act)
        db.session.commit()
    except Exception:
        db.session.rollback()


def create_notification(title, message, notification_type, severity='info'):
    try:
        notif = MonitoringNotification(
            title=str(title)[:200], message=str(message)[:500],
            notification_type=notification_type, severity=severity
        )
        db.session.add(notif)
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_system_stats():
    stats = {'cpu_percent': 0, 'ram_percent': 0, 'ram_used': 0, 'ram_total': 0,
             'storage_percent': 0, 'storage_used': 0, 'storage_total': 0}
    # CPU: approximate using os.cpu_count and a simple heuristic
    try:
        import psutil
        stats['cpu_percent'] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        stats['ram_total'] = round(mem.total / (1024**3), 1)
        stats['ram_used'] = round(mem.used / (1024**3), 1)
        stats['ram_percent'] = round(mem.percent, 1)
    except ImportError:
        stats['cpu_percent'] = 0
        stats['ram_total'] = 0
        stats['ram_used'] = 0
        stats['ram_percent'] = 0
    # Storage
    try:
        du = shutil.disk_usage(_base_dir)
        stats['storage_total'] = round(du.total / (1024**3), 1)
        stats['storage_used'] = round(du.used / (1024**3), 1)
        stats['storage_percent'] = round(du.used / du.total * 100, 1)
    except Exception:
        pass
    return stats


def record_performance_snapshot():
    try:
        stats = get_system_stats()
        # Get latest performance record to derive trends
        last = MonitoringPerformance.query.order_by(MonitoringPerformance.id.desc()).first()
        total_reqs = (last.total_requests if last else 0) + 1
        failed_reqs = last.failed_requests if last else 0
        slow_reqs = last.slow_requests if last else 0

        perf = MonitoringPerformance(
            cpu_usage=stats['cpu_percent'], ram_usage=stats['ram_percent'],
            ram_total=stats['ram_total'], storage_usage=stats['storage_percent'],
            storage_total=stats['storage_total'],
            db_response_time=0, api_response_time=0, avg_page_load_time=0,
            active_users=User.query.filter_by(active=True).count(),
            total_requests=total_reqs, failed_requests=failed_reqs,
            slow_requests=slow_reqs
        )
        db.session.add(perf)
        db.session.commit()

        # Auto-notify on high usage
        if stats['ram_percent'] > 90:
            create_notification('High RAM Usage', f'RAM at {stats["ram_percent"]}%', 'RAM_HIGH', 'warning')
        if stats['storage_percent'] > 90:
            create_notification('High Storage Usage', f'Storage at {stats["storage_percent"]}%', 'STORAGE_HIGH', 'warning')
    except Exception:
        db.session.rollback()


# ---------------------------------------------------------------------------
# REQUEST TRACKING (performance monitoring)
# ---------------------------------------------------------------------------

_request_start_times = {}
_request_count = 0
_request_failed = 0
_request_slow = 0

@app.before_request
def track_request_start():
    _request_start_times[threading.get_ident()] = time.time()


@app.after_request
def track_request_end(response):
    global _request_count, _request_failed, _request_slow
    ident = threading.get_ident()
    start = _request_start_times.pop(ident, None)
    if start:
        elapsed = (time.time() - start) * 1000
        _request_count += 1
        if response.status_code >= 500:
            _request_failed += 1
        if elapsed > 2000:
            _request_slow += 1
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
    elif response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# SEO - robots.txt & sitemap.xml
# ---------------------------------------------------------------------------

@app.route('/robots.txt')
def robots_txt():
    resp = make_response(
        'User-agent: *\n'
        'Allow: /\n'
        'Sitemap: https://www.myledger.co.tz/sitemap.xml\n'
    )
    resp.mimetype = 'text/plain'
    return resp


@app.route('/sitemap.xml')
def sitemap_xml():
    pages = [
        {'loc': 'https://www.myledger.co.tz/', 'priority': '1.0'},
        {'loc': 'https://www.myledger.co.tz/login', 'priority': '0.9'},
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for p in pages:
        xml += f'  <url>\n    <loc>{p["loc"]}</loc>\n    <priority>{p["priority"]}</priority>\n  </url>\n'
    xml += '</urlset>'
    resp = make_response(xml)
    resp.mimetype = 'application/xml'
    return resp


# ---------------------------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.active and user.check_password(password):
            if get_setting('maintenance_mode') == '1' and user.role != 'admin':
                log_monitoring_security('FAILED_LOGIN', username, f'Login blocked during maintenance for {username}', 'warning')
                flash('Maintenance is in progress. Only the system administrator can log in.', 'danger')
                return redirect(url_for('login'))
            login_user(user)
            log_audit('login', 'user', user.id, f'User {user.username} logged in')
            log_monitoring_security('SUCCESSFUL_LOGIN', user.username, f'User {user.username} logged in', 'success')
            log_monitoring_activity(user.username, 'LOGIN', 'auth')
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(url_for('dashboard'))
        log_monitoring_security('FAILED_LOGIN', username, f'Failed login attempt for {username}', 'danger')
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    log_audit('logout', 'user', current_user.id, f'User {current_user.username} logged out')
    log_monitoring_activity(current_user.username, 'LOGOUT', 'auth')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    data = get_dashboard_data()
    return render_template('dashboard.html', **data)


# ---------------------------------------------------------------------------
# MAIN TZS ACCOUNT (Income + Expenses combined, no customers)
# ---------------------------------------------------------------------------

@app.route('/main')
@login_required
def main_account():
    cat = request.args.get('category', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()
    kind = request.args.get('type', '')

    inc_q = Income.query.filter(
        db.or_(Income.currency == 'TZS', Income.currency.is_(None))
    )
    exp_q = Expense.query.filter(
        db.or_(Expense.currency == 'TZS', Expense.currency.is_(None))
    )
    if cat:
        inc_q = inc_q.filter(Income.category == cat)
        exp_q = exp_q.filter(Expense.category == cat)
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date >= sdt)
            exp_q = exp_q.filter(Expense.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date <= edt)
            exp_q = exp_q.filter(Expense.date <= edt)
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        inc_q = inc_q.filter(db.or_(
            Income.description.ilike(like), Income.recorded_by.ilike(like)))
        exp_q = exp_q.filter(db.or_(
            Expense.description.ilike(like), Expense.recorded_by.ilike(like)))
    if kind == 'income':
        exp_q = exp_q.filter(db.text('1 = 0'))
    elif kind == 'expense':
        inc_q = inc_q.filter(db.text('1 = 0'))

    incomes = inc_q.order_by(Income.date.desc(), Income.created_at.desc()).all()
    expenses = exp_q.order_by(Expense.date.desc(), Expense.created_at.desc()).all()

    total_income = sum(float(i.tzs_equivalent or i.amount) for i in incomes)
    total_expense = sum(float(e.tzs_equivalent or e.amount) for e in expenses)
    balance = total_income - total_expense

    return render_template('main_account.html',
        incomes=incomes, expenses=expenses, total_income=total_income,
        total_expense=total_expense, balance=balance,
        categories=INCOME_CATEGORIES, expense_categories=EXPENSE_CATEGORIES,
        filter_category=cat, filter_from=sdate, filter_to=edate, filter_q=search,
        filter_type=kind)


@app.route('/dollar')
@login_required
def dollar_account():
    cat = request.args.get('category', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()
    kind = request.args.get('type', '')

    inc_q = Income.query.filter(Income.currency == '$')
    exp_q = Expense.query.filter(Expense.currency == '$')
    if cat:
        inc_q = inc_q.filter(Income.category == cat)
        exp_q = exp_q.filter(Expense.category == cat)
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date >= sdt)
            exp_q = exp_q.filter(Expense.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date <= edt)
            exp_q = exp_q.filter(Expense.date <= edt)
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        inc_q = inc_q.filter(db.or_(
            Income.description.ilike(like), Income.recorded_by.ilike(like)))
        exp_q = exp_q.filter(db.or_(
            Expense.description.ilike(like), Expense.recorded_by.ilike(like)))
    if kind == 'income':
        exp_q = exp_q.filter(db.text('1 = 0'))
    elif kind == 'expense':
        inc_q = inc_q.filter(db.text('1 = 0'))

    incomes = inc_q.order_by(Income.date.desc(), Income.created_at.desc()).all()
    expenses = exp_q.order_by(Expense.date.desc(), Expense.created_at.desc()).all()

    total_income = sum(float(i.amount) for i in incomes)
    total_expense = sum(float(e.amount) for e in expenses)
    balance = total_income - total_expense

    return render_template('dollar_account.html',
        incomes=incomes, expenses=expenses, total_income=total_income,
        total_expense=total_expense, balance=balance,
        categories=INCOME_CATEGORIES, expense_categories=EXPENSE_CATEGORIES,
        filter_category=cat, filter_from=sdate, filter_to=edate, filter_q=search,
        filter_type=kind)


# ---------------------------------------------------------------------------
# MAIN TZS ACCOUNT - Separate Income & Expenses Pages
# ---------------------------------------------------------------------------

@app.route('/main/income')
@login_required
def main_account_income():
    cat = request.args.get('category', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()

    inc_q = Income.query.filter(
        db.or_(Income.currency == 'TZS', Income.currency.is_(None))
    )
    if cat:
        inc_q = inc_q.filter(Income.category == cat)
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date <= edt)
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        inc_q = inc_q.filter(db.or_(
            Income.description.ilike(like), Income.recorded_by.ilike(like)))

    incomes = inc_q.order_by(Income.date.desc(), Income.created_at.desc()).all()
    total_income = sum(float(i.tzs_equivalent or i.amount) for i in incomes)

    # For balance calculation, get expenses too
    exp_q = Expense.query.filter(
        db.or_(Expense.currency == 'TZS', Expense.currency.is_(None))
    )
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date <= edt)
        except ValueError:
            pass
    expenses = exp_q.order_by(Expense.date.desc(), Expense.created_at.desc()).all()
    total_expense = sum(float(e.tzs_equivalent or e.amount) for e in expenses)
    balance = total_income - total_expense

    return render_template('main_account_income.html',
        incomes=incomes, total_income=total_income,
        total_expense=total_expense, balance=balance,
        categories=INCOME_CATEGORIES, expense_categories=EXPENSE_CATEGORIES,
        filter_category=cat, filter_from=sdate, filter_to=edate, filter_q=search)


@app.route('/main/expenses')
@login_required
def main_account_expenses():
    cat = request.args.get('category', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()

    exp_q = Expense.query.filter(
        db.or_(Expense.currency == 'TZS', Expense.currency.is_(None))
    )
    if cat:
        exp_q = exp_q.filter(Expense.category == cat)
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date <= edt)
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        exp_q = exp_q.filter(db.or_(
            Expense.description.ilike(like), Expense.recorded_by.ilike(like)))

    expenses = exp_q.order_by(Expense.date.desc(), Expense.created_at.desc()).all()
    total_expense = sum(float(e.tzs_equivalent or e.amount) for e in expenses)

    # For balance calculation, get income too
    inc_q = Income.query.filter(
        db.or_(Income.currency == 'TZS', Income.currency.is_(None))
    )
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date <= edt)
        except ValueError:
            pass
    incomes = inc_q.order_by(Income.date.desc(), Income.created_at.desc()).all()
    total_income = sum(float(i.tzs_equivalent or i.amount) for i in incomes)
    balance = total_income - total_expense

    return render_template('main_account_expenses.html',
        expenses=expenses, total_income=total_income,
        total_expense=total_expense, balance=balance,
        categories=INCOME_CATEGORIES, expense_categories=EXPENSE_CATEGORIES,
        filter_category=cat, filter_from=sdate, filter_to=edate, filter_q=search)


# ---------------------------------------------------------------------------
# DOLLAR ACCOUNT - Separate Income & Expenses Pages
# ---------------------------------------------------------------------------

@app.route('/dollar/income')
@login_required
def dollar_account_income():
    cat = request.args.get('category', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()

    inc_q = Income.query.filter(Income.currency == '$')
    if cat:
        inc_q = inc_q.filter(Income.category == cat)
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date <= edt)
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        inc_q = inc_q.filter(db.or_(
            Income.description.ilike(like), Income.recorded_by.ilike(like)))

    incomes = inc_q.order_by(Income.date.desc(), Income.created_at.desc()).all()
    total_income = sum(float(i.amount) for i in incomes)

    # For balance calculation, get expenses too
    exp_q = Expense.query.filter(Expense.currency == '$')
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date <= edt)
        except ValueError:
            pass
    expenses = exp_q.order_by(Expense.date.desc(), Expense.created_at.desc()).all()
    total_expense = sum(float(e.amount) for e in expenses)
    balance = total_income - total_expense

    return render_template('dollar_account_income.html',
        incomes=incomes, total_income=total_income,
        total_expense=total_expense, balance=balance,
        categories=INCOME_CATEGORIES, expense_categories=EXPENSE_CATEGORIES,
        filter_category=cat, filter_from=sdate, filter_to=edate, filter_q=search)


@app.route('/dollar/expenses')
@login_required
def dollar_account_expenses():
    cat = request.args.get('category', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()

    exp_q = Expense.query.filter(Expense.currency == '$')
    if cat:
        exp_q = exp_q.filter(Expense.category == cat)
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            exp_q = exp_q.filter(Expense.date <= edt)
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        exp_q = exp_q.filter(db.or_(
            Expense.description.ilike(like), Expense.recorded_by.ilike(like)))

    expenses = exp_q.order_by(Expense.date.desc(), Expense.created_at.desc()).all()
    total_expense = sum(float(e.amount) for e in expenses)

    # For balance calculation, get income too
    inc_q = Income.query.filter(Income.currency == '$')
    if sdate:
        try:
            sdt = datetime.strptime(sdate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date >= sdt)
        except ValueError:
            pass
    if edate:
        try:
            edt = datetime.strptime(edate, '%Y-%m-%d').date()
            inc_q = inc_q.filter(Income.date <= edt)
        except ValueError:
            pass
    incomes = inc_q.order_by(Income.date.desc(), Income.created_at.desc()).all()
    total_income = sum(float(i.amount) for i in incomes)
    balance = total_income - total_expense

    return render_template('dollar_account_expenses.html',
        expenses=expenses, total_income=total_income,
        total_expense=total_expense, balance=balance,
        categories=INCOME_CATEGORIES, expense_categories=EXPENSE_CATEGORIES,
        filter_category=cat, filter_from=sdate, filter_to=edate, filter_q=search)


# ---------------------------------------------------------------------------
# INCOME
# ---------------------------------------------------------------------------

@app.route('/income')
@login_required
def income_list():
    page = request.args.get('page', 1, type=int)
    query = Income.query
    cat = request.args.get('category', '')
    currency = request.args.get('currency', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()

    if cat:
        query = query.filter(Income.category == cat)
    if currency:
        query = query.filter(Income.currency == currency)
    if sdate:
        try:
            query = query.filter(Income.date >= datetime.strptime(sdate, '%Y-%m-%d').date())
        except ValueError:
            pass
    if edate:
        try:
            query = query.filter(Income.date <= datetime.strptime(edate, '%Y-%m-%d').date())
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(
            Income.description.ilike(like),
            Income.recorded_by.ilike(like),
            Income.category.ilike(like)
        ))

    income_totals = db.session.query(
        func.coalesce(func.sum(Income.amount), 0),
        func.count(Income.id)
    ).select_from(Income)
    use_filter = cat or currency or sdate or edate or search
    if use_filter:
        if cat:
            income_totals = income_totals.filter(Income.category == cat)
        if currency:
            income_totals = income_totals.filter(Income.currency == currency)
        if sdate:
            try:
                income_totals = income_totals.filter(Income.date >= datetime.strptime(sdate, '%Y-%m-%d').date())
            except ValueError:
                pass
        if edate:
            try:
                income_totals = income_totals.filter(Income.date <= datetime.strptime(edate, '%Y-%m-%d').date())
            except ValueError:
                pass
        if search:
            income_totals = income_totals.filter(db.or_(
                Income.description.ilike(f'%{search}%'),
                Income.recorded_by.ilike(f'%{search}%'),
                Income.category.ilike(f'%{search}%')
            ))
    else:
        income_totals = income_totals.filter(db.or_(
            Income.currency == 'TZS', Income.currency.is_(None)))
    filt_total_sum, filt_total_count = income_totals.one()

    incomes = query.order_by(Income.date.desc(), Income.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('income.html', incomes=incomes, categories=INCOME_CATEGORIES,
                           filter_category=cat, filter_currency=currency,
                           filter_from=sdate, filter_to=edate, filter_q=search,
                           filtered_total=float(filt_total_sum), filtered_count=filt_total_count)


@app.route('/income/add', methods=['POST'])
@login_required
def income_add():
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = date.today()
    category = request.form.get('category', 'Other Income')
    description = request.form.get('description', '')
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0

    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('income_list'))

    recorded_by = request.form.get('recorded_by', '').strip() or current_user.full_name
    currency = request.form.get('currency', 'TZS')
    if currency not in ('TZS', '$'):
        currency = currency or 'TZS'

    income = Income(
        date=dt, category=category, description=description,
        amount=amount, currency=currency,
        tzs_equivalent=amount, recorded_by=recorded_by, created_by=current_user.id
    )
    db.session.add(income)
    db.session.commit()
    log_audit('create', 'income', income.id, f'Income: {category} {amount} {currency}')
    log_monitoring_activity(current_user.username, 'CREATE', 'income', None, f'{category} {amount} {currency}')
    flash('Income saved successfully.', 'success')
    return redirect(url_for('income_list'))


@app.route('/income/edit/<int:id>', methods=['POST'])
@login_required
def income_edit(id):
    income = Income.query.get_or_404(id)
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = income.date
    category = request.form.get('category', income.category)
    description = request.form.get('description', income.description)
    try:
        amount = float(request.form.get('amount', income.amount))
    except ValueError:
        amount = income.amount

    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('income_list'))

    old = f'{income.date} {income.category} {income.amount} {income.currency}'
    income.date = dt
    income.category = category
    income.description = description
    income.amount = amount
    income.currency = request.form.get('currency', income.currency)
    if income.currency not in ('TZS', '$'):
        income.currency = income.currency or 'TZS'
    income.recorded_by = request.form.get('recorded_by', '').strip() or income.recorded_by
    income.usd_to_tzs_rate = None
    income.tzs_equivalent = amount
    db.session.commit()
    log_audit('update', 'income', id, f'Changed from: {old}')
    log_monitoring_activity(current_user.username, 'UPDATE', 'income', old, f'{income.date} {income.category} {income.amount}')
    flash('Income updated successfully.', 'success')
    return redirect(url_for('income_list'))


@app.route('/income/delete/<int:id>', methods=['POST'])
@login_required
def income_delete(id):
    income = Income.query.get_or_404(id)
    log_audit('delete', 'income', id, f'Deleted: {income.date} {income.category} {income.amount}')
    log_monitoring_activity(current_user.username, 'DELETE', 'income', f'{income.date} {income.category} {income.amount}')
    db.session.delete(income)
    db.session.commit()
    flash('Income deleted.', 'info')
    return redirect(url_for('income_list'))


# ---------------------------------------------------------------------------
# EXPENSES
# ---------------------------------------------------------------------------

@app.route('/expenses')
@login_required
def expense_list():
    page = request.args.get('page', 1, type=int)
    query = Expense.query
    cat = request.args.get('category', '')
    currency = request.args.get('currency', '')
    sdate = request.args.get('from_date', '')
    edate = request.args.get('to_date', '')
    search = request.args.get('q', '').strip()

    if cat:
        query = query.filter(Expense.category == cat)
    if currency:
        query = query.filter(Expense.currency == currency)
    if sdate:
        try:
            query = query.filter(Expense.date >= datetime.strptime(sdate, '%Y-%m-%d').date())
        except ValueError:
            pass
    if edate:
        try:
            query = query.filter(Expense.date <= datetime.strptime(edate, '%Y-%m-%d').date())
        except ValueError:
            pass
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(
            Expense.description.ilike(like),
            Expense.recorded_by.ilike(like),
            Expense.category.ilike(like)
        ))

    expense_totals = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0),
        func.count(Expense.id)
    ).select_from(Expense)
    use_filter = cat or currency or sdate or edate or search
    if use_filter:
        if cat:
            expense_totals = expense_totals.filter(Expense.category == cat)
        if currency:
            expense_totals = expense_totals.filter(Expense.currency == currency)
        if sdate:
            try:
                expense_totals = expense_totals.filter(Expense.date >= datetime.strptime(sdate, '%Y-%m-%d').date())
            except ValueError:
                pass
        if edate:
            try:
                expense_totals = expense_totals.filter(Expense.date <= datetime.strptime(edate, '%Y-%m-%d').date())
            except ValueError:
                pass
        if search:
            expense_totals = expense_totals.filter(db.or_(
                Expense.description.ilike(f'%{search}%'),
                Expense.recorded_by.ilike(f'%{search}%'),
                Expense.category.ilike(f'%{search}%')
            ))
    else:
        expense_totals = expense_totals.filter(db.or_(
            Expense.currency == 'TZS', Expense.currency.is_(None)))
    filt_total_sum, filt_total_count = expense_totals.one()

    expenses = query.order_by(Expense.date.desc(), Expense.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('expenses.html', expenses=expenses, categories=EXPENSE_CATEGORIES,
                           filter_category=cat, filter_currency=currency,
                           filter_from=sdate, filter_to=edate, filter_q=search,
                           filtered_total=float(filt_total_sum), filtered_count=filt_total_count)


@app.route('/expenses/add', methods=['POST'])
@login_required
def expense_add():
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = date.today()
    category = request.form.get('category', 'Other')
    description = request.form.get('description', '')
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0

    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('expense_list'))

    recorded_by = request.form.get('recorded_by', '').strip() or current_user.full_name
    currency = request.form.get('currency', 'TZS')
    if currency not in ('TZS', '$'):
        currency = currency or 'TZS'

    expense = Expense(
        date=dt, category=category, description=description,
        amount=amount, currency=currency,
        tzs_equivalent=amount, recorded_by=recorded_by, created_by=current_user.id
    )
    db.session.add(expense)
    db.session.commit()
    log_audit('create', 'expense', expense.id, f'Expense: {category} {amount} {currency}')
    log_monitoring_activity(current_user.username, 'CREATE', 'expense', None, f'{category} {amount} {currency}')
    flash('Expense saved successfully.', 'success')
    return redirect(url_for('expense_list'))


@app.route('/expenses/edit/<int:id>', methods=['POST'])
@login_required
def expense_edit(id):
    expense = Expense.query.get_or_404(id)
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = expense.date
    category = request.form.get('category', expense.category)
    description = request.form.get('description', expense.description)
    try:
        amount = float(request.form.get('amount', expense.amount))
    except ValueError:
        amount = expense.amount

    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('expense_list'))

    old = f'{expense.date} {expense.category} {expense.amount} {expense.currency}'
    expense.date = dt
    expense.category = category
    expense.description = description
    expense.amount = amount
    expense.currency = request.form.get('currency', expense.currency)
    if expense.currency not in ('TZS', '$'):
        expense.currency = expense.currency or 'TZS'
    expense.recorded_by = request.form.get('recorded_by', '').strip() or expense.recorded_by
    expense.usd_to_tzs_rate = None
    expense.tzs_equivalent = amount
    db.session.commit()
    log_audit('update', 'expense', id, f'Changed from: {old}')
    log_monitoring_activity(current_user.username, 'UPDATE', 'expense', old, f'{expense.date} {expense.category} {expense.amount}')
    flash('Expense updated successfully.', 'success')
    return redirect(url_for('expense_list'))


@app.route('/expenses/delete/<int:id>', methods=['POST'])
@login_required
def expense_delete(id):
    expense = Expense.query.get_or_404(id)
    log_audit('delete', 'expense', id, f'Deleted: {expense.date} {expense.category} {expense.amount}')
    log_monitoring_activity(current_user.username, 'DELETE', 'expense', f'{expense.date} {expense.category} {expense.amount}')
    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted.', 'info')
    return redirect(url_for('expense_list'))


# ---------------------------------------------------------------------------
# TZS ACCOUNT
# ---------------------------------------------------------------------------

@app.route('/tzs')
@login_required
def tzs_account():
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('tzs_account.html',
        customers=customers,
        income_categories=TZS_INCOME_CATEGORIES,
        expense_categories=TZS_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


@app.route('/tzs/customer/<int:id>')
@login_required
def tzs_customer(id):
    customer = Customer.query.get_or_404(id)
    incomes = TzsIncome.query.filter_by(customer_id=id).order_by(TzsIncome.date.desc(), TzsIncome.created_at.desc()).all()
    expenses = TzsExpense.query.filter_by(customer_id=id).order_by(TzsExpense.date.desc(), TzsExpense.created_at.desc()).all()
    total_income = sum(i.amount for i in incomes)
    total_expense = sum(e.amount for e in expenses)
    balance = total_income - total_expense
    return render_template('tzs_customer.html',
        customer=customer, incomes=incomes, expenses=expenses,
        total_income=total_income, total_expense=total_expense, balance=balance,
        income_categories=TZS_INCOME_CATEGORIES,
        expense_categories=TZS_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


@app.route('/tzs/customer/add', methods=['POST'])
@login_required
def tzs_customer_add():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Customer name is required.', 'danger')
        return redirect(url_for('tzs_account'))
    customer = Customer(name=name, created_by=current_user.id)
    db.session.add(customer)
    db.session.commit()
    flash('Customer added.', 'success')
    return redirect(url_for('tzs_account'))


@app.route('/tzs/customer/edit/<int:id>', methods=['POST'])
@login_required
def tzs_customer_edit(id):
    customer = Customer.query.get_or_404(id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Customer name is required.', 'danger')
        return redirect(url_for('tzs_account'))
    customer.name = name
    db.session.commit()
    flash('Customer updated.', 'success')
    return redirect(url_for('tzs_account'))


@app.route('/tzs/customer/delete/<int:id>', methods=['POST'])
@login_required
def tzs_customer_delete(id):
    customer = Customer.query.get_or_404(id)
    if customer.tzs_incomes or customer.tzs_expenses or customer.usd_incomes or customer.usd_expenses:
        flash('Cannot delete customer with transactions.', 'danger')
        return redirect(url_for('tzs_account'))
    db.session.delete(customer)
    db.session.commit()
    flash('Customer deleted.', 'info')
    return redirect(url_for('tzs_account'))


@app.route('/tzs/income/add', methods=['POST'])
@login_required
def tzs_income_add():
    customer_id = request.form.get('customer_id', type=int)
    if not customer_id:
        flash('Customer is required.', 'danger')
        return redirect(url_for('tzs_account'))
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = date.today()
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0
    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('tzs_customer', id=customer_id))
    income = TzsIncome(
        customer_id=customer_id, date=dt, amount=amount,
        category=request.form.get('category', 'Other Income'),
        payment_method=request.form.get('payment_method', 'Cash'),
        note=request.form.get('note', ''),
        description=request.form.get('description', ''),
        created_by=current_user.id)
    db.session.add(income)
    db.session.commit()
    flash('TZS Income saved.', 'success')
    return redirect(url_for('tzs_customer', id=customer_id))


@app.route('/tzs/income/edit/<int:id>', methods=['POST'])
@login_required
def tzs_income_edit(id):
    income = TzsIncome.query.get_or_404(id)
    try:
        income.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        pass
    try:
        income.amount = float(request.form.get('amount', income.amount))
    except ValueError:
        pass
    if income.amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('tzs_customer', id=income.customer_id))
    income.category = request.form.get('category', income.category)
    income.payment_method = request.form.get('payment_method', income.payment_method)
    income.note = request.form.get('note', '')
    income.description = request.form.get('description', '')
    db.session.commit()
    flash('TZS Income updated.', 'success')
    return redirect(url_for('tzs_customer', id=income.customer_id))


@app.route('/tzs/income/delete/<int:id>', methods=['POST'])
@login_required
def tzs_income_delete(id):
    income = TzsIncome.query.get_or_404(id)
    cid = income.customer_id
    db.session.delete(income)
    db.session.commit()
    flash('TZS Income deleted.', 'info')
    return redirect(url_for('tzs_customer', id=cid))


@app.route('/tzs/expense/add', methods=['POST'])
@login_required
def tzs_expense_add():
    customer_id = request.form.get('customer_id', type=int)
    if not customer_id:
        flash('Customer is required.', 'danger')
        return redirect(url_for('tzs_account'))
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = date.today()
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0
    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('tzs_customer', id=customer_id))
    expense = TzsExpense(
        customer_id=customer_id, date=dt, amount=amount,
        category=request.form.get('category', 'Other'),
        payment_method=request.form.get('payment_method', 'Cash'),
        note=request.form.get('note', ''),
        description=request.form.get('description', ''),
        created_by=current_user.id)
    db.session.add(expense)
    db.session.commit()
    flash('TZS Expense saved.', 'success')
    return redirect(url_for('tzs_customer', id=customer_id))


@app.route('/tzs/expense/edit/<int:id>', methods=['POST'])
@login_required
def tzs_expense_edit(id):
    expense = TzsExpense.query.get_or_404(id)
    try:
        expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        pass
    try:
        expense.amount = float(request.form.get('amount', expense.amount))
    except ValueError:
        pass
    if expense.amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('tzs_customer', id=expense.customer_id))
    expense.category = request.form.get('category', expense.category)
    expense.payment_method = request.form.get('payment_method', expense.payment_method)
    expense.note = request.form.get('note', '')
    expense.description = request.form.get('description', '')
    db.session.commit()
    flash('TZS Expense updated.', 'success')
    return redirect(url_for('tzs_customer', id=expense.customer_id))


@app.route('/tzs/expense/delete/<int:id>', methods=['POST'])
@login_required
def tzs_expense_delete(id):
    expense = TzsExpense.query.get_or_404(id)
    cid = expense.customer_id
    db.session.delete(expense)
    db.session.commit()
    flash('TZS Expense deleted.', 'info')
    return redirect(url_for('tzs_customer', id=cid))


# ---------------------------------------------------------------------------
# DOLLAR ACCOUNT
# ---------------------------------------------------------------------------

@app.route('/usd')
@login_required
def usd_account():
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('usd_account.html',
        customers=customers,
        income_categories=USD_INCOME_CATEGORIES,
        expense_categories=USD_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


@app.route('/usd/customer/<int:id>')
@login_required
def usd_customer(id):
    customer = Customer.query.get_or_404(id)
    incomes = UsdIncome.query.filter_by(customer_id=id).order_by(UsdIncome.date.desc(), UsdIncome.created_at.desc()).all()
    expenses = UsdExpense.query.filter_by(customer_id=id).order_by(UsdExpense.date.desc(), UsdExpense.created_at.desc()).all()
    total_income = sum(i.amount for i in incomes)
    total_expense = sum(e.amount for e in expenses)
    balance = total_income - total_expense
    return render_template('usd_customer.html',
        customer=customer, incomes=incomes, expenses=expenses,
        total_income=total_income, total_expense=total_expense, balance=balance,
        income_categories=USD_INCOME_CATEGORIES,
        expense_categories=USD_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


# ---------------------------------------------------------------------------
# TZS CUSTOMER ACCOUNT - Separate Income & Expenses Pages
# ---------------------------------------------------------------------------

@app.route('/tzs/customer/<int:id>/income')
@login_required
def tzs_customer_income(id):
    customer = Customer.query.get_or_404(id)
    incomes = TzsIncome.query.filter_by(customer_id=id).order_by(TzsIncome.date.desc(), TzsIncome.created_at.desc()).all()
    total_income = sum(i.amount for i in incomes)

    expenses = TzsExpense.query.filter_by(customer_id=id).order_by(TzsExpense.date.desc(), TzsExpense.created_at.desc()).all()
    total_expense = sum(e.amount for e in expenses)
    balance = total_income - total_expense

    return render_template('tzs_customer_income.html',
        customer=customer, incomes=incomes,
        total_income=total_income, total_expense=total_expense, balance=balance,
        income_categories=TZS_INCOME_CATEGORIES,
        expense_categories=TZS_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


@app.route('/tzs/customer/<int:id>/expenses')
@login_required
def tzs_customer_expenses(id):
    customer = Customer.query.get_or_404(id)
    expenses = TzsExpense.query.filter_by(customer_id=id).order_by(TzsExpense.date.desc(), TzsExpense.created_at.desc()).all()
    total_expense = sum(e.amount for e in expenses)

    incomes = TzsIncome.query.filter_by(customer_id=id).order_by(TzsIncome.date.desc(), TzsIncome.created_at.desc()).all()
    total_income = sum(i.amount for i in incomes)
    balance = total_income - total_expense

    return render_template('tzs_customer_expenses.html',
        customer=customer, expenses=expenses,
        total_income=total_income, total_expense=total_expense, balance=balance,
        income_categories=TZS_INCOME_CATEGORIES,
        expense_categories=TZS_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


# ---------------------------------------------------------------------------
# USD CUSTOMER ACCOUNT - Separate Income & Expenses Pages
# ---------------------------------------------------------------------------

@app.route('/usd/customer/<int:id>/income')
@login_required
def usd_customer_income(id):
    customer = Customer.query.get_or_404(id)
    incomes = UsdIncome.query.filter_by(customer_id=id).order_by(UsdIncome.date.desc(), UsdIncome.created_at.desc()).all()
    total_income = sum(i.amount for i in incomes)

    expenses = UsdExpense.query.filter_by(customer_id=id).order_by(UsdExpense.date.desc(), UsdExpense.created_at.desc()).all()
    total_expense = sum(e.amount for e in expenses)
    balance = total_income - total_expense

    return render_template('usd_customer_income.html',
        customer=customer, incomes=incomes,
        total_income=total_income, total_expense=total_expense, balance=balance,
        income_categories=USD_INCOME_CATEGORIES,
        expense_categories=USD_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


@app.route('/usd/customer/<int:id>/expenses')
@login_required
def usd_customer_expenses(id):
    customer = Customer.query.get_or_404(id)
    expenses = UsdExpense.query.filter_by(customer_id=id).order_by(UsdExpense.date.desc(), UsdExpense.created_at.desc()).all()
    total_expense = sum(e.amount for e in expenses)

    incomes = UsdIncome.query.filter_by(customer_id=id).order_by(UsdIncome.date.desc(), UsdIncome.created_at.desc()).all()
    total_income = sum(i.amount for i in incomes)
    balance = total_income - total_expense

    return render_template('usd_customer_expenses.html',
        customer=customer, expenses=expenses,
        total_income=total_income, total_expense=total_expense, balance=balance,
        income_categories=USD_INCOME_CATEGORIES,
        expense_categories=USD_EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS)


@app.route('/usd/income/add', methods=['POST'])
@login_required
def usd_income_add():
    customer_id = request.form.get('customer_id', type=int)
    if not customer_id:
        flash('Customer is required.', 'danger')
        return redirect(url_for('usd_account'))
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = date.today()
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0
    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('usd_customer', id=customer_id))
    income = UsdIncome(
        customer_id=customer_id, date=dt, amount=amount,
        category=request.form.get('category', 'Other Income'),
        payment_method=request.form.get('payment_method', 'Cash'),
        note=request.form.get('note', ''),
        description=request.form.get('description', ''),
        created_by=current_user.id)
    db.session.add(income)
    db.session.commit()
    flash('USD Income saved.', 'success')
    return redirect(url_for('usd_customer', id=customer_id))


@app.route('/usd/income/edit/<int:id>', methods=['POST'])
@login_required
def usd_income_edit(id):
    income = UsdIncome.query.get_or_404(id)
    try:
        income.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        pass
    try:
        income.amount = float(request.form.get('amount', income.amount))
    except ValueError:
        pass
    if income.amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('usd_customer', id=income.customer_id))
    income.category = request.form.get('category', income.category)
    income.payment_method = request.form.get('payment_method', income.payment_method)
    income.note = request.form.get('note', '')
    income.description = request.form.get('description', '')
    db.session.commit()
    flash('USD Income updated.', 'success')
    return redirect(url_for('usd_customer', id=income.customer_id))


@app.route('/usd/income/delete/<int:id>', methods=['POST'])
@login_required
def usd_income_delete(id):
    income = UsdIncome.query.get_or_404(id)
    cid = income.customer_id
    db.session.delete(income)
    db.session.commit()
    flash('USD Income deleted.', 'info')
    return redirect(url_for('usd_customer', id=cid))


@app.route('/usd/expense/add', methods=['POST'])
@login_required
def usd_expense_add():
    customer_id = request.form.get('customer_id', type=int)
    if not customer_id:
        flash('Customer is required.', 'danger')
        return redirect(url_for('usd_account'))
    try:
        dt = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        dt = date.today()
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0
    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('usd_customer', id=customer_id))
    expense = UsdExpense(
        customer_id=customer_id, date=dt, amount=amount,
        category=request.form.get('category', 'Other'),
        payment_method=request.form.get('payment_method', 'Cash'),
        note=request.form.get('note', ''),
        description=request.form.get('description', ''),
        created_by=current_user.id)
    db.session.add(expense)
    db.session.commit()
    flash('USD Expense saved.', 'success')
    return redirect(url_for('usd_customer', id=customer_id))


@app.route('/usd/expense/edit/<int:id>', methods=['POST'])
@login_required
def usd_expense_edit(id):
    expense = UsdExpense.query.get_or_404(id)
    try:
        expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError):
        pass
    try:
        expense.amount = float(request.form.get('amount', expense.amount))
    except ValueError:
        pass
    if expense.amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('usd_customer', id=expense.customer_id))
    expense.category = request.form.get('category', expense.category)
    expense.payment_method = request.form.get('payment_method', expense.payment_method)
    expense.note = request.form.get('note', '')
    expense.description = request.form.get('description', '')
    db.session.commit()
    flash('USD Expense updated.', 'success')
    return redirect(url_for('usd_customer', id=expense.customer_id))


@app.route('/usd/expense/delete/<int:id>', methods=['POST'])
@login_required
def usd_expense_delete(id):
    expense = UsdExpense.query.get_or_404(id)
    cid = expense.customer_id
    db.session.delete(expense)
    db.session.commit()
    flash('USD Expense deleted.', 'info')
    return redirect(url_for('usd_customer', id=cid))


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------

@app.route('/api/customers/<account_type>')
@login_required
def api_customers_by_account(account_type):
    if account_type == 'tzs':
        ids = [r[0] for r in db.session.query(TzsIncome.customer_id).distinct().all() if r[0]]
        ids += [r[0] for r in db.session.query(TzsExpense.customer_id).distinct().all() if r[0]]
    elif account_type == 'usd':
        ids = [r[0] for r in db.session.query(UsdIncome.customer_id).distinct().all() if r[0]]
        ids += [r[0] for r in db.session.query(UsdExpense.customer_id).distinct().all() if r[0]]
    else:
        return jsonify([])
    ids = list(set(ids))
    customers = Customer.query.filter(Customer.id.in_(ids)).order_by(Customer.name).all() if ids else []
    return jsonify([{'id': c.id, 'name': c.name} for c in customers])


@app.route('/reports')
@login_required
def reports():
    category = request.args.get('category', '')
    return render_template('reports.html',
                           income_categories=INCOME_CATEGORIES,
                           expense_categories=EXPENSE_CATEGORIES,
                           tzs_income_categories=TZS_INCOME_CATEGORIES,
                           tzs_expense_categories=TZS_EXPENSE_CATEGORIES,
                           usd_income_categories=USD_INCOME_CATEGORIES,
                           usd_expense_categories=USD_EXPENSE_CATEGORIES,
                           category=category)


@app.route('/reports/generate', methods=['POST'])
@login_required
def reports_generate():
    report_type = request.form.get('report_type', 'daily')
    report_date = request.form.get('date', date.today().isoformat())
    start_date = request.form.get('start_date', '')
    end_date = request.form.get('end_date', '')
    category = request.form.get('category', '')
    account_type = request.form.get('account_type', 'general')
    report_mode = request.form.get('report_mode', 'standard')
    customer_id = request.form.get('customer_id', type=int)
    transaction_type = request.form.get('transaction_type', 'all')

    try:
        dt = datetime.strptime(report_date, '%Y-%m-%d').date()
    except ValueError:
        dt = date.today()

    if report_type == 'daily':
        start = dt
        end = dt
        title = f'Daily Report - {dt.strftime("%B %d, %Y")}'
    elif report_type == 'weekly':
        start = dt - timedelta(days=dt.weekday())
        end = start + timedelta(days=6)
        title = f'Weekly Report - {start.strftime("%b %d")} to {end.strftime("%b %d, %Y")}'
    elif report_type == 'monthly':
        start = dt.replace(day=1)
        if dt.month == 12:
            end = dt.replace(year=dt.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
        title = f'Monthly Report - {dt.strftime("%B %Y")}'
    else:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date range.', 'danger')
            return redirect(url_for('reports'))
        title = f'Custom Report - {start.strftime("%b %d")} to {end.strftime("%b %d, %Y")}'

    # Add category filter to title
    if category:
        category_upper = category.upper().replace(' ', '')
        title = f'{title} ({category_upper} ONLY)'

    if account_type == 'tzs':
        inc_model = TzsIncome
        exp_model = TzsExpense
        inc_cats = TZS_INCOME_CATEGORIES
        exp_cats = TZS_EXPENSE_CATEGORIES
        currency_label = 'TZS'
    elif account_type == 'usd':
        inc_model = UsdIncome
        exp_model = UsdExpense
        inc_cats = USD_INCOME_CATEGORIES
        exp_cats = USD_EXPENSE_CATEGORIES
        currency_label = 'USD'
    elif account_type == 'dollar':
        inc_model = Income
        exp_model = Expense
        inc_cats = INCOME_CATEGORIES
        exp_cats = EXPENSE_CATEGORIES
        currency_label = 'USD'
    else:
        inc_model = Income
        exp_model = Expense
        inc_cats = INCOME_CATEGORIES
        exp_cats = EXPENSE_CATEGORIES
        currency_label = 'TZS'

    income_query = inc_model.query.filter(inc_model.date >= start, inc_model.date <= end)
    expense_query = exp_model.query.filter(exp_model.date >= start, exp_model.date <= end)

    if report_mode == 'customer' and customer_id and account_type in ('tzs', 'usd'):
        income_query = income_query.filter(inc_model.customer_id == customer_id)
        expense_query = expense_query.filter(exp_model.customer_id == customer_id)

    # Currency filtering for general-ledger accounts
    if account_type == 'normal':
        income_query = income_query.filter(db.or_(inc_model.currency == 'TZS', inc_model.currency.is_(None)))
        expense_query = expense_query.filter(db.or_(exp_model.currency == 'TZS', exp_model.currency.is_(None)))
    elif account_type == 'dollar':
        income_query = income_query.filter(inc_model.currency == '$')
        expense_query = expense_query.filter(exp_model.currency == '$')

    if category:
        # Check if category is primarily income or expense
        cat_in_income = category in inc_cats
        cat_in_expense = category in exp_cats

        if cat_in_income and not cat_in_expense:
            # Category is only in income categories
            income_query = income_query.filter(inc_model.category == category)
        elif cat_in_expense and not cat_in_income:
            # Category is only in expense categories
            expense_query = expense_query.filter(exp_model.category == category)
        elif cat_in_income and cat_in_expense:
            # Category exists in both lists (e.g., 'Flight Ticket')
            # Use account type to disambiguate:
            # - Dollar account: prioritize income (USD transactions often income)
            # - Other accounts: prioritize expense (TZS transactions often expenses)
            if account_type == 'dollar':
                income_query = income_query.filter(inc_model.category == category)
            else:
                expense_query = expense_query.filter(exp_model.category == category)

    # Transaction type filter (income only, expenses only, or all)
    if transaction_type == 'income':
        expense_query = expense_query.filter(db.text('1 = 0'))
        show_balance = False
    elif transaction_type == 'expense':
        income_query = income_query.filter(db.text('1 = 0'))
        show_balance = False
    else:
        show_balance = not bool(category)

    incomes = list(income_query.order_by(inc_model.date.asc()).all())
    expenses = list(expense_query.order_by(exp_model.date.asc()).all())

    # Ensure all items have payment_method and note for template
    for i in incomes:
        if not hasattr(i, 'payment_method'):
            i.payment_method = ''
        if not hasattr(i, 'note'):
            i.note = ''
    for e in expenses:
        if not hasattr(e, 'payment_method'):
            e.payment_method = ''
        if not hasattr(e, 'note'):
            e.note = ''

    # Merge TZS Account records into General report
    if account_type == 'general' and report_mode != 'customer':
        tzs_incomes = TzsIncome.query.filter(TzsIncome.date >= start, TzsIncome.date <= end).all()
        if category and category in TZS_INCOME_CATEGORIES:
            tzs_incomes = [i for i in tzs_incomes if i.category == category]
        for i in tzs_incomes:
            if not hasattr(i, 'payment_method'):
                i.payment_method = i.payment_method or ''
            if not hasattr(i, 'note'):
                i.note = i.note or ''
        incomes.extend(tzs_incomes)
        incomes.sort(key=lambda x: x.date)

        tzs_expenses = TzsExpense.query.filter(TzsExpense.date >= start, TzsExpense.date <= end).all()
        if category and category in TZS_EXPENSE_CATEGORIES:
            tzs_expenses = [e for e in tzs_expenses if e.category == category]
        for e in tzs_expenses:
            if not hasattr(e, 'payment_method'):
                e.payment_method = e.payment_method or ''
            if not hasattr(e, 'note'):
                e.note = e.note or ''
        expenses.extend(tzs_expenses)
        expenses.sort(key=lambda x: x.date)

    if account_type == 'dollar':
        total_income = sum(float(i.amount) for i in incomes)
        total_expense = sum(float(e.amount) for e in expenses)
    else:
        total_income = sum(getattr(i, 'tzs_equivalent', None) or i.amount for i in incomes)
        total_expense = sum(getattr(e, 'tzs_equivalent', None) or e.amount for e in expenses)

    extra = {}
    if report_mode == 'customer' and customer_id and account_type in ('tzs', 'usd'):
        customer = Customer.query.get(customer_id)
        extra['report_customer'] = customer
        extra['report_customer_id'] = customer_id

    return render_template('reports.html',
                           report_data=True,
                           title=title,
                           incomes=incomes,
                           expenses=expenses,
                           total_income=total_income,
                           total_expense=total_expense,
                           balance=total_income - total_expense,
                           income_categories=inc_cats,
                           expense_categories=exp_cats,
                           account_type=account_type,
                           report_mode=report_mode,
                           currency_label=currency_label,
                           start=start,
                           end=end,
                           tzs_income_categories=TZS_INCOME_CATEGORIES,
                           tzs_expense_categories=TZS_EXPENSE_CATEGORIES,
                           usd_income_categories=USD_INCOME_CATEGORIES,
                           usd_expense_categories=USD_EXPENSE_CATEGORIES,
                           category=category,
                           transaction_type=transaction_type,  # ADD THIS LINE
                           show_balance=show_balance,
                           **extra)


# ---------------------------------------------------------------------------
# USERS (Admin Only)
# ---------------------------------------------------------------------------

@app.route('/users')
@login_required
@admin_required
def users():
    users = User.query.order_by(User.username).all()
    return render_template('users.html', users=users)


@app.route('/users/add', methods=['POST'])
@login_required
@admin_required
def users_add():
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'user')

    if not username or not password:
        flash('Username and password are required.', 'danger')
        return redirect(url_for('users'))

    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'danger')
        return redirect(url_for('users'))

    user = User(username=username, full_name=full_name or username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    log_audit('create', 'user', user.id, f'Created user: {username} ({role})')
    log_monitoring_activity(current_user.username, 'CREATE', 'user', None, f'{username} ({role})')
    log_monitoring_security('PERMISSION_CHANGE', username, f'User {username} created with role {role}', 'info')
    create_notification('New User Created', f'User {username} ({role}) was created by {current_user.username}', 'NEW_USER', 'info')
    flash(f'User "{username}" created.', 'success')
    return redirect(url_for('users'))


@app.route('/users/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def users_edit(id):
    user = User.query.get_or_404(id)
    old_role = user.role
    user.full_name = request.form.get('full_name', user.full_name)
    user.role = request.form.get('role', user.role)
    password = request.form.get('password', '')
    if password:
        user.set_password(password)
    db.session.commit()
    log_audit('update', 'user', id, f'Updated user: {user.username}')
    log_monitoring_activity(current_user.username, 'UPDATE', 'user', f'role:{old_role}', f'role:{user.role}')
    if old_role != user.role:
        log_monitoring_security('ROLE_CHANGE', user.username, f'Role changed from {old_role} to {user.role}', 'warning')
        create_notification('User Role Changed', f'{user.username}\'s role changed from {old_role} to {user.role}', 'PERMISSION_CHANGED', 'warning')
    flash('User updated.', 'success')
    return redirect(url_for('users'))


@app.route('/users/toggle/<int:id>', methods=['POST'])
@login_required
@admin_required
def users_toggle(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Cannot deactivate yourself.', 'danger')
        return redirect(url_for('users'))
    user.active = not user.active
    db.session.commit()
    status = 'activated' if user.active else 'deactivated'
    log_audit('update', 'user', id, f'{status} user: {user.username}')
    flash(f'User {status}.', 'success')
    return redirect(url_for('users'))


@app.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def users_delete(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Cannot delete yourself.', 'danger')
        return redirect(url_for('users'))
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin', active=True).count()
        if admin_count <= 1:
            flash('Cannot delete the last admin.', 'danger')
            return redirect(url_for('users'))
    log_audit('delete', 'user', id, f'Deleted user: {user.username}')
    db.session.delete(user)
    db.session.commit()
    flash('User deleted.', 'info')
    return redirect(url_for('users'))





# ---------------------------------------------------------------------------
# AUDIT TRAIL (Admin Only)
# ---------------------------------------------------------------------------

@app.route('/audit')
@login_required
@admin_required
def audit():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('audit.html', logs=logs)


# ---------------------------------------------------------------------------
# SETTINGS (Admin Only)
# ---------------------------------------------------------------------------

PWA_ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

def _regenerate_pwa_icons(logo_abs_path):
    """Regenerate PWA icons from the uploaded logo so the installed app icon matches."""
    try:
        from PIL import Image, ImageDraw
        im = Image.open(logo_abs_path).convert('RGBA')
        for size in PWA_ICON_SIZES:
            canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            # White rounded-rectangle background
            draw = ImageDraw.Draw(canvas)
            radius = max(1, int(size * 0.22))
            draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=(255, 255, 255, 255))
            # Logo centered in the safe zone
            thumb = im.copy()
            fit = max(1, int(size * 0.6))
            thumb.thumbnail((fit, fit), Image.LANCZOS)
            offset = ((size - thumb.width) // 2, (size - thumb.height) // 2)
            canvas.paste(thumb, offset, thumb)
            out = os.path.join(app.root_path, 'static', 'img', f'icon-{size}.png')
            canvas.save(out, 'PNG')
        print('[OK] PWA icons regenerated from uploaded logo.')
    except Exception as e:
        print(f'[WARN] Could not regenerate PWA icons from logo: {e}')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    if request.method == 'POST':
        company_name = request.form.get('company_name', '')
        logo = request.files.get('logo')
        currency = request.form.get('currency', '$')

        set_setting('company_name', company_name)
        set_setting('currency', currency)

        if logo and logo.filename:
            ext = logo.filename.rsplit('.', 1)[-1].lower() if '.' in logo.filename else 'png'
            logo_path = os.path.join(app.root_path, 'static', 'img', f'logo.{ext}')
            logo.save(logo_path)
            set_setting('logo', f'img/logo.{ext}')
            _regenerate_pwa_icons(logo_path)

        # Email backup settings
        for k in ('smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'smtp_to'):
            v = request.form.get(k, '')
            set_setting(k, v)

        # Maintenance mode
        maintenance = request.form.get('maintenance_mode')
        set_setting('maintenance_mode', '1' if maintenance else '0')
        if maintenance:
            msg = request.form.get('maintenance_message', '')
            if msg:
                set_setting('maintenance_message', msg)
            from flask import current_app
            current_app.config['MAINTENANCE_MODE'] = True
            flash('Maintenance mode enabled. Regular users will see the maintenance page.', 'warning')
        else:
            from flask import current_app
            current_app.config.pop('MAINTENANCE_MODE', None)
            flash('Maintenance mode disabled. System is live.', 'success')

        log_audit('update', 'settings', 0, f'Settings updated by {current_user.username}')
        flash('Settings saved.', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html',
                           company_name=get_setting('company_name', 'Income & Expense Manager'),
                           currency=get_setting('currency', '$'),
                           logo=get_setting('logo', ''),
                           maintenance_mode=get_setting('maintenance_mode', '0'),
                           maintenance_message=get_setting('maintenance_message',
                               'System is currently under maintenance. Please check back later.'),
                           smtp_host=get_setting('smtp_host', ''),
                           smtp_port=get_setting('smtp_port', '587'),
                           smtp_user=get_setting('smtp_user', ''),
                           smtp_pass=get_setting('smtp_pass', ''),
                           smtp_to=get_setting('smtp_to', ''))


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    if not current_pw or not new_pw or not confirm:
        flash('All fields are required.', 'danger')
        return redirect(url_for('settings'))
    if new_pw != confirm:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('settings'))
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('settings'))
    if not current_user.check_password(current_pw):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('settings'))
    current_user.set_password(new_pw)
    db.session.commit()
    log_audit('password_change', 'user', current_user.id, f'User {current_user.username} changed their password')
    flash('Password changed successfully.', 'success')
    return redirect(url_for('settings'))


def set_setting(key, value):
    setting = Setting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.session.add(setting)
    db.session.commit()


# ---------------------------------------------------------------------------
# BACKUP SYSTEM (Admin Only + Daily Auto via Scheduled Task)
# ---------------------------------------------------------------------------

_BACKUP_DIR = os.path.join(_base_dir, 'backup')
os.makedirs(_BACKUP_DIR, exist_ok=True)

def _resolve_db_path():
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    prefix = 'sqlite:///'
    if uri.startswith(prefix):
        path = uri[len(prefix):]
        if not os.path.isabs(path):
            path = os.path.join(app.root_path, 'instance', path)
        return os.path.normpath(path)
    return os.path.join(app.root_path, 'instance', 'finance.db')

def _list_backups():
    snaps = []
    if not os.path.exists(_BACKUP_DIR):
        return snaps
    for f in sorted(os.listdir(_BACKUP_DIR), reverse=True):
        if f.startswith('backup_') and f.endswith('.db'):
            fp = os.path.join(_BACKUP_DIR, f)
            ts_str = f.replace('backup_', '').replace('.db', '')
            try:
                ts = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
            except ValueError:
                continue
            snaps.append({
                'filename': f,
                'size': f'{os.path.getsize(fp) / 1024:.1f} KB',
                'date': ts.strftime('%Y-%m-%d %H:%M'),
                'timestamp': ts,
            })
    return snaps

def _create_backup():
    db_path = _resolve_db_path()
    if not os.path.exists(db_path):
        return None
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'backup_{ts}.db'
    dst = os.path.join(_BACKUP_DIR, name)
    shutil.copy2(db_path, dst)
    # Keep only last 7
    all_bk = sorted([f for f in os.listdir(_BACKUP_DIR) if f.startswith('backup_') and f.endswith('.db')])
    for old in all_bk[:-7]:
        os.remove(os.path.join(_BACKUP_DIR, old))
    return name

@app.before_request
def auto_backup_check():
    if request.endpoint in ('static', 'robots_txt', 'sitemap_xml'):
        return
    try:
        last = get_setting('last_backup_date')
        today = datetime.now().strftime('%Y-%m-%d')
        if last != today:
            name = _create_backup()
            if name:
                set_setting('last_backup_date', today)
                log_monitoring_activity('system', 'BACKUP', 'system', None, name)
    except Exception:
        pass

def _send_backup_email(backup_name):
    """Email a backup file using configured SMTP settings. Returns (success, message)."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email.utils import formatdate
    host = get_setting('smtp_host', '')
    port = get_setting('smtp_port', '587')
    user = get_setting('smtp_user', '')
    pw = get_setting('smtp_pass', '')
    to = get_setting('smtp_to', '')
    if not host or not user or not pw or not to:
        return False, 'SMTP not configured. Go to Settings > Email Backup.'
    fp = os.path.join(_BACKUP_DIR, backup_name)
    if not os.path.exists(fp):
        return False, 'Backup file not found.'
    try:
        msg = MIMEMultipart()
        msg['From'] = user
        msg['To'] = to
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = f'{get_setting("company_name", "System")} - Database Backup ({backup_name})'
        msg.attach(MIMEText(f'Automated database backup: {backup_name}\n\nSize: {os.path.getsize(fp) / 1024:.1f} KB', 'plain'))
        part = MIMEBase('application', 'octet-stream')
        with open(fp, 'rb') as f:
            part.set_payload(f.read())
        from email import encoders
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{backup_name}"')
        msg.attach(part)
        smtp = smtplib.SMTP(host, int(port), timeout=15)
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(user, pw)
        smtp.sendmail(user, to, msg.as_string())
        smtp.quit()
        return True, f'Backup sent to {to}'
    except Exception as e:
        return False, str(e)


@app.route('/admin/backup')
@login_required
@admin_required
def admin_backup():
    email_ok = bool(get_setting('smtp_host', ''))
    return render_template('backup.html', backups=_list_backups(), email_configured=email_ok)

@app.route('/admin/backup/create', methods=['POST'])
@login_required
@admin_required
def admin_backup_create():
    name = _create_backup()
    if name:
        log_monitoring_activity(current_user.username, 'BACKUP', 'system', None, name)
        flash(f'Backup created: {name}', 'success')
    else:
        flash('Database file not found.', 'danger')
    return redirect(url_for('admin_backup'))

@app.route('/admin/backup/download/<filename>')
@login_required
@admin_required
def admin_backup_download(filename):
    safe = os.path.basename(filename)
    fp = os.path.join(_BACKUP_DIR, safe)
    if not os.path.exists(fp):
        flash('Backup file not found.', 'danger')
        return redirect(url_for('admin_backup'))
    return send_file(fp, as_attachment=True, download_name=safe)

@app.route('/admin/backup/email/<filename>', methods=['POST'])
@login_required
@admin_required
def admin_backup_email(filename):
    name = os.path.basename(filename)
    ok, msg = _send_backup_email(name)
    if ok:
        flash(msg, 'success')
        log_monitoring_activity(current_user.username, 'BACKUP_EMAIL', 'system', None, name)
    else:
        flash(f'Email failed: {msg}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/api/backup/email')
def api_backup_email():
    token = request.args.get('token', '')
    if token != app.config.get('SECRET_KEY', ''):
        return 'forbidden', 403
    snaps = _list_backups()
    if not snaps:
        return 'no backups to send', 200
    name = snaps[0]['filename']
    ok, msg = _send_backup_email(name)
    if ok:
        return f'email sent: {name}', 200
    return f'email failed: {msg}', 500


@app.route('/api/backup/tick')
def api_backup_tick():
    token = request.args.get('token', '')
    if token != app.config.get('SECRET_KEY', ''):
        return 'forbidden', 403
    name = _create_backup()
    if name:
        return f'backup created: {name}', 200
    return 'no backup needed', 200


# ---------------------------------------------------------------------------
# CSV EXPORT (Authenticated Users)
# ---------------------------------------------------------------------------

@app.route('/export/incomes')
@login_required
def export_incomes():
    import csv
    incomes = Income.query.filter_by(created_by=current_user.id).order_by(Income.date.desc()).all()
    if current_user.role == 'admin':
        uid = request.args.get('user_id', type=int)
        if uid:
            incomes = Income.query.filter_by(created_by=uid).order_by(Income.date.desc()).all()
    currency_filter = request.args.get('currency', '')
    if currency_filter:
        incomes = [i for i in incomes if i.currency == currency_filter]
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(['Date', 'Category', 'Amount', 'Currency', 'Description', 'Recorded'])
    for inc in incomes:
        w.writerow([inc.date, inc.category, inc.amount, inc.currency, inc.description, inc.created_at])
    out = io.BytesIO(si.getvalue().encode('utf-8-sig'))
    return send_file(out, mimetype='text/csv', as_attachment=True, download_name='incomes.csv')

@app.route('/export/expenses')
@login_required
def export_expenses():
    import csv
    expenses = Expense.query.filter_by(created_by=current_user.id).order_by(Expense.date.desc()).all()
    if current_user.role == 'admin':
        uid = request.args.get('user_id', type=int)
        if uid:
            expenses = Expense.query.filter_by(created_by=uid).order_by(Expense.date.desc()).all()
    currency_filter = request.args.get('currency', '')
    if currency_filter:
        expenses = [e for e in expenses if e.currency == currency_filter]
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(['Date', 'Category', 'Amount', 'Currency', 'Description', 'Recorded'])
    for exp in expenses:
        w.writerow([exp.date, exp.category, exp.amount, exp.currency, exp.description, exp.created_at])
    out = io.BytesIO(si.getvalue().encode('utf-8-sig'))
    return send_file(out, mimetype='text/csv', as_attachment=True, download_name='expenses.csv')

@app.route('/export/database')
@login_required
@admin_required
def export_database():
    db_path = _resolve_db_path()
    if not os.path.exists(db_path):
        flash('Database file not found.', 'danger')
        return redirect(url_for('dashboard'))
    return send_file(db_path, as_attachment=True, download_name='finance.db')


# ---------------------------------------------------------------------------
# MONITORING ROUTES (Admin Only)
# ---------------------------------------------------------------------------

@app.route('/monitoring')
@login_required
@admin_required
def monitoring_dashboard():
    errors = MonitoringError.query.order_by(MonitoringError.id.desc()).limit(10).all()
    activities = MonitoringActivity.query.order_by(MonitoringActivity.id.desc()).limit(10).all()
    notifications = MonitoringNotification.query.order_by(MonitoringNotification.id.desc()).limit(10).all()
    security = MonitoringSecurity.query.order_by(MonitoringSecurity.id.desc()).limit(10).all()
    perf = MonitoringPerformance.query.order_by(MonitoringPerformance.id.desc()).first()
    today = date.today()
    today_errors = MonitoringError.query.filter(
        db.func.date(MonitoringError.created_at) == today).count()
    failed_logins = MonitoringSecurity.query.filter(
        MonitoringSecurity.event_type == 'FAILED_LOGIN',
        db.func.date(MonitoringSecurity.created_at) == today).count()
    active_sessions = User.query.filter_by(active=True).count()

    # DB status
    db_connected = True
    db_last_conn = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        db_connected = False
        db_last_conn = 'N/A'

    return render_template('monitoring/dashboard.html',
        errors=errors, activities=activities, notifications=notifications,
        security=security, perf=perf, today_errors=today_errors,
        failed_logins=failed_logins, active_sessions=active_sessions,
        db_connected=db_connected, db_last_conn=db_last_conn)


@app.route('/monitoring/health')
@login_required
@admin_required
def monitoring_health():
    stats = get_system_stats()
    db_connected = True
    db_last_conn = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        db_connected = False
        db_last_conn = 'N/A'

    api_healthy = True

    uptime = 'N/A'
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_secs = float(f.read().split()[0])
            days = int(uptime_secs // 86400)
            hours = int((uptime_secs % 86400) // 3600)
            uptime = f'{days}d {hours}h'
    except Exception:
        pass

    # Overall health percentage
    health = 100
    if not db_connected: health -= 25
    if not api_healthy: health -= 20
    if stats.get('cpu_percent', 0) > 90: health -= 15
    if stats.get('ram_percent', 0) > 90: health -= 15
    if stats.get('storage_percent', 0) > 90: health -= 15
    health = max(0, health)

    return render_template('monitoring/health.html',
        stats=stats, db_connected=db_connected, db_last_conn=db_last_conn,
        api_healthy=api_healthy, uptime=uptime, health=health)


@app.route('/monitoring/errors')
@login_required
@admin_required
def monitoring_errors():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    error_type = request.args.get('type', '')
    severity = request.args.get('severity', '')
    status = request.args.get('status', '')

    query = MonitoringError.query
    if search:
        query = query.filter(MonitoringError.description.ilike(f'%{search}%'))
    if error_type:
        query = query.filter(MonitoringError.error_type == error_type)
    if severity:
        query = query.filter(MonitoringError.severity == severity)
    if status:
        query = query.filter(MonitoringError.status == status)

    errors = query.order_by(MonitoringError.id.desc()).paginate(
        page=page, per_page=30, error_out=False)

    error_types = db.session.query(MonitoringError.error_type).distinct().all()
    return render_template('monitoring/errors.html',
        errors=errors, error_types=[e[0] for e in error_types],
        search=search, filter_type=error_type, filter_severity=severity, filter_status=status)


@app.route('/monitoring/errors/export')
@login_required
@admin_required
def monitoring_errors_export():
    import csv
    errors = MonitoringError.query.order_by(MonitoringError.id.desc()).limit(1000).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Type', 'Description', 'Endpoint', 'User', 'Severity', 'Status', 'IP', 'Date'])
    for e in errors:
        writer.writerow([e.id, e.error_type, e.description, e.endpoint, e.username,
                        e.severity, e.status, e.ip_address,
                        e.created_at.strftime('%Y-%m-%d %H:%M') if e.created_at else ''])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv', as_attachment=True,
        download_name=f'errors_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@app.route('/monitoring/errors/resolve/<int:id>', methods=['POST'])
@login_required
@admin_required
def monitoring_error_resolve(id):
    err = MonitoringError.query.get_or_404(id)
    err.status = 'resolved'
    db.session.commit()
    flash('Error marked as resolved.', 'success')
    return redirect(url_for('monitoring_errors'))


@app.route('/monitoring/performance')
@login_required
@admin_required
def monitoring_performance():
    # Record a new snapshot
    record_performance_snapshot()

    # Get history (last 60 entries)
    history = MonitoringPerformance.query.order_by(
        MonitoringPerformance.id.desc()).limit(60).all()
    history.reverse()

    stats = get_system_stats()
    latest = MonitoringPerformance.query.order_by(MonitoringPerformance.id.desc()).first()

    # Chart data
    labels = [h.created_at.strftime('%H:%M') if h.created_at else '' for h in history]
    cpu_data = [h.cpu_usage for h in history]
    ram_data = [h.ram_usage for h in history]
    db_time = [h.db_response_time for h in history]
    api_time = [h.api_response_time for h in history]

    return render_template('monitoring/performance.html',
        stats=stats, latest=latest,
        chart_labels=json.dumps(labels),
        chart_cpu=json.dumps(cpu_data),
        chart_ram=json.dumps(ram_data),
        chart_db=json.dumps(db_time),
        chart_api=json.dumps(api_time))


@app.route('/monitoring/performance/data')
@login_required
@admin_required
def monitoring_performance_data():
    record_performance_snapshot()
    stats = get_system_stats()
    latest = MonitoringPerformance.query.order_by(MonitoringPerformance.id.desc()).first()
    return jsonify({
        'cpu': stats.get('cpu_percent', 0),
        'ram': stats.get('ram_percent', 0),
        'ram_used': stats.get('ram_used', 0),
        'ram_total': stats.get('ram_total', 0),
        'storage': stats.get('storage_percent', 0),
        'storage_used': stats.get('storage_used', 0),
        'storage_total': stats.get('storage_total', 0),
        'active_users': latest.active_users if latest else 0,
        'total_requests': latest.total_requests if latest else 0,
        'failed_requests': latest.failed_requests if latest else 0,
        'slow_requests': latest.slow_requests if latest else 0,
        'db_response_time': latest.db_response_time if latest else 0,
        'api_response_time': latest.api_response_time if latest else 0,
        'avg_page_load_time': latest.avg_page_load_time if latest else 0,
    })


@app.route('/monitoring/security')
@login_required
@admin_required
def monitoring_security():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    event_type = request.args.get('type', '')
    status_filter = request.args.get('status', '')

    query = MonitoringSecurity.query
    if search:
        query = query.filter(
            db.or_(MonitoringSecurity.username.ilike(f'%{search}%'),
                   MonitoringSecurity.ip_address.ilike(f'%{search}%'),
                   MonitoringSecurity.details.ilike(f'%{search}%')))
    if event_type:
        query = query.filter(MonitoringSecurity.event_type == event_type)
    if status_filter:
        query = query.filter(MonitoringSecurity.status == status_filter)

    events = query.order_by(MonitoringSecurity.id.desc()).paginate(
        page=page, per_page=30, error_out=False)

    event_types = db.session.query(MonitoringSecurity.event_type).distinct().all()
    return render_template('monitoring/security.html',
        events=events, event_types=[e[0] for e in event_types],
        search=search, filter_type=event_type, filter_status=status_filter)


@app.route('/monitoring/activity')
@login_required
@admin_required
def monitoring_activity():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    action_filter = request.args.get('action', '')
    module_filter = request.args.get('module', '')

    query = MonitoringActivity.query
    if search:
        query = query.filter(
            db.or_(MonitoringActivity.username.ilike(f'%{search}%'),
                   MonitoringActivity.module.ilike(f'%{search}%'),
                   MonitoringActivity.action.ilike(f'%{search}%')))
    if action_filter:
        query = query.filter(MonitoringActivity.action == action_filter)
    if module_filter:
        query = query.filter(MonitoringActivity.module == module_filter)

    activities = query.order_by(MonitoringActivity.id.desc()).paginate(
        page=page, per_page=30, error_out=False)

    actions = db.session.query(MonitoringActivity.action).distinct().all()
    modules = db.session.query(MonitoringActivity.module).distinct().all()
    return render_template('monitoring/activity.html',
        activities=activities, actions=[a[0] for a in actions],
        modules=[m[0] for m in modules],
        search=search, filter_action=action_filter, filter_module=module_filter)


@app.route('/monitoring/notifications')
@login_required
@admin_required
def monitoring_notifications():
    page = request.args.get('page', 1, type=int)
    ntype = request.args.get('type', '')
    severity = request.args.get('severity', '')

    query = MonitoringNotification.query
    if ntype:
        query = query.filter(MonitoringNotification.notification_type == ntype)
    if severity:
        query = query.filter(MonitoringNotification.severity == severity)

    notifications = query.order_by(MonitoringNotification.id.desc()).paginate(
        page=page, per_page=30, error_out=False)
    unread_count = MonitoringNotification.query.filter_by(is_read=False).count()

    notif_types = db.session.query(MonitoringNotification.notification_type).distinct().all()
    return render_template('monitoring/notifications.html',
        notifications=notifications, unread_count=unread_count,
        notif_types=[n[0] for n in notif_types],
        filter_type=ntype, filter_severity=severity)


@app.route('/monitoring/notifications/read/<int:id>', methods=['POST'])
@login_required
@admin_required
def monitoring_notification_read(id):
    notif = MonitoringNotification.query.get_or_404(id)
    notif.is_read = True
    db.session.commit()
    return redirect(url_for('monitoring_notifications'))


@app.route('/monitoring/notifications/read-all', methods=['POST'])
@login_required
@admin_required
def monitoring_notification_read_all():
    MonitoringNotification.query.filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('monitoring_notifications'))


@app.route('/monitoring/notifications/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def monitoring_notification_delete(id):
    notif = MonitoringNotification.query.get_or_404(id)
    db.session.delete(notif)
    db.session.commit()
    flash('Notification deleted.', 'info')
    return redirect(url_for('monitoring_notifications'))


@app.route('/monitoring/notifications/count')
@login_required
@admin_required
def monitoring_notification_count():
    count = MonitoringNotification.query.filter_by(is_read=False).count()
    return jsonify({'count': count})


# ---------------------------------------------------------------------------
# CREATE TABLES & DEFAULT ADMIN
# ---------------------------------------------------------------------------

def init_db():
    with app.app_context():
        db.create_all()
        # Migrate existing DBs: add recorded_by and currency columns if missing
        for table in ['income', 'expense']:
            try:
                from sqlalchemy import inspect
                insp = inspect(db.engine)
                cols = [c['name'] for c in insp.get_columns(table)]
                if 'recorded_by' not in cols:
                    db.session.execute(
                        db.text(f'ALTER TABLE {table} ADD COLUMN recorded_by VARCHAR(100) DEFAULT \'\'')
                    )
                    db.session.commit()
                    print(f'[OK] Added recorded_by column to {table}')
                if 'currency' not in cols:
                    db.session.execute(
                        db.text(f"ALTER TABLE {table} ADD COLUMN currency VARCHAR(10) DEFAULT 'TZS'")
                    )
                    db.session.commit()
                    print(f'[OK] Added currency column to {table}')
                if 'usd_to_tzs_rate' not in cols:
                    db.session.execute(
                        db.text(f'ALTER TABLE {table} ADD COLUMN usd_to_tzs_rate FLOAT')
                    )
                    db.session.commit()
                    print(f'[OK] Added usd_to_tzs_rate column to {table}')
                if 'tzs_equivalent' not in cols:
                    db.session.execute(
                        db.text(f'ALTER TABLE {table} ADD COLUMN tzs_equivalent FLOAT')
                    )
                    db.session.execute(
                        db.text(f'UPDATE {table} SET tzs_equivalent = amount')
                    )
                    db.session.commit()
                    print(f'[OK] Added tzs_equivalent column to {table}')
            except Exception as e:
                db.session.rollback()
                print(f'[INFO] {e}')
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                full_name='System Administrator',
                role='admin'
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print('[OK] Default admin created: admin / admin123')
        else:
            admin_user.set_password('admin123')
            db.session.commit()
            print('[OK] Admin password synced to admin123')

        print('[OK] Database ready.')


# ---------------------------------------------------------------------------
# CONTEXT PROCESSOR
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    # Cache-busting version based on static file modification times
    _static_ver = hashlib.md5()
    for _rel in ('static/js/main.js', 'static/css/style.css'):
        _p = os.path.join(_base_dir, _rel)
        try:
            _static_ver.update(str(os.path.getmtime(_p)).encode())
        except OSError:
            pass
    notif_count = 0
    try:
        notif_count = MonitoringNotification.query.filter_by(is_read=False).count()
    except Exception:
        pass
    return {
        'company_name': get_setting('company_name', 'Income & Expense Manager'),
        'currency_symbol': get_setting('currency', '$'),
        'logo': get_setting('logo', ''),
        'now': datetime.now(),
        'timedelta': timedelta,
        'csrf_token': session.get('csrf_token', ''),
        'unread_notifications': notif_count,
        'static_version': _static_ver.hexdigest()[:8],
    }


# ---------------------------------------------------------------------------
# ERROR HANDLERS (monitoring)
# ---------------------------------------------------------------------------

@app.errorhandler(500)
def handle_500(e):
    log_monitoring_error('SERVER_ERROR', str(e)[:500], severity='critical')
    return render_template('monitoring/error.html', code=500,
        message='Internal server error. Our team has been notified.'), 500


@app.route('/admin/debug-user/<token>')
def admin_debug_user(token):
    expected = app.config.get('SECRET_KEY', '')[:16]
    if token != expected:
        return 'Bad token', 403
    from werkzeug.security import check_password_hash
    u = User.query.filter_by(username='admin').first()
    if not u:
        return 'No admin user'
    pw = 'Admin123!'
    lines = [
        f'Username: {u.username}',
        f'Active: {u.active}',
        f'Role: {u.role}',
        f'Full Name: {u.full_name}',
        f'Hash starts: {u.password_hash[:30]}',
        f'Hash ends: {u.password_hash[-30:]}',
        f'Check Admin123!: {check_password_hash(u.password_hash, pw)}',
    ]
    return '<br>'.join(lines)


@app.route('/admin/reset-admin/<token>')
def admin_reset_admin(token):
    expected = app.config.get('SECRET_KEY', '')[:16]
    if token != expected:
        return 'Bad token', 403
    new_pw = secrets.token_urlsafe(12)
    u = User.query.filter_by(username='admin').first()
    if not u:
        return 'No admin user'
    u.set_password(new_pw)
    db.session.commit()
    return f'Password reset to: {new_pw}'


@app.errorhandler(404)
def handle_404(e):
    return render_template('monitoring/error.html', code=404,
        message='The requested page was not found.'), 404


@app.errorhandler(403)
def handle_403(e):
    return render_template('monitoring/error.html', code=403,
        message='You do not have permission to access this page.'), 403


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

# Initialize database on startup (also runs when imported by WSGI on PythonAnywhere)
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
