"""
Admin blueprint – /admin/*

All routes require is_admin=True (enforced by the admin_required decorator).
"""

import csv
import io
import logging
import re
import smtplib
import socket
from datetime import date, datetime, timezone
from functools import wraps

import qrcode
from flask import (
    Blueprint,
    Response,
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
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from models import (
    AuditLog,
    Defect,
    DefectCategory,
    Device,
    DeviceCategory,
    EmailRecipient,
    User,
    db,
    log_audit,
)
from notifications import send_event_summary_report

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _safe_commit(success_msg: str | None = None) -> bool:
    """Commit the current DB session with user-friendly error handling.

    Returns True on success, False on failure (session is rolled back and
    a flash message is shown).
    """
    try:
        db.session.commit()
        if success_msg:
            flash(success_msg, "success")
        return True
    except IntegrityError:
        db.session.rollback()
        flash(
            "Speichern fehlgeschlagen: Ein Datensatz mit diesen Werten "
            "existiert bereits.",
            "danger",
        )
        return False
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("Database commit failed: %s", exc)
        flash(
            "Speichern fehlgeschlagen: Die Datenbank hat einen Fehler gemeldet. "
            "Bitte versuchen Sie es erneut oder kontaktieren Sie den Administrator.",
            "danger",
        )
        return False


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
            category_id = request.form.get("category_id", type=int) or None
            if not device_id or not name:
                flash("Geräte-ID und Name sind erforderlich.", "danger")
            elif Device.query.filter_by(device_id=device_id).first():
                flash(f"Geräte-ID '{device_id}' ist bereits vergeben.", "danger")
            else:
                device = Device(
                    device_id=device_id,
                    name=name,
                    description=description,
                    category_id=category_id,
                )
                db.session.add(device)
                log_audit(
                    "CREATE", "Device", device_id,
                    new={"device_id": device_id, "name": name, "description": description},
                )
                _safe_commit(f"Gerät '{name}' wurde angelegt.")

        elif action == "delete":
            dev_id = request.form.get("dev_id", type=int)
            device = db.session.get(Device, dev_id)
            if device:
                log_audit(
                    "DELETE", "Device", device.device_id,
                    old={"device_id": device.device_id, "name": device.name, "status": device.status},
                )
                db.session.delete(device)
                _safe_commit("Gerät gelöscht.")

        elif action == "set_category":
            dev_id = request.form.get("dev_id", type=int)
            category_id = request.form.get("category_id", type=int) or None
            device = db.session.get(Device, dev_id)
            if device:
                device.category_id = category_id
                _safe_commit("Kategorie aktualisiert.")

    # Filters (GET params)
    status_filter = request.args.get("status", "").strip()
    cat_filter = request.args.get("cat", type=int)
    search = request.args.get("search", "").strip()

    query = Device.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if cat_filter:
        query = query.filter_by(category_id=cat_filter)
    if search:
        query = query.filter(
            Device.name.ilike(f"%{search}%") | Device.device_id.ilike(f"%{search}%")
        )

    all_devices = query.order_by(Device.name).all()
    all_categories = DeviceCategory.query.order_by(DeviceCategory.sort_order).all()
    return render_template(
        "admin/devices.html",
        devices=all_devices,
        device_categories=all_categories,
        status_filter=status_filter,
        cat_filter=cat_filter,
        search=search,
    )


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
    log_audit(
        "UPDATE", "Defect", defect.id,
        old={"status": "Offen"},
        new={"status": "Behoben", "resolution_notes": resolution_notes},
    )
    defect.status = "Behoben"
    defect.resolved_at = datetime.now(timezone.utc)
    defect.resolution_notes = resolution_notes

    # If no open defects remain, mark device as available again.
    device = defect.device
    open_defects = Defect.query.filter_by(device_id=device.id, status="Offen").count()
    if open_defects == 0:
        device.status = "Verfügbar"

    _safe_commit("Defekt als behoben markiert.")
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
            is_disponent = request.form.get("is_disponent") == "on" and not is_admin
            is_werkstatt = (
                request.form.get("is_werkstatt") == "on"
                and not is_admin
                and not is_disponent
            )
            is_api_user = (
                request.form.get("is_api_user") == "on"
                and not is_admin
                and not is_disponent
                and not is_werkstatt
            )
            if not username or not password:
                flash("Benutzername und Passwort sind erforderlich.", "danger")
            elif len(password) < 8:
                flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "danger")
            elif User.query.filter_by(username=username).first():
                flash(f"Benutzername '{username}' ist bereits vergeben.", "danger")
            else:
                user = User(
                    username=username,
                    is_admin=is_admin,
                    is_disponent=is_disponent,
                    is_werkstatt=is_werkstatt,
                    is_api_user=is_api_user,
                )
                user.set_password(password)
                db.session.add(user)
                log_audit(
                    "CREATE", "User", username,
                    new={"username": username, "role": user.role},
                )
                _safe_commit(f"Benutzer '{username}' wurde angelegt.")

        elif action == "delete":
            user_id = request.form.get("user_id", type=int)
            user = db.session.get(User, user_id)
            if user and user.username != "admin" and user.id != current_user.id:
                log_audit(
                    "DELETE", "User", user.username,
                    old={"username": user.username, "role": user.role},
                )
                db.session.delete(user)
                _safe_commit("Benutzer gelöscht.")
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
                    log_audit("UPDATE", "User", user.username,
                              new={"action": "password_changed"})
                    _safe_commit(
                        f"Passwort für '{user.username}' wurde geändert."
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
            try:
                send_event_summary_report(
                    mail, event_name, project_number, defects, recipient
                )
                flash(
                    f"Ereignisbericht für '{event_name}' an {recipient} gesendet "
                    f"({len(defects)} Defekte).",
                    "success",
                )
            except smtplib.SMTPAuthenticationError:
                flash(
                    "E-Mail-Versand fehlgeschlagen: Benutzername oder Passwort für den "
                    "E-Mail-Server ist falsch. Bitte MAIL_USERNAME und MAIL_PASSWORD "
                    "in der .env-Datei prüfen.",
                    "danger",
                )
            except (smtplib.SMTPConnectError, ConnectionRefusedError, socket.gaierror):
                flash(
                    "E-Mail-Versand fehlgeschlagen: Der E-Mail-Server ist nicht "
                    "erreichbar. Bitte MAIL_SERVER und MAIL_PORT in der .env-Datei "
                    "prüfen.",
                    "danger",
                )
            except smtplib.SMTPRecipientsRefused:
                flash(
                    "E-Mail-Versand fehlgeschlagen: Die Empfänger-Adresse wurde vom "
                    "E-Mail-Server abgelehnt. Bitte E-Mail-Adresse prüfen.",
                    "danger",
                )
            except smtplib.SMTPException as exc:
                flash(
                    f"E-Mail-Versand fehlgeschlagen: {exc}",
                    "danger",
                )
            except Exception as exc:
                current_app.logger.error("Unexpected error sending event report: %s", exc)
                flash(
                    "E-Mail-Versand fehlgeschlagen: Ein unerwarteter Fehler ist "
                    "aufgetreten. Details stehen im Server-Log.",
                    "danger",
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
            elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                flash(
                    "Bitte geben Sie eine gültige E-Mail-Adresse ein "
                    "(z.\u202fB. name@example.com).",
                    "danger",
                )
            elif EmailRecipient.query.filter_by(email=email).first():
                flash(f"E-Mail '{email}' ist bereits eingetragen.", "danger")
            else:
                rec = EmailRecipient(name=name, email=email)
                db.session.add(rec)
                _safe_commit(f"Empfänger '{name}' wurde hinzugefügt.")

        elif action == "delete":
            rec_id = request.form.get("rec_id", type=int)
            rec = db.session.get(EmailRecipient, rec_id)
            if rec:
                db.session.delete(rec)
                _safe_commit(f"Empfänger '{rec.name}' wurde gelöscht.")

        elif action == "toggle":
            rec_id = request.form.get("rec_id", type=int)
            rec = db.session.get(EmailRecipient, rec_id)
            if rec:
                rec.active = not rec.active
                state = "aktiviert" if rec.active else "deaktiviert"
                _safe_commit(f"Empfänger '{rec.name}' wurde {state}.")

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
                _safe_commit(f"Kategorie '{name}' wurde angelegt.")

        elif action == "delete":
            cat_id = request.form.get("cat_id", type=int)
            cat = db.session.get(DefectCategory, cat_id)
            if cat:
                db.session.delete(cat)
                _safe_commit(f"Kategorie '{cat.name}' wurde gelöscht.")

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
    _safe_commit()


# --------------------------------------------------------------------------- #
#  Device availability report (Disponenten)                                     #
# --------------------------------------------------------------------------- #


def _parse_date(value: str | None, default: date) -> date:
    """Parse an ISO date string, returning *default* on failure."""
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


def _availability_query(from_date: date, to_date: date, category: str):
    """Return defects that overlap [from_date, to_date].

    A defect makes a device unavailable from created_at until resolved_at
    (or until now if still open).
    """
    from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
    to_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc)

    query = (
        Defect.query
        .join(Device, Defect.device_id == Device.id)
        .filter(Defect.created_at <= to_dt)
        .filter(
            db.or_(
                Defect.resolved_at >= from_dt,
                Defect.resolved_at.is_(None),
            )
        )
    )
    if category:
        query = query.filter(Defect.category == category)

    return query.order_by(Defect.created_at.desc()).all()


@admin_bp.route("/availability")
@admin_required
def availability():
    """Disponenten-Report: welche Geräte sind in einem Zeitraum nicht verfügbar?"""
    today = date.today()
    from_date = _parse_date(request.args.get("from"), today)
    to_date = _parse_date(request.args.get("to"), today)

    if to_date < from_date:
        flash("Das Bis-Datum darf nicht vor dem Von-Datum liegen.", "danger")
        to_date = from_date

    category = request.args.get("category", "").strip()
    defects = _availability_query(from_date, to_date, category)

    categories = [
        c.name
        for c in DefectCategory.query.order_by(
            DefectCategory.sort_order, DefectCategory.name
        ).all()
    ]

    return render_template(
        "admin/availability.html",
        defects=defects,
        from_date=from_date,
        to_date=to_date,
        category=category,
        categories=categories,
    )


@admin_bp.route("/availability/export")
@admin_required
def availability_export():
    """CSV-Export der Geräteverfügbarkeits-Übersicht."""
    today = date.today()
    from_date = _parse_date(request.args.get("from"), today)
    to_date = _parse_date(request.args.get("to"), today)
    if to_date < from_date:
        to_date = from_date
    category = request.args.get("category", "").strip()

    defects = _availability_query(from_date, to_date, category)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "Geräte-ID",
        "Gerätename",
        "Kategorie",
        "Beschreibung",
        "Status",
        "Nicht verfügbar seit",
        "Verfügbar ab",
        "Event",
        "Projektnummer",
        "Gemeldet von",
    ])
    for d in defects:
        writer.writerow([
            d.device.device_id,
            d.device.name,
            d.category,
            d.description,
            "Defekt (offen)" if d.status == "Offen" else "Behoben",
            d.created_at.strftime("%d.%m.%Y %H:%M"),
            d.resolved_at.strftime("%d.%m.%Y %H:%M") if d.resolved_at else "–",
            d.event_name,
            d.project_number,
            d.reporter,
        ])

    filename = f"verfuegbarkeit_{from_date.isoformat()}_{to_date.isoformat()}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # UTF-8 BOM so Excel recognises the encoding
            "Content-Type": "text/csv; charset=utf-8-sig",
        },
    )


# --------------------------------------------------------------------------- #
#  Device categories (Produktkategorien)                                        #
# --------------------------------------------------------------------------- #


@admin_bp.route("/device-categories", methods=["GET", "POST"])
@admin_required
def device_categories():
    """CRUD for device product categories (Ton, Licht, Bühne …)."""
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            name = request.form.get("name", "").strip()
            color = request.form.get("color", "#6b7280").strip()
            if not name:
                flash("Kategorienname ist erforderlich.", "danger")
            elif DeviceCategory.query.filter_by(name=name).first():
                flash(f"Kategorie '{name}' existiert bereits.", "danger")
            else:
                max_order = db.session.query(
                    db.func.max(DeviceCategory.sort_order)
                ).scalar() or 0
                cat = DeviceCategory(name=name, color=color, sort_order=max_order + 1)
                db.session.add(cat)
                _safe_commit(f"Kategorie '{name}' wurde angelegt.")

        elif action == "delete":
            cat_id = request.form.get("cat_id", type=int)
            cat = db.session.get(DeviceCategory, cat_id)
            if cat:
                # Unlink devices before deleting
                Device.query.filter_by(category_id=cat_id).update(
                    {"category_id": None}
                )
                db.session.delete(cat)
                _safe_commit(f"Kategorie '{cat.name}' wurde gelöscht.")

        elif action == "edit":
            cat_id = request.form.get("cat_id", type=int)
            cat = db.session.get(DeviceCategory, cat_id)
            if cat:
                new_name = request.form.get("name", "").strip()
                new_color = request.form.get("color", cat.color).strip()
                if not new_name:
                    flash("Kategorienname darf nicht leer sein.", "danger")
                elif new_name != cat.name and DeviceCategory.query.filter_by(name=new_name).first():
                    flash(f"Kategorie '{new_name}' existiert bereits.", "danger")
                else:
                    cat.name = new_name
                    cat.color = new_color
                    _safe_commit(f"Kategorie aktualisiert.")

    cats = DeviceCategory.query.order_by(DeviceCategory.sort_order).all()
    return render_template("admin/device_categories.html", categories=cats)


# --------------------------------------------------------------------------- #
#  Admin dashboard tile detail (klickbare Kacheln)                              #
# --------------------------------------------------------------------------- #

_ADMIN_TILE_MAP: dict[str, tuple[str, str | None]] = {
    "alle":       ("Alle Geräte",         None),
    "wartung":    ("Geräte in Wartung",   "Wartung"),
    "verfuegbar": ("Verfügbare Geräte",   "Verfügbar"),
    "reserviert": ("Reservierte Geräte",  "Reserviert"),
}


@admin_bp.route("/kachel/<filter_key>")
@admin_required
def admin_kachel(filter_key: str):
    """Filtered device list behind a dashboard stat tile."""
    if filter_key not in _ADMIN_TILE_MAP:
        abort(404)

    title, status_filter = _ADMIN_TILE_MAP[filter_key]

    search = request.args.get("search", "").strip()
    cat_filter = request.args.get("cat", type=int)

    query = Device.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if search:
        query = query.filter(
            Device.name.ilike(f"%{search}%") | Device.device_id.ilike(f"%{search}%")
        )
    if cat_filter:
        query = query.filter_by(category_id=cat_filter)

    device_list = query.order_by(Device.name).all()
    device_categories = DeviceCategory.query.order_by(DeviceCategory.sort_order).all()

    return render_template(
        "admin/kachel_detail.html",
        devices=device_list,
        title=title,
        filter_key=filter_key,
        search=search,
        cat_filter=cat_filter,
        device_categories=device_categories,
    )


# --------------------------------------------------------------------------- #
#  NFR-SEC-003 – Audit log viewer                                               #
# --------------------------------------------------------------------------- #


@admin_bp.route("/audit")
@admin_required
def audit_log():
    """Paginated view of the security audit trail."""
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", "").strip()
    entity_filter = request.args.get("entity", "").strip()

    query = AuditLog.query.order_by(AuditLog.timestamp.desc())
    if action_filter:
        query = query.filter_by(action=action_filter)
    if entity_filter:
        query = query.filter_by(entity_type=entity_filter)

    pagination = query.paginate(page=page, per_page=50, error_out=False)

    # Distinct entity types for the filter dropdown
    entity_types = [
        r[0]
        for r in db.session.query(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)
    ]

    return render_template(
        "admin/audit.html",
        pagination=pagination,
        action_filter=action_filter,
        entity_filter=entity_filter,
        entity_types=entity_types,
    )


# --------------------------------------------------------------------------- #
#  Help page                                                                    #
# --------------------------------------------------------------------------- #


@admin_bp.route("/help")
@login_required
def help_page():
    return render_template("admin/help.html")
