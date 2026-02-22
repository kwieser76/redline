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
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from models import Defect, DefectCategory, Device, db

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


def _availability_query(from_date: date, to_date: date, category: str):
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

    return query.order_by(Defect.created_at.desc()).all()


# --------------------------------------------------------------------------- #
#  Routes                                                                       #
# --------------------------------------------------------------------------- #


@disponent_bp.route("/")
@disponent_required
def dashboard():
    """Main dashboard with four clickable stat tiles."""
    total = Device.query.count()
    nicht_verfuegbar = Device.query.filter_by(status="Wartung").count()
    reserviert = Device.query.filter_by(status="Reserviert").count()
    verfuegbar = Device.query.filter_by(status="Verfügbar").count()

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
        reserviert=reserviert,
        verfuegbar=verfuegbar,
        unavailable_devices=unavailable_devices,
    )


@disponent_bp.route("/geraete")
@disponent_required
def devices():
    """Read-only device list ordered by name."""
    devices = Device.query.order_by(Device.name).all()
    return render_template("disponent/devices.html", devices=devices)


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
    defects = _availability_query(from_date, to_date, category)

    categories = [
        c.name
        for c in DefectCategory.query.order_by(DefectCategory.sort_order).all()
    ]

    return render_template(
        "disponent/availability.html",
        defects=defects,
        from_date=from_date,
        to_date=to_date,
        category=category,
        categories=categories,
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

    defects = _availability_query(from_date, to_date, category)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "Geräte-ID",
            "Gerätename",
            "Kategorie",
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


# Tile filter keys → (page title, device status filter or None for all)
_TILE_MAP: dict[str, tuple[str, str | None]] = {
    "alle": ("Alle Geräte", None),
    "nicht-verfuegbar": ("Nicht verfügbare Geräte", "Wartung"),
    "reserviert": ("Reservierte Geräte", "Reserviert"),
    "verfuegbar": ("Verfügbare Geräte", "Verfügbar"),
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
            Device.query.filter_by(status=status_filter).order_by(Device.name).all()
        )
    else:
        device_list = Device.query.order_by(Device.name).all()

    return render_template(
        "disponent/tile_detail.html",
        devices=device_list,
        title=title,
        filter_key=filter_key,
    )
