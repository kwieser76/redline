"""
Email notification helpers for the Redline defect reporting system.
"""
import logging
from typing import TYPE_CHECKING

from flask_mail import Message

if TYPE_CHECKING:
    from models import Defect

logger = logging.getLogger(__name__)


def send_defect_notification(mail, defect: "Defect", device_name: str, workshop_email: str) -> None:
    """Send an immediate defect notification to the workshop manager."""
    try:
        subject = f"Defekt gemeldet: {device_name} (Gerät-ID: {defect.device.device_id})"
        body = (
            f"Ein neuer Defekt wurde gemeldet.\n\n"
            f"Gerät:          {device_name}\n"
            f"Geräte-ID:      {defect.device.device_id}\n"
            f"Kategorie:      {defect.category}\n"
            f"Beschreibung:   {defect.description}\n"
            f"Event:          {defect.event_name}\n"
            f"Projektnummer:  {defect.project_number}\n"
            f"Gemeldet am:    {defect.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"Gemeldet von:   {defect.reporter}\n\n"
            f"Das Gerät wurde auf 'Wartung' gesetzt und steht nicht zur Vermietung zur Verfügung.\n"
        )
        msg = Message(subject=subject, recipients=[workshop_email], body=body)
        mail.send(msg)
        logger.info("Defect notification sent to %s for defect #%s", workshop_email, defect.id)
    except Exception as exc:
        logger.error("Failed to send defect notification: %s", exc)


def send_event_summary_report(mail, event_name: str, project_number: str, defects: list, recipient: str) -> None:
    """Send a post-event summary report with all defects for that event."""
    try:
        subject = f"Ereignisbericht: {event_name} (Projekt: {project_number})"
        if not defects:
            body = (
                f"Ereignisbericht für: {event_name} (Projektnummer: {project_number})\n\n"
                f"Keine Defekte für dieses Event gemeldet.\n"
            )
        else:
            lines = [
                f"Ereignisbericht für: {event_name} (Projektnummer: {project_number})",
                f"Anzahl der Defekte: {len(defects)}",
                "",
                "=" * 60,
            ]
            for i, defect in enumerate(defects, start=1):
                lines += [
                    f"\nDefekt #{i}",
                    f"  Gerät:         {defect.device.name} ({defect.device.device_id})",
                    f"  Kategorie:     {defect.category}",
                    f"  Beschreibung:  {defect.description}",
                    f"  Status:        {defect.status}",
                    f"  Gemeldet am:   {defect.created_at.strftime('%d.%m.%Y %H:%M')}",
                ]
                if defect.resolved_at:
                    lines.append(
                        f"  Behoben am:    {defect.resolved_at.strftime('%d.%m.%Y %H:%M')}"
                    )
                lines.append("-" * 60)
            body = "\n".join(lines)

        msg = Message(subject=subject, recipients=[recipient], body=body)
        mail.send(msg)
        logger.info("Event summary sent to %s for event '%s'", recipient, event_name)
    except Exception as exc:
        logger.error("Failed to send event summary report: %s", exc)
