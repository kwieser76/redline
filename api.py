"""
Redline REST JSON API – v1

Base path : /api/v1
Auth      : HTTP Basic Auth  –  requires a dedicated api_user account.
            Web-UI roles (admin, disponent, werkstatt) cannot use the API.
Format    : application/json

Endpoints
---------
GET    /api/v1/devices                     List devices
POST   /api/v1/devices                     Create device          [admin]
GET    /api/v1/devices/<device_id>         Get device
PATCH  /api/v1/devices/<device_id>         Update device          [admin]
DELETE /api/v1/devices/<device_id>         Delete device          [admin]
GET    /api/v1/devices/<device_id>/qr      QR-code PNG            [admin]

GET    /api/v1/defects                     List defects (filterable)
POST   /api/v1/defects                     Report a defect
GET    /api/v1/defects/<id>                Get defect
PATCH  /api/v1/defects/<id>/resolve        Mark defect resolved   [admin]

GET    /api/v1/events                      List distinct events
GET    /api/v1/events/<project_number>     Defects for one event
"""

import functools
import io
import logging
from datetime import datetime, timezone

import qrcode
from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from models import Defect, Device, User, db

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# --------------------------------------------------------------------------- #
#  Helpers                                                                      #
# --------------------------------------------------------------------------- #

_WWW_AUTH = 'Basic realm="Redline API"'


def _json_error(message: str, status: int):
    resp = jsonify({"error": message})
    if status == 401:
        resp.headers["WWW-Authenticate"] = _WWW_AUTH
    return resp, status


def _require_auth(admin_only: bool = False):
    """Decorator factory – enforces HTTP Basic Auth.

    Only users with ``is_api_user=True`` may authenticate.  All api_users
    have full access to every endpoint; the *admin_only* parameter is kept
    for documentation purposes only.
    """

    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            auth = request.authorization
            if not auth:
                return _json_error("Authentication required.", 401)
            user = User.query.filter_by(username=auth.username).first()
            if not user or not user.check_password(auth.password):
                return _json_error("Invalid credentials.", 401)
            if not user.is_api_user:
                return _json_error(
                    "API access requires a dedicated api_user account. "
                    "Web-UI accounts (admin, disponent, werkstatt) cannot "
                    "authenticate to the API.",
                    403,
                )
            g.api_user = user
            return f(*args, **kwargs)

        return wrapped

    return decorator


def _device_to_dict(device: Device) -> dict:
    return {
        "device_id": device.device_id,
        "name": device.name,
        "description": device.description,
        "status": device.status,
        "open_defect_count": device.open_defect_count,
        "created_at": device.created_at.isoformat(),
    }


def _defect_to_dict(defect: Defect) -> dict:
    return {
        "id": defect.id,
        "device_id": defect.device.device_id,
        "device_name": defect.device.name,
        "category": defect.category,
        "description": defect.description,
        "event_name": defect.event_name,
        "project_number": defect.project_number,
        "status": defect.status,
        "reporter": defect.reporter,
        "created_at": defect.created_at.isoformat(),
        "resolved_at": defect.resolved_at.isoformat() if defect.resolved_at else None,
        "resolution_notes": defect.resolution_notes,
    }


# --------------------------------------------------------------------------- #
#  Device endpoints                                                             #
# --------------------------------------------------------------------------- #


@api_bp.route("/devices", methods=["GET"])
@_require_auth()
def list_devices():
    """List all devices, optionally filtered by status."""
    status = request.args.get("status")
    query = Device.query
    if status:
        query = query.filter_by(status=status)
    devices = query.order_by(Device.name).all()
    return jsonify([_device_to_dict(d) for d in devices])


@api_bp.route("/devices", methods=["POST"])
@_require_auth(admin_only=True)
def create_device():
    """Create a new device. Requires admin."""
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()

    if not device_id or not name:
        return _json_error("'device_id' and 'name' are required.", 400)
    if Device.query.filter_by(device_id=device_id).first():
        return _json_error(f"device_id '{device_id}' already exists.", 409)

    device = Device(device_id=device_id, name=name, description=description)
    db.session.add(device)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _json_error(f"device_id '{device_id}' already exists.", 409)
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("DB error creating device: %s", exc)
        return _json_error("Database error – could not create device.", 500)
    return jsonify(_device_to_dict(device)), 201


@api_bp.route("/devices/<string:device_id>", methods=["GET"])
@_require_auth()
def get_device(device_id: str):
    """Get a single device by its device_id."""
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return _json_error(f"Device '{device_id}' not found.", 404)
    return jsonify(_device_to_dict(device))


@api_bp.route("/devices/<string:device_id>", methods=["PATCH"])
@_require_auth(admin_only=True)
def update_device(device_id: str):
    """Update device name, description, or status. Requires admin."""
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return _json_error(f"Device '{device_id}' not found.", 404)

    data = request.get_json(silent=True) or {}
    allowed_statuses = {"Verfügbar", "Wartung", "Reserviert"}

    if "name" in data:
        device.name = str(data["name"]).strip() or device.name
    if "description" in data:
        device.description = str(data["description"]).strip()
    if "status" in data:
        if data["status"] not in allowed_statuses:
            return _json_error(
                f"'status' must be one of: {sorted(allowed_statuses)}", 400
            )
        device.status = data["status"]

    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("DB error updating device %s: %s", device_id, exc)
        return _json_error("Database error – could not update device.", 500)
    return jsonify(_device_to_dict(device))


@api_bp.route("/devices/<string:device_id>", methods=["DELETE"])
@_require_auth(admin_only=True)
def delete_device(device_id: str):
    """Delete a device and all its defects (cascade). Requires admin."""
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return _json_error(f"Device '{device_id}' not found.", 404)
    db.session.delete(device)
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("DB error deleting device %s: %s", device_id, exc)
        return _json_error("Database error – could not delete device.", 500)
    return "", 204


@api_bp.route("/devices/<string:device_id>/qr", methods=["GET"])
@_require_auth(admin_only=True)
def device_qr(device_id: str):
    """Return the QR-code PNG for a device. Requires admin."""
    from flask import current_app

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return _json_error(f"Device '{device_id}' not found.", 404)

    report_url = f"{current_app.config['APP_BASE_URL']}/report/{device_id}"
    img = qrcode.make(report_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name=f"qr_{device_id}.png")


# --------------------------------------------------------------------------- #
#  Defect endpoints                                                             #
# --------------------------------------------------------------------------- #


@api_bp.route("/defects", methods=["GET"])
@_require_auth()
def list_defects():
    """
    List defects.  Optional query filters:
      status         – "Offen" | "Behoben"
      device_id      – device_id string
      event_name     – partial match
      project_number – partial match
      page           – page number (default 1)
      per_page       – results per page (default 50, max 200)
    """
    status = request.args.get("status")
    device_id_filter = request.args.get("device_id")
    event_name = request.args.get("event_name")
    project_number = request.args.get("project_number")
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)

    query = Defect.query
    if status:
        query = query.filter_by(status=status)
    if device_id_filter:
        device = Device.query.filter_by(device_id=device_id_filter).first()
        if device:
            query = query.filter_by(device_id=device.id)
        else:
            return jsonify(
                {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "per_page": per_page,
                    "pages": 0,
                }
            )
    if event_name:
        query = query.filter(Defect.event_name.ilike(f"%{event_name}%"))
    if project_number:
        query = query.filter(Defect.project_number.ilike(f"%{project_number}%"))

    pagination = query.order_by(Defect.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify(
        {
            "items": [_defect_to_dict(d) for d in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "per_page": per_page,
            "pages": pagination.pages,
        }
    )


@api_bp.route("/defects", methods=["POST"])
@_require_auth()
def create_defect():
    """
    Report a new defect for a device.
    Sets the device status to 'Wartung', syncs to FileMaker,
    and sends an email notification to the workshop.
    """
    from flask import current_app
    from notifications import send_defect_notification

    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "")).strip()
    category = str(data.get("category", "")).strip()
    description = str(data.get("description", "")).strip()
    event_name = str(data.get("event_name", "")).strip()
    project_number = str(data.get("project_number", "")).strip()

    errors: dict = {}
    if not device_id:
        errors["device_id"] = "Required."
    if not category:
        errors["category"] = "Required."
    elif category not in current_app.config["DEFECT_CATEGORIES"]:
        errors["category"] = f"Must be one of: {current_app.config['DEFECT_CATEGORIES']}"
    if not description:
        errors["description"] = "Required."
    if not event_name:
        errors["event_name"] = "Required."
    if not project_number:
        errors["project_number"] = "Required."
    if errors:
        return jsonify({"error": "Validation failed.", "fields": errors}), 400

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return _json_error(f"Device '{device_id}' not found.", 404)

    defect = Defect(
        device_id=device.id,
        category=category,
        description=description,
        event_name=event_name,
        project_number=project_number,
        reporter=g.api_user.username,
    )
    db.session.add(defect)
    device.status = "Wartung"
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("DB error creating defect: %s", exc)
        return _json_error("Database error – could not save defect.", 500)

    # FileMaker sync (non-blocking – errors are logged, not raised)
    from filemaker import fm_client

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
            "Gemeldet_Von": g.api_user.username,
        }
    )

    # Email notification
    mail = current_app.extensions.get("mail")
    if mail:
        send_defect_notification(
            mail, defect, device.name, current_app.config["WORKSHOP_EMAIL"]
        )

    return jsonify(_defect_to_dict(defect)), 201


@api_bp.route("/defects/<int:defect_id>", methods=["GET"])
@_require_auth()
def get_defect(defect_id: int):
    """Get a single defect by ID."""
    defect = db.session.get(Defect, defect_id)
    if not defect:
        return _json_error(f"Defect {defect_id} not found.", 404)
    return jsonify(_defect_to_dict(defect))


@api_bp.route("/defects/<int:defect_id>/resolve", methods=["PATCH"])
@_require_auth(admin_only=True)
def resolve_defect(defect_id: int):
    """
    Mark a defect as resolved.
    If no open defects remain for the device, its status returns to 'Verfügbar'.
    Requires admin.
    """
    defect = db.session.get(Defect, defect_id)
    if not defect:
        return _json_error(f"Defect {defect_id} not found.", 404)
    if defect.status == "Behoben":
        return _json_error("Defect is already resolved.", 409)

    data = request.get_json(silent=True) or {}
    defect.resolution_notes = str(data.get("resolution_notes", "")).strip()
    defect.status = "Behoben"
    defect.resolved_at = datetime.now(timezone.utc)

    device = defect.device
    # autoflush ensures the status change above is visible to this count query
    open_count = Defect.query.filter_by(device_id=device.id, status="Offen").count()
    if open_count == 0:
        device.status = "Verfügbar"
        from filemaker import fm_client

        fm_client.update_device_status(device.device_id, "Verfügbar")

    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("DB error resolving defect %d: %s", defect_id, exc)
        return _json_error("Database error – could not resolve defect.", 500)
    return jsonify(_defect_to_dict(defect))


# --------------------------------------------------------------------------- #
#  Event endpoints                                                              #
# --------------------------------------------------------------------------- #


@api_bp.route("/events", methods=["GET"])
@_require_auth()
def list_events():
    """Return all distinct (event_name, project_number) pairs."""
    rows = (
        db.session.query(Defect.event_name, Defect.project_number)
        .distinct()
        .order_by(Defect.event_name)
        .all()
    )
    return jsonify(
        [{"event_name": r.event_name, "project_number": r.project_number} for r in rows]
    )


@api_bp.route("/events/<string:project_number>", methods=["GET"])
@_require_auth()
def get_event_defects(project_number: str):
    """
    Return all defects for a given project_number.
    Optionally filter further with ?event_name=...
    """
    event_name = request.args.get("event_name")
    query = Defect.query.filter_by(project_number=project_number)
    if event_name:
        query = query.filter_by(event_name=event_name)
    defects = query.order_by(Defect.created_at.desc()).all()
    if not defects:
        return _json_error(f"No defects found for project '{project_number}'.", 404)
    return jsonify(
        {
            "project_number": project_number,
            "event_name": defects[0].event_name,
            "defect_count": len(defects),
            "defects": [_defect_to_dict(d) for d in defects],
        }
    )
