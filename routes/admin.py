"""
Admin blueprint – /admin/*

All routes require is_admin=True (enforced by the admin_required decorator).
"""

import io
from datetime import datetime, timezone
from functools import wraps

import qrcode
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from flask_mail import Mail

from models import Defect, DefectCategory, Device, EmailRecipient, User, db
from notifications import send_event_summary_report

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# --------------------------------------------------------------------------- #
#  Auth decorator                                                               #
# --------------------------------------------------------------------------- #


def admin_required(f):
    """Decorator: authenticated admin users only."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return login_required(decorated)


# --------------------------------------------------------------------------- #
#  Dashboard                                                                    #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
#  Device management                                                            #
# --------------------------------------------------------------------------- #


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
                device = Device(
                    device_id=device_id, name=name, description=description
                )
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

    report_url = f"{current_app.config['APP_BASE_URL']}/report/{device_id}"
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
    report_url = f"{current_app.config['APP_BASE_URL']}/report/{device_id}"
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

    # If no open defects remain, mark device as available again.
    device = defect.device
    open_defects = Defect.query.filter_by(device_id=device.id, status="Offen").count()
    if open_defects == 0:
        device.status = "Verfügbar"

    db.session.commit()
    flash("Defekt als behoben markiert.", "success")
    return redirect(url_for("admin.device_history", device_id=device.device_id))


# --------------------------------------------------------------------------- #
#  User management                                                              #
# --------------------------------------------------------------------------- #


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
            elif len(password) < 8:
                flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "danger")
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
                if len(new_password) < 8:
                    flash(
                        "Das neue Passwort muss mindestens 8 Zeichen lang sein.",
                        "danger",
                    )
                else:
                    user.set_password(new_password)
                    db.session.commit()
                    flash(
                        f"Passwort für '{user.username}' wurde geändert.", "success"
                    )

    all_users = User.query.order_by(User.username).all()
    return render_template("admin/users.html", users=all_users)


# --------------------------------------------------------------------------- #
#  Defect views                                                                 #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
#  Event reports                                                                #
# --------------------------------------------------------------------------- #


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
            mail: Mail = current_app.extensions["mail"]
            send_event_summary_report(
                mail, event_name, project_number, defects, recipient
            )
            flash(
                f"Ereignisbericht für '{event_name}' an {recipient} gesendet "
                f"({len(defects)} Defekte).",
                "success",
            )

    events = (
        db.session.query(Defect.event_name, Defect.project_number)
        .distinct()
        .order_by(Defect.event_name)
        .all()
    )
    return render_template("admin/event_report.html", events=events)


# --------------------------------------------------------------------------- #
#  Email recipients                                                             #
# --------------------------------------------------------------------------- #


@admin_bp.route("/recipients", methods=["GET", "POST"])
@admin_required
def recipients():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            if not name or not email:
                flash("Name und E-Mail-Adresse sind erforderlich.", "danger")
            elif EmailRecipient.query.filter_by(email=email).first():
                flash(f"E-Mail '{email}' ist bereits eingetragen.", "danger")
            else:
                rec = EmailRecipient(name=name, email=email)
                db.session.add(rec)
                db.session.commit()
                flash(f"Empfänger '{name}' wurde hinzugefügt.", "success")

        elif action == "delete":
            rec_id = request.form.get("rec_id", type=int)
            rec = db.session.get(EmailRecipient, rec_id)
            if rec:
                db.session.delete(rec)
                db.session.commit()
                flash(f"Empfänger '{rec.name}' wurde gelöscht.", "success")

        elif action == "toggle":
            rec_id = request.form.get("rec_id", type=int)
            rec = db.session.get(EmailRecipient, rec_id)
            if rec:
                rec.active = not rec.active
                db.session.commit()
                state = "aktiviert" if rec.active else "deaktiviert"
                flash(f"Empfänger '{rec.name}' wurde {state}.", "success")

    all_recipients = EmailRecipient.query.order_by(EmailRecipient.name).all()
    return render_template("admin/recipients.html", recipients=all_recipients)


# --------------------------------------------------------------------------- #
#  Defect categories                                                            #
# --------------------------------------------------------------------------- #


@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name ist erforderlich.", "danger")
            elif DefectCategory.query.filter_by(name=name).first():
                flash(f"Kategorie '{name}' existiert bereits.", "danger")
            else:
                max_order = (
                    db.session.query(db.func.max(DefectCategory.sort_order)).scalar()
                    or 0
                )
                cat = DefectCategory(name=name, sort_order=max_order + 1)
                db.session.add(cat)
                db.session.commit()
                flash(f"Kategorie '{name}' wurde angelegt.", "success")

        elif action == "delete":
            cat_id = request.form.get("cat_id", type=int)
            cat = db.session.get(DefectCategory, cat_id)
            if cat:
                db.session.delete(cat)
                db.session.commit()
                flash(f"Kategorie '{cat.name}' wurde gelöscht.", "success")

        elif action == "move_up":
            _move_category(request.form.get("cat_id", type=int), direction="up")

        elif action == "move_down":
            _move_category(request.form.get("cat_id", type=int), direction="down")

    all_cats = DefectCategory.query.order_by(
        DefectCategory.sort_order, DefectCategory.name
    ).all()
    return render_template("admin/categories.html", categories=all_cats)


def _move_category(cat_id: int, direction: str) -> None:
    cats = DefectCategory.query.order_by(
        DefectCategory.sort_order, DefectCategory.name
    ).all()
    idx = next((i for i, c in enumerate(cats) if c.id == cat_id), None)
    if idx is None:
        return
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(cats):
        return
    cats[idx].sort_order, cats[swap_idx].sort_order = (
        cats[swap_idx].sort_order,
        cats[idx].sort_order,
    )
    db.session.commit()


# --------------------------------------------------------------------------- #
#  Help page                                                                    #
# --------------------------------------------------------------------------- #


@admin_bp.route("/help")
@login_required
def help_page():
    return render_template("admin/help.html")
