"""
Werkstatt blueprint – /werkstatt/*

Provides the repair-workshop view for werkstatt users and admins.
Community users and disponnents are denied.

Routes:
  GET  /werkstatt/              – dashboard: all open defects
  GET  /werkstatt/defekt/<id>   – defect detail with comments
  POST /werkstatt/defekt/<id>/status    – update werkstatt_status
  POST /werkstatt/defekt/<id>/kommentar – add comment (+ optional photo)
"""

import logging
import os
import uuid
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from models import Comment, Defect, Device, db

logger = logging.getLogger(__name__)

werkstatt_bp = Blueprint("werkstatt", __name__, url_prefix="/werkstatt")

# Valid werkstatt status transitions (ordered for UI display)
WERKSTATT_STATUSES = ["Ausstehend", "In Prüfung", "In Reparatur", "Repariert"]


# --------------------------------------------------------------------------- #
#  Auth decorator                                                               #
# --------------------------------------------------------------------------- #


def werkstatt_required(f):
    """Allow admins and werkstatt users; deny everyone else with 403."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not (current_user.is_admin or current_user.is_werkstatt):
            abort(403)
        return f(*args, **kwargs)

    return login_required(decorated)


# --------------------------------------------------------------------------- #
#  Upload helper                                                                #
# --------------------------------------------------------------------------- #


def _save_photo(file) -> str | None:
    """Validate and persist an uploaded photo file.

    Returns the stored filename (just the basename, no directory) on success,
    or None if no file was provided or the extension is not allowed.
    Raises on OS/disk errors so the caller can handle them.
    """
    if not file or not file.filename:
        return None

    parts = file.filename.rsplit(".", 1)
    if len(parts) != 2:
        return None

    ext = parts[1].lower()
    allowed = current_app.config.get("ALLOWED_PHOTO_EXTENSIONS", set())
    if ext not in allowed:
        return None

    # UUID-based filename prevents path traversal and enumeration
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    return filename


# --------------------------------------------------------------------------- #
#  Routes                                                                       #
# --------------------------------------------------------------------------- #


@werkstatt_bp.route("/")
@werkstatt_required
def dashboard():
    """Show all defects that are currently open (device in Wartung)."""
    open_defects = (
        Defect.query.filter_by(status="Offen")
        .join(Device, Defect.device_id == Device.id)
        .order_by(Defect.created_at.asc())
        .all()
    )
    return render_template(
        "werkstatt/dashboard.html",
        defects=open_defects,
        werkstatt_statuses=WERKSTATT_STATUSES,
    )


@werkstatt_bp.route("/defekt/<int:defect_id>")
@werkstatt_required
def defekt_detail(defect_id: int):
    """Defect detail page: full info, werkstatt status, and comment thread."""
    defect = db.session.get(Defect, defect_id)
    if not defect:
        abort(404)
    return render_template(
        "werkstatt/defekt_detail.html",
        defect=defect,
        werkstatt_statuses=WERKSTATT_STATUSES,
    )


@werkstatt_bp.route("/defekt/<int:defect_id>/status", methods=["POST"])
@werkstatt_required
def update_status(defect_id: int):
    """Update the werkstatt_status of a defect."""
    defect = db.session.get(Defect, defect_id)
    if not defect:
        abort(404)

    new_status = request.form.get("werkstatt_status", "").strip()
    if new_status not in WERKSTATT_STATUSES:
        flash("Ungültiger Status.", "danger")
        return redirect(url_for("werkstatt.defekt_detail", defect_id=defect_id))

    defect.werkstatt_status = new_status
    try:
        db.session.commit()
        flash(f"Status auf '{new_status}' geändert.", "success")
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("Failed to update werkstatt_status for defect %d: %s", defect_id, exc)
        flash("Status konnte nicht gespeichert werden.", "danger")

    return redirect(url_for("werkstatt.defekt_detail", defect_id=defect_id))


@werkstatt_bp.route("/defekt/<int:defect_id>/kommentar", methods=["POST"])
@werkstatt_required
def add_comment(defect_id: int):
    """Add a text comment (with optional photo) to a defect."""
    defect = db.session.get(Defect, defect_id)
    if not defect:
        abort(404)

    text = request.form.get("text", "").strip()
    if not text:
        flash("Kommentartext darf nicht leer sein.", "danger")
        return redirect(url_for("werkstatt.defekt_detail", defect_id=defect_id))

    if len(text) > 2000:
        flash("Kommentar ist zu lang (max. 2000 Zeichen).", "danger")
        return redirect(url_for("werkstatt.defekt_detail", defect_id=defect_id))

    # Handle optional photo upload
    photo_path = None
    photo_file = request.files.get("photo")
    if photo_file and photo_file.filename:
        try:
            photo_path = _save_photo(photo_file)
            if photo_path is None:
                flash(
                    "Ungültiges Dateiformat. Erlaubt: JPG, PNG, GIF, WEBP.",
                    "warning",
                )
        except OSError as exc:
            logger.error("Photo upload failed for defect %d: %s", defect_id, exc)
            flash("Foto konnte nicht gespeichert werden.", "warning")

    comment = Comment(
        defect_id=defect_id,
        username=current_user.username,
        user_role=current_user.role,
        text=text,
        photo_path=photo_path,
    )
    db.session.add(comment)
    try:
        db.session.commit()
        flash("Kommentar hinzugefügt.", "success")
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("Failed to save comment for defect %d: %s", defect_id, exc)
        flash("Kommentar konnte nicht gespeichert werden.", "danger")

    return redirect(url_for("werkstatt.defekt_detail", defect_id=defect_id))
