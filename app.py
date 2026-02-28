"""
Redline – QR-Code-basiertes Defektmeldesystem
Application factory.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, logout_user
from flask_mail import Mail
from sqlalchemy import text

from config import APP_VERSION, Config, config_by_name
from extensions import limiter, metrics_exporter, migrate
from metrics import app_info, business_collector, db_up
from models import DefectCategory, Device, DeviceCategory, EmailRecipient, User, db

# --------------------------------------------------------------------------- #
#  NFR-SEC-007 – Sanitize sensitive key=value pairs from log output            #
# --------------------------------------------------------------------------- #


class SanitizeFilter(logging.Filter):
    """Redacts secret values from log records.

    Replaces the value in patterns like ``password=geheim123`` with ``***``
    so credentials are never written to log files or stdout.

    Patterns matched (case-insensitive): password, passwd, token, secret, key.
    """

    _PATTERN = re.compile(r"(?i)(password|passwd|token|secret|key)=\S+")

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.msg = self._PATTERN.sub(r"\1=***", str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._PATTERN.sub(r"\1=***", str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._PATTERN.sub(r"\1=***", str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True  # always pass the (possibly modified) record


# --------------------------------------------------------------------------- #
#  Logging                                                                      #
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Register SanitizeFilter on every root handler so no sensitive value leaks.
_sanitize_filter = SanitizeFilter()
for _handler in logging.root.handlers:
    _handler.addFilter(_sanitize_filter)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  App factory                                                                  #
# --------------------------------------------------------------------------- #


def create_app(config_class=None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_class: A config class from config.py (or a dict of overrides).
                      When None the class is selected from the FLASK_ENV
                      environment variable (default: DevelopmentConfig).
    """
    if config_class is None:
        env = os.environ.get("FLASK_ENV", "development")
        config_class = config_by_name.get(env, Config)

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validate config – warns (dev) or aborts (production) on bad values.
    if not app.config.get("TESTING"):
        config_class.validate()

    # Ensure QR code and photo upload directories exist
    os.makedirs(app.config["QR_CODE_DIR"], exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ---------------------------------------------------------------------- #
    #  Extensions                                                              #
    # ---------------------------------------------------------------------- #
    db.init_app(app)
    migrate.init_app(app, db)
    Mail(app)
    limiter.init_app(app)

    # Prometheus metrics – disabled in test runs to keep the registry clean
    if not app.config.get("TESTING"):
        env = os.environ.get("FLASK_ENV", "development")
        metrics_exporter.init_app(app)
        app_info.info({"version": APP_VERSION, "environment": env})
        business_collector.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bitte melden Sie sich an, um fortzufahren."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # ---------------------------------------------------------------------- #
    #  Security headers                                                        #
    # ---------------------------------------------------------------------- #

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Only send HSTS over HTTPS (don't lock out HTTP-only development)
        if not app.debug and app.config.get("APP_BASE_URL", "").startswith("https://"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    # ---------------------------------------------------------------------- #
    #  NFR-SEC-006 – Time-based session expiry                                #
    # ---------------------------------------------------------------------- #

    @app.before_request
    def check_session_expiry():
        """Log out users whose session exceeds SESSION_LIFETIME_HOURS."""
        if not current_user.is_authenticated:
            return None
        login_time_str = session.get("_login_time")
        if login_time_str is None:
            # No timestamp → session predates this feature or was tampered.
            logout_user()
            flash("Session abgelaufen, bitte erneut anmelden.", "warning")
            return redirect(url_for("auth.login"))
        try:
            login_dt = datetime.fromisoformat(login_time_str)
        except ValueError:
            logout_user()
            flash("Session abgelaufen, bitte erneut anmelden.", "warning")
            return redirect(url_for("auth.login"))
        max_age = timedelta(hours=app.config.get("SESSION_LIFETIME_HOURS", 8))
        if datetime.now(timezone.utc) - login_dt > max_age:
            session.pop("_login_time", None)
            logout_user()
            flash("Session abgelaufen, bitte erneut anmelden.", "warning")
            return redirect(url_for("auth.login"))
        return None

    # ---------------------------------------------------------------------- #
    #  NFR-SEC-004 – Global anonymous-access gate (defense-in-depth)          #
    # ---------------------------------------------------------------------- #

    # Paths that must stay accessible without a Flask-Login session.
    # API routes (/api/) use HTTP Basic Auth and handle their own 401 responses.
    _AUTH_EXEMPT = ("/auth/", "/healthz", "/metrics", "/static/", "/api/")

    @app.before_request
    def require_auth():
        """Redirect unauthenticated web users to the login page."""
        if any(request.path.startswith(p) for p in _AUTH_EXEMPT):
            return None
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        return None

    # ---------------------------------------------------------------------- #
    #  Template globals                                                        #
    # ---------------------------------------------------------------------- #

    @app.context_processor
    def inject_app_version():
        from datetime import datetime as _dt
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        db_path = (
            db_uri.replace("sqlite:///", "")
            if db_uri.startswith("sqlite:///")
            else db_uri
        )
        return {
            "app_version": APP_VERSION,
            "show_debug_info": app.config.get("SHOW_DEBUG_INFO", False),
            "app_db_path": db_path,
            "current_year": _dt.now().year,
        }

    # ---------------------------------------------------------------------- #
    #  Blueprints                                                              #
    # ---------------------------------------------------------------------- #
    from routes.auth import auth_bp
    from routes.report import report_bp
    from routes.admin import admin_bp
    from routes.disponent import disponent_bp
    from routes.werkstatt import werkstatt_bp
    from api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(disponent_bp)
    app.register_blueprint(werkstatt_bp)
    app.register_blueprint(api_bp)

    # ---------------------------------------------------------------------- #
    #  Standalone routes                                                       #
    # ---------------------------------------------------------------------- #

    @app.route("/healthz")
    def healthz():
        """Liveness + readiness probe.

        Checks DB connectivity and updates the ``redline_db_up`` Prometheus
        gauge so the health state is always reflected in metrics.

        Returns 200 {"status": "ok"} or 503 {"status": "degraded"}.
        """
        try:
            db.session.execute(text("SELECT 1"))
            if not app.config.get("TESTING"):
                db_up.set(1)
            return jsonify({"status": "ok", "db": "ok"}), 200
        except Exception as exc:  # noqa: BLE001
            logger.error("Health check – DB unreachable: %s", exc)
            if not app.config.get("TESTING"):
                db_up.set(0)
            return jsonify({"status": "degraded", "db": "error"}), 503

    @app.route("/api/docs")
    def api_docs():
        return render_template("api_docs.html")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for("admin.dashboard"))
            if current_user.is_disponent:
                return redirect(url_for("disponent.dashboard"))
            if current_user.is_werkstatt:
                return redirect(url_for("werkstatt.dashboard"))
            if current_user.is_api_user:
                return redirect(url_for("auth.logout"))
            return redirect(url_for("admin.all_defects"))
        return redirect(url_for("auth.login"))

    # ---------------------------------------------------------------------- #
    #  Error handlers                                                          #
    # ---------------------------------------------------------------------- #

    @app.errorhandler(403)
    def forbidden(e):
        return (
            render_template(
                "error.html",
                title="Zugriff verweigert",
                message="Sie haben keine Berechtigung für diese Seite.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(e):
        return (
            render_template(
                "error.html",
                title="Seite nicht gefunden",
                message="Die angeforderte Seite existiert nicht.",
            ),
            404,
        )

    @app.errorhandler(429)
    def too_many_requests(e):
        return (
            render_template(
                "error.html",
                title="Zu viele Anfragen",
                message="Zu viele Anfragen. Bitte warten Sie kurz und versuchen Sie es erneut.",
            ),
            429,
        )

    # ---------------------------------------------------------------------- #
    #  DB init + seed data                                                     #
    # ---------------------------------------------------------------------- #
    with app.app_context():
        db.create_all()
        _seed_db()

    return app


# --------------------------------------------------------------------------- #
#  Seed helper                                                                  #
# --------------------------------------------------------------------------- #


def _seed_db() -> None:
    """Create default users and seed data on first run."""
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        logger.warning(
            "Created default admin user (admin / admin123). "
            "CHANGE THIS PASSWORD IMMEDIATELY!"
        )

    if not User.query.filter_by(username="team_login").first():
        team = User(username="team_login", is_admin=False, is_community=True)
        team.set_password("team2025")
        db.session.add(team)
        logger.warning(
            "Created default team_login user (team_login / team2025). "
            "Change this password regularly."
        )

    if not User.query.filter_by(username="disponent").first():
        disp = User(username="disponent", is_disponent=True)
        disp.set_password("disp2025")
        db.session.add(disp)
        logger.warning(
            "Created default disponent user (disponent / disp2025). "
            "CHANGE THIS PASSWORD before going live!"
        )

    if not User.query.filter_by(username="werkstatt").first():
        ws = User(username="werkstatt", is_werkstatt=True)
        ws.set_password("werk2025")
        db.session.add(ws)
        logger.warning(
            "Created default werkstatt user (werkstatt / werk2025). "
            "CHANGE THIS PASSWORD before going live!"
        )

    if not User.query.filter_by(username="api").first():
        api_user = User(username="api", is_api_user=True)
        api_user.set_password("api2025")
        db.session.add(api_user)
        logger.warning(
            "Created default API user (api / api2025). "
            "CHANGE THIS PASSWORD before going live!"
        )

    if DefectCategory.query.count() == 0:
        for i, name in enumerate(Config.DEFECT_CATEGORIES):
            db.session.add(DefectCategory(name=name, sort_order=i))
        logger.info("Seeded %d default defect categories.", len(Config.DEFECT_CATEGORIES))

    if DeviceCategory.query.count() == 0:
        for i, (name, color) in enumerate(Config.DEVICE_CATEGORIES):
            db.session.add(DeviceCategory(name=name, color=color, sort_order=i))
        logger.info("Seeded %d default device categories.", len(Config.DEVICE_CATEGORIES))

    if EmailRecipient.query.count() == 0:
        workshop_email = Config.WORKSHOP_EMAIL
        if workshop_email and "@" in workshop_email:
            db.session.add(EmailRecipient(name="Werkstatt", email=workshop_email))
            logger.info("Seeded default email recipient: %s", workshop_email)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "Datenbank-Seed fehlgeschlagen: %s. "
            "Standarddaten (Admin-Benutzer, Kategorien) wurden möglicherweise "
            "nicht angelegt.",
            exc,
        )


# --------------------------------------------------------------------------- #
#  Module-level app instance (used by gunicorn / flask run)                    #
# --------------------------------------------------------------------------- #

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
