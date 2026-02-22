"""
Defect-reporting blueprint – /report/*

Mobile-first flow:
  GET  /report/<device_id>          – display the defect form
  POST /report/<device_id>          – submit a defect (+ optional photo)
  GET  /report/<device_id>/success  – confirmation page with mailto: link
"""

import logging
import os
import urllib.parse
import uuid

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from models import Comment, Defect, DefectCategory, Device, EmailRecipient, db

logger = logging.getLogger(__name__)

report_bp = Blueprint("report", __name__, url_prefix="/report")


def _save_photo(file) -> str | None:
    """Validate and persist an uploaded photo. Returns filename or None."""
    if not file or not file.filename:
        return None
    parts = file.filename.rsplit(".", 1)
    if len(parts) != 2:
        return None
    ext = parts[1].lower()
    if ext not in current_app.config.get("ALLOWED_PHOTO_EXTENSIONS", set()):
        return None
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    return filename


@report_bp.route("/<string:device_id>", methods=["GET", "POST"])
@login_required
def defect_form(device_id: str):
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return (
            render_template(
                "error.html",
                title="Gerät nicht gefunden",
                message=(
                    f"Das Gerät mit der ID '{device_id}' ist im System nicht registriert."
                ),
            ),
            404,
        )

    categories = [
        c.name
        for c in DefectCategory.query.order_by(
            DefectCategory.sort_order, DefectCategory.name
        ).all()
    ]

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

        defect = Defect(
            device_id=device.id,
            category=category,
            description=description,
            event_name=event_name,
            project_number=project_number,
            reporter=current_user.username,
        )
        db.session.add(defect)
        device.status = "Wartung"

        try:
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Failed to save defect report: %s", exc)
            flash(
                "Die Defektmeldung konnte nicht gespeichert werden. "
                "Bitte versuchen Sie es erneut.",
                "danger",
            )
            return render_template(
                "report_defect.html",
                device=device,
                categories=categories,
                form_data=request.form,
            )

        # Optional: save photo and attach it as the first comment on the defect
        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename:
            try:
                photo_path = _save_photo(photo_file)
                if photo_path:
                    initial_comment = Comment(
                        defect_id=defect.id,
                        username=current_user.username,
                        user_role=current_user.role,
                        text="Foto bei Defektmeldung",
                        photo_path=photo_path,
                    )
                    db.session.add(initial_comment)
                    db.session.commit()
                else:
                    flash(
                        "Foto-Format nicht unterstützt (erlaubt: JPG, PNG, GIF, WEBP).",
                        "warning",
                    )
            except (OSError, SQLAlchemyError) as exc:
                logger.warning("Could not save initial photo for defect %d: %s", defect.id, exc)
                db.session.rollback()
                # Photo loss is non-fatal; defect was already saved

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

    # Latest defect for this device (the one just submitted)
    defect = (
        Defect.query.filter_by(device_id=device.id)
        .order_by(Defect.created_at.desc())
        .first()
    )

    # Build a mailto: URL addressed to all active recipients
    recipients = EmailRecipient.query.filter_by(active=True).all()
    mailto_url = None
    if defect and recipients:
        to = ",".join(r.email for r in recipients)
        ts = defect.created_at.strftime("%d.%m.%Y %H:%M")
        subject = f"Defekt gemeldet: {device.name} – {defect.category}"
        body = (
            f"DEFEKTMELDUNG\n"
            f"=============\n\n"
            f"Gerät:        {device.name} ({device.device_id})\n"
            f"Kategorie:    {defect.category}\n"
            f"Event:        {defect.event_name}\n"
            f"Projektnr.:   {defect.project_number}\n"
            f"Gemeldet von: {defect.reporter}\n"
            f"Datum:        {ts}\n\n"
            f"Beschreibung:\n{defect.description}\n\n"
            f"---\n"
            f"Gemeldet über das Redline Defektmeldesystem"
        )
        params = urllib.parse.urlencode(
            {"subject": subject, "body": body},
            quote_via=urllib.parse.quote,
        )
        mailto_url = f"mailto:{to}?{params}"

    return render_template(
        "defect_success.html",
        device=device,
        defect=defect,
        mailto_url=mailto_url,
        recipients=recipients,
    )
