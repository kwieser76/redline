"""
Redline – QR-Code-basiertes Defektmeldesystem
Application factory.
"""

import logging
import os

from flask import Flask, redirect, render_template, url_for
from flask_login import LoginManager, current_user
from flask_mail import Mail

from config import Config, config_by_name
from extensions import limiter, migrate
from models import DefectCategory, Device, EmailRecipient, User, db

# --------------------------------------------------------------------------- #
#  Logging                                                                      #
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
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

    # Ensure QR code directory exists
    os.makedirs(app.config["QR_CODE_DIR"], exist_ok=True)

    # ---------------------------------------------------------------------- #
    #  Extensions                                                              #
    # ---------------------------------------------------------------------- #
    db.init_app(app)
    migrate.init_app(app, db)
    Mail(app)
    limiter.init_app(app)

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
    #  Blueprints                                                              #
    # ---------------------------------------------------------------------- #
    from routes.auth import auth_bp
    from routes.report import report_bp
    from routes.admin import admin_bp
    from api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # ---------------------------------------------------------------------- #
    #  Standalone routes                                                       #
    # ---------------------------------------------------------------------- #

    @app.route("/api/docs")
    def api_docs():
        return render_template("api_docs.html")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for("admin.dashboard"))
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

    if DefectCategory.query.count() == 0:
        for i, name in enumerate(Config.DEFECT_CATEGORIES):
            db.session.add(DefectCategory(name=name, sort_order=i))
        logger.info("Seeded %d default defect categories.", len(Config.DEFECT_CATEGORIES))

    if EmailRecipient.query.count() == 0:
        workshop_email = Config.WORKSHOP_EMAIL
        if workshop_email and "@" in workshop_email:
            db.session.add(EmailRecipient(name="Werkstatt", email=workshop_email))
            logger.info("Seeded default email recipient: %s", workshop_email)

    db.session.commit()


# --------------------------------------------------------------------------- #
#  Module-level app instance (used by gunicorn / flask run)                    #
# --------------------------------------------------------------------------- #

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
