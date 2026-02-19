"""
Redline – QR-Code-basiertes Defektmeldesystem
Main Flask application entry point.
"""
import io
import logging
import os
from datetime import datetime, timezone

import qrcode
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_mail import Mail

from config import Config
from models import Defect, Device, User, db
from filemaker import fm_client
from notifications import send_defect_notification, send_event_summary_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure QR code directory exists
    os.makedirs(app.config["QR_CODE_DIR"], exist_ok=True)

    # Extensions
    db.init_app(app)
    mail = Mail(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bitte melden Sie sich an, um fortzufahren."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # ------------------------------------------------------------------
    # Blueprints (inline for simplicity)
    # ------------------------------------------------------------------
    from flask import Blueprint

    auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
    report_bp = Blueprint("report", __name__, url_prefix="/report")
    admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

    # ---- Auth routes ----

    @auth_bp.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user, remember=False)
                next_page = request.args.get("next")
                return redirect(next_page or url_for("index"))
            flash("Ungültiger Benutzername oder Passwort.", "danger")
        return render_template("login.html")

    @auth_bp.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Sie wurden abgemeldet.", "info")
        return redirect(url_for("auth.login"))

    # ---- Defect report routes ----

    @report_bp.route("/<string:device_id>", methods=["GET", "POST"])
    @login_required
    def defect_form(device_id: str):
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return render_template(
                "error.html",
                title="Gerät nicht gefunden",
                message=f"Das Gerät mit der ID '{device_id}' ist im System nicht registriert.",
            ), 404

        categories = app.config["DEFECT_CATEGORIES"]

        if request.method == "POST":
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()
            event_name = request.form.get("event_name", "").strip()
            project_number = request.form.get("project_number", "").strip()

            errors = []
            if not category or category not in categories:
                errors.append("Bitte wählen Sie eine gültige Kategorie.")
            if not description:
                errors.append("Bitte geben Sie eine Beschreibung ein.")
            if not event_name:
                errors.append("Bitte geben Sie den Eventnamen ein.")
            if not project_number:
                errors.append("Bitte geben Sie die Projektnummer ein.")

            if errors:
                for err in errors:
                    flash(err, "danger")
                return render_template(
                    "report_defect.html",
                    device=device,
                    categories=categories,
                    form_data=request.form,
                )

            # Create defect record
            defect = Defect(
                device_id=device.id,
                category=category,
                description=description,
                event_name=event_name,
                project_number=project_number,
                reporter=current_user.username,
            )
            db.session.add(defect)

            # Update device status
            device.status = "Wartung"
            db.session.commit()

            # Sync to FileMaker
            fm_client.update_device_status(device.device_id, "Wartung")
            fm_client.create_defect_record(
                {
                    "Geräte-ID": device.device_id,
                    "Gerätename": device.name,
                    "Kategorie": category,
                    "Beschreibung": description,
                    "Eventname": event_name,
                    "Projektnummer": project_number,
                    "Status": "Offen",
                    "Gemeldet_Von": current_user.username,
                }
            )

            # Send email notification
            send_defect_notification(
                mail, defect, device.name, app.config["WORKSHOP_EMAIL"]
            )

            flash("Defekt erfolgreich gemeldet.", "success")
            return redirect(url_for("report.defect_success", device_id=device.device_id))

        return render_template(
            "report_defect.html",
            device=device,
            categories=categories,
            form_data={},
        )

    @report_bp.route("/<string:device_id>/success")
    @login_required
    def defect_success(device_id: str):
        device = Device.query.filter_by(device_id=device_id).first_or_404()
        return render_template("defect_success.html", device=device)

    # ---- Admin routes ----

    def admin_required(f):
        """Decorator: only admin users may access."""
        from functools import wraps

        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                abort(403)
            return f(*args, **kwargs)

        return login_required(decorated)

    @admin_bp.route("/")
    @admin_required
    def dashboard():
        devices = Device.query.order_by(Device.name).all()
        open_defects = Defect.query.filter_by(status="Offen").count()
        total_devices = Device.query.count()
        maintenance_devices = Device.query.filter_by(status="Wartung").count()
        return render_template(
            "admin/dashboard.html",
            devices=devices,
            open_defects=open_defects,
            total_devices=total_devices,
            maintenance_devices=maintenance_devices,
        )

    @admin_bp.route("/devices", methods=["GET", "POST"])
    @admin_required
    def devices():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                device_id = request.form.get("device_id", "").strip()
                name = request.form.get("name", "").strip()
                description = request.form.get("description", "").strip()
                if not device_id or not name:
                    flash("Geräte-ID und Name sind erforderlich.", "danger")
                elif Device.query.filter_by(device_id=device_id).first():
                    flash(f"Geräte-ID '{device_id}' ist bereits vergeben.", "danger")
                else:
                    device = Device(device_id=device_id, name=name, description=description)
                    db.session.add(device)
                    db.session.commit()
                    flash(f"Gerät '{name}' wurde angelegt.", "success")
            elif action == "delete":
                dev_id = request.form.get("dev_id", type=int)
                device = db.session.get(Device, dev_id)
                if device:
                    db.session.delete(device)
                    db.session.commit()
                    flash("Gerät gelöscht.", "success")
        all_devices = Device.query.order_by(Device.name).all()
        return render_template("admin/devices.html", devices=all_devices)

    @admin_bp.route("/qr/<string:device_id>")
    @admin_required
    def generate_qr(device_id: str):
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            flash(f"Gerät '{device_id}' nicht gefunden.", "danger")
            return redirect(url_for("admin.devices"))

        report_url = f"{app.config['APP_BASE_URL']}/report/{device_id}"
        qr_img = qrcode.make(report_url)

        img_io = io.BytesIO()
        qr_img.save(img_io, format="PNG")
        img_io.seek(0)

        return send_file(
            img_io,
            mimetype="image/png",
            as_attachment=True,
            download_name=f"qr_{device_id}.png",
        )

    @admin_bp.route("/qr-page/<string:device_id>")
    @admin_required
    def qr_page(device_id: str):
        device = Device.query.filter_by(device_id=device_id).first_or_404()
        report_url = f"{app.config['APP_BASE_URL']}/report/{device_id}"
        return render_template("admin/qr_page.html", device=device, report_url=report_url)

    @admin_bp.route("/history/<string:device_id>")
    @admin_required
    def device_history(device_id: str):
        device = Device.query.filter_by(device_id=device_id).first_or_404()
        page = request.args.get("page", 1, type=int)
        pagination = (
            Defect.query.filter_by(device_id=device.id)
            .order_by(Defect.created_at.desc())
            .paginate(page=page, per_page=20, error_out=False)
        )
        return render_template(
            "admin/device_history.html", device=device, pagination=pagination
        )

    @admin_bp.route("/repair/<int:defect_id>", methods=["POST"])
    @admin_required
    def mark_repaired(defect_id: int):
        defect = db.session.get(Defect, defect_id)
        if not defect:
            abort(404)

        resolution_notes = request.form.get("resolution_notes", "").strip()
        defect.status = "Behoben"
        defect.resolved_at = datetime.now(timezone.utc)
        defect.resolution_notes = resolution_notes

        # Check if all defects for device are resolved
        device = defect.device
        open_defects = Defect.query.filter_by(
            device_id=device.id, status="Offen"
        ).count()
        if open_defects == 0:
            device.status = "Verfügbar"
            fm_client.update_device_status(device.device_id, "Verfügbar")

        db.session.commit()
        flash("Defekt als behoben markiert.", "success")
        return redirect(url_for("admin.device_history", device_id=device.device_id))

    @admin_bp.route("/users", methods=["GET", "POST"])
    @admin_required
    def users():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                username = request.form.get("username", "").strip()
                password = request.form.get("password", "")
                is_admin = request.form.get("is_admin") == "on"
                if not username or not password:
                    flash("Benutzername und Passwort sind erforderlich.", "danger")
                elif User.query.filter_by(username=username).first():
                    flash(f"Benutzername '{username}' ist bereits vergeben.", "danger")
                else:
                    user = User(username=username, is_admin=is_admin)
                    user.set_password(password)
                    db.session.add(user)
                    db.session.commit()
                    flash(f"Benutzer '{username}' wurde angelegt.", "success")
            elif action == "delete":
                user_id = request.form.get("user_id", type=int)
                user = db.session.get(User, user_id)
                if user and user.username != "admin" and user.id != current_user.id:
                    db.session.delete(user)
                    db.session.commit()
                    flash("Benutzer gelöscht.", "success")
                else:
                    flash("Dieser Benutzer kann nicht gelöscht werden.", "danger")
            elif action == "change_password":
                user_id = request.form.get("user_id", type=int)
                new_password = request.form.get("new_password", "")
                user = db.session.get(User, user_id)
                if user and new_password:
                    user.set_password(new_password)
                    db.session.commit()
                    flash(f"Passwort für '{user.username}' wurde geändert.", "success")

        all_users = User.query.order_by(User.username).all()
        return render_template("admin/users.html", users=all_users)

    @admin_bp.route("/defects")
    @admin_required
    def all_defects():
        page = request.args.get("page", 1, type=int)
        status_filter = request.args.get("status", "")
        event_filter = request.args.get("event", "").strip()

        query = Defect.query
        if status_filter:
            query = query.filter_by(status=status_filter)
        if event_filter:
            query = query.filter(
                Defect.event_name.ilike(f"%{event_filter}%")
                | Defect.project_number.ilike(f"%{event_filter}%")
            )

        pagination = query.order_by(Defect.created_at.desc()).paginate(
            page=page, per_page=30, error_out=False
        )
        return render_template(
            "admin/all_defects.html",
            pagination=pagination,
            status_filter=status_filter,
            event_filter=event_filter,
        )

    @admin_bp.route("/event-report", methods=["GET", "POST"])
    @admin_required
    def event_report():
        if request.method == "POST":
            event_name = request.form.get("event_name", "").strip()
            project_number = request.form.get("project_number", "").strip()
            recipient = request.form.get("recipient", "").strip()

            if not event_name or not project_number or not recipient:
                flash("Alle Felder sind erforderlich.", "danger")
            else:
                defects = (
                    Defect.query.filter_by(
                        event_name=event_name, project_number=project_number
                    )
                    .order_by(Defect.created_at.desc())
                    .all()
                )
                send_event_summary_report(mail, event_name, project_number, defects, recipient)
                flash(
                    f"Ereignisbericht für '{event_name}' an {recipient} gesendet ({len(defects)} Defekte).",
                    "success",
                )

        # List distinct events for convenience
        events = (
            db.session.query(Defect.event_name, Defect.project_number)
            .distinct()
            .order_by(Defect.event_name)
            .all()
        )
        return render_template("admin/event_report.html", events=events)

    # ---- Register blueprints ----
    from api import api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # ---- API docs route (Swagger UI) ----
    @app.route("/api/docs")
    def api_docs():
        return render_template("api_docs.html")

    # ---- Root route ----
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("admin.all_defects"))
        return redirect(url_for("auth.login"))

    # ---- Error handlers ----
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", title="Zugriff verweigert", message="Sie haben keine Berechtigung für diese Seite."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", title="Seite nicht gefunden", message="Die angeforderte Seite existiert nicht."), 404

    # ---- DB init + seed ----
    with app.app_context():
        db.create_all()
        _seed_db()

    return app


def _seed_db() -> None:
    """Create default admin and team_login users if they don't exist."""
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", is_admin=True)
        admin.set_password("admin123")  # Change immediately in production
        db.session.add(admin)
        logger.info("Created default admin user (password: admin123)")

    if not User.query.filter_by(username="team_login").first():
        team = User(username="team_login", is_admin=False, is_community=True)
        team.set_password("team2025")  # Change regularly
        db.session.add(team)
        logger.info("Created community user team_login (password: team2025)")

    db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
