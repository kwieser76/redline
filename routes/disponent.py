"""
Disponent blueprint – /disponent/*

Provides a read-only operations view for dispatchers (Disponenten).
Admins may also access these pages.  Regular community users are denied.
"""

import csv
import io
from datetime import date, datetime, timezone
from functools import wraps

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from models import Defect, DefectCategory, Device, DeviceCategory, db, log_audit

import logging

logger = logging.getLogger(__name__)

disponent_bp = Blueprint("disponent", __name__, url_prefix="/disponent")


# --------------------------------------------------------------------------- #
#  Auth decorator                                                               #
# --------------------------------------------------------------------------- #


def disponent_required(f):
    """Allow admins and disponnents; deny everyone else with 403."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not (current_user.is_admin or current_user.is_disponent):
            abort(403)
        return f(*args, **kwargs)

    return login_required(decorated)


# --------------------------------------------------------------------------- #
#  Internal helpers                                                             #
# --------------------------------------------------------------------------- #


def _parse_date(value: str | None, default: date) -> date:
    """Parse an ISO date string; return *default* on any failure."""
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


def _availability_query(
    from_date: date, to_date: date, category: str, device_cat_id: int | None = None
):
    """Return defects whose maintenance window overlaps [from_date, to_date].

    A defect makes a device unavailable from created_at until resolved_at
    (or indefinitely when still open).
    """
    from_dt = datetime(
        from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc
    )
    to_dt = datetime(
        to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc
    )

    query = (
        Defect.query.join(Device, Defect.device_id == Device.id)
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
    if device_cat_id:
        query = query.filter(Device.category_id == device_cat_id)

    return query.order_by(Defect.created_at.desc()).all()


# --------------------------------------------------------------------------- #
#  Routes                                                                       #
# --------------------------------------------------------------------------- #


@disponent_bp.route("/")
@disponent_required
def dashboard():
    """Main dashboard with four clickable stat tiles."""
    total = Device.query.count()
    nicht_verfuegbar = Device.query.filter(
        Device.status.in_(["Wartung", "Reserviert"])
    ).count()
    verfuegbar = Device.query.filter_by(status="Verfügbar").count()
    open_defects = Defect.query.filter_by(status="Offen").count()

    # Devices currently unavailable – shown in the quick table below tiles
    unavailable_devices = (
        Device.query.filter(Device.status.in_(["Wartung", "Reserviert"]))
        .order_by(Device.name)
        .all()
    )

    return render_template(
        "disponent/dashboard.html",
        total=total,
        nicht_verfuegbar=nicht_verfuegbar,
        verfuegbar=verfuegbar,
        open_defects=open_defects,
        unavailable_devices=unavailable_devices,
    )


@disponent_bp.route("/geraete")
@disponent_required
def devices():
    """Device list with reserve/release actions."""
    devices = Device.query.order_by(Device.name).all()
    return render_template("disponent/devices.html", devices=devices)


@disponent_bp.route("/geraet/<int:device_id>/status", methods=["POST"])
@disponent_required
def set_device_status(device_id: int):
    """Set a device status to 'Verfügbar' or 'Reserviert'.

    Devices in 'Wartung' cannot be changed here – that is handled by the
    defect-reporting and repair workflow.
    """
    device = db.session.get(Device, device_id)
    if not device:
        abort(404)

    new_status = request.form.get("status", "").strip()
    if new_status not in {"Verfügbar", "Reserviert"}:
        flash("Ungültiger Status.", "danger")
        return redirect(request.referrer or url_for("disponent.devices"))

    if device.status == "Wartung":
        flash(
            f"'{device.name}' befindet sich in Wartung und kann nicht manuell "
            "umgeschaltet werden.",
            "warning",
        )
        return redirect(request.referrer or url_for("disponent.devices"))

    old_status = device.status
    device.status = new_status
    log_audit(
        "UPDATE", "Device", device.device_id,
        old={"status": old_status},
        new={"status": new_status},
    )
    try:
        db.session.commit()
        flash(f"'{device.name}' wurde auf '{new_status}' gesetzt.", "success")
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("Failed to update device status %d: %s", device_id, exc)
        flash("Status konnte nicht gespeichert werden.", "danger")

    return redirect(request.referrer or url_for("disponent.devices"))


@disponent_bp.route("/verfuegbarkeit")
@disponent_required
def availability():
    """Date-range availability report – which devices are unavailable when."""
    today = date.today()
    from_date = _parse_date(request.args.get("from"), today)
    to_date = _parse_date(request.args.get("to"), today)

    if to_date < from_date:
        to_date = from_date

    category = request.args.get("category", "").strip()
    device_cat_id = request.args.get("device_cat", type=int)
    defects = _availability_query(from_date, to_date, category, device_cat_id)

    categories = [
        c.name
        for c in DefectCategory.query.order_by(DefectCategory.sort_order).all()
    ]
    device_categories = DeviceCategory.query.order_by(DeviceCategory.sort_order).all()

    return render_template(
        "disponent/availability.html",
        defects=defects,
        from_date=from_date,
        to_date=to_date,
        category=category,
        device_cat_id=device_cat_id,
        categories=categories,
        device_categories=device_categories,
    )


@disponent_bp.route("/verfuegbarkeit/export")
@disponent_required
def availability_export():
    """CSV export of the availability report."""
    today = date.today()
    from_date = _parse_date(request.args.get("from"), today)
    to_date = _parse_date(request.args.get("to"), today)
    if to_date < from_date:
        to_date = from_date
    category = request.args.get("category", "").strip()
    device_cat_id = request.args.get("device_cat", type=int)

    defects = _availability_query(from_date, to_date, category, device_cat_id)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "Geräte-ID",
            "Gerätename",
            "Produktkategorie",
            "Defektkategorie",
            "Grund",
            "Seit",
            "Bis",
            "Status",
            "Gemeldet von",
            "Eventname",
            "Projektnummer",
        ]
    )
    for d in defects:
        writer.writerow(
            [
                d.device.device_id,
                d.device.name,
                d.device.product_category.name if d.device.product_category else "",
                d.category,
                d.description,
                d.created_at.strftime("%d.%m.%Y %H:%M"),
                d.resolved_at.strftime("%d.%m.%Y %H:%M") if d.resolved_at else "offen",
                d.status,
                d.reporter,
                d.event_name,
                d.project_number,
            ]
        )

    filename = (
        f"verfuegbarkeit_{from_date.isoformat()}_bis_{to_date.isoformat()}.csv"
    )
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Tile filter keys → (page title, list of device statuses or None for all)
_TILE_MAP: dict[str, tuple[str, list[str] | None]] = {
    "alle": ("Alle Geräte", None),
    "nicht-verfuegbar": ("Nicht verfügbare Geräte", ["Wartung", "Reserviert"]),
    "reserviert": ("Reservierte Geräte", ["Reserviert"]),
    "verfuegbar": ("Verfügbare Geräte", ["Verfügbar"]),
}


@disponent_bp.route("/kachel/<filter_key>")
@disponent_required
def tile_detail(filter_key: str):
    """Filtered device list shown when a dashboard tile is clicked."""
    if filter_key not in _TILE_MAP:
        abort(404)

    title, status_filter = _TILE_MAP[filter_key]

    if status_filter:
        device_list = (
            Device.query.filter(Device.status.in_(status_filter))
            .order_by(Device.name)
            .all()
        )
    else:
        device_list = Device.query.order_by(Device.name).all()

    device_categories = DeviceCategory.query.order_by(DeviceCategory.sort_order).all()
    return render_template(
        "disponent/tile_detail.html",
        devices=device_list,
        title=title,
        filter_key=filter_key,
        device_categories=device_categories,
    )
