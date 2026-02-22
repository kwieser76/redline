"""
Unit tests for email notification helpers.
Flask-Mail's Message class requires an application context, so all calls
are wrapped in app.app_context(). The `mail` object itself is mocked –
no real SMTP connection needed.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from notifications import send_defect_notification, send_event_summary_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(device_id="CAM-001", name="Kamera Alpha"):
    device = MagicMock()
    device.device_id = device_id
    device.name = name
    return device


def _make_defect(
    status="Offen",
    resolved_at=None,
    device=None,
    category="Mechanischer Schaden",
    description="Gehäuse gerissen",
):
    if device is None:
        device = _make_device()
    defect = MagicMock()
    defect.id = 42
    defect.device = device
    defect.category = category
    defect.description = description
    defect.event_name = "Sommerfestival"
    defect.project_number = "PRJ-2025-001"
    defect.reporter = "team_login"
    defect.status = status
    defect.created_at = datetime(2025, 6, 15, 14, 30, tzinfo=timezone.utc)
    defect.resolved_at = resolved_at
    return defect


# ---------------------------------------------------------------------------
# send_defect_notification
# ---------------------------------------------------------------------------

class TestSendDefectNotification:
    def test_mail_send_is_called_once(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        mail.send.assert_called_once()

    def test_subject_contains_device_name(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "Kamera Alpha" in msg.subject

    def test_subject_contains_device_id(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "CAM-001" in msg.subject

    def test_recipient_is_workshop_email(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "werkstatt@test.com" in msg.recipients

    def test_body_contains_category(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "Mechanischer Schaden" in msg.body

    def test_body_contains_description(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "Gehäuse gerissen" in msg.body

    def test_body_contains_event_and_project(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "Sommerfestival" in msg.body
        assert "PRJ-2025-001" in msg.body

    def test_body_contains_reporter(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "team_login" in msg.body

    def test_body_contains_formatted_date(self, app):
        mail = MagicMock()
        with app.app_context():
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")
        msg = mail.send.call_args[0][0]
        assert "15.06.2025" in msg.body

    def test_mail_exception_does_not_propagate(self, app):
        mail = MagicMock()
        mail.send.side_effect = Exception("SMTP connection refused")
        with app.app_context():
            # Must not raise
            send_defect_notification(mail, _make_defect(), "Kamera Alpha", "werkstatt@test.com")


# ---------------------------------------------------------------------------
# send_event_summary_report
# ---------------------------------------------------------------------------

class TestSendEventSummaryReport:
    def test_mail_send_called_with_defects(self, app):
        mail = MagicMock()
        with app.app_context():
            send_event_summary_report(
                mail, "Sommerfestival", "PRJ-2025-001", [_make_defect()], "chef@test.com"
            )
        mail.send.assert_called_once()

    def test_subject_contains_event_name(self, app):
        mail = MagicMock()
        with app.app_context():
            send_event_summary_report(
                mail, "Sommerfestival", "PRJ-2025-001", [_make_defect()], "chef@test.com"
            )
        msg = mail.send.call_args[0][0]
        assert "Sommerfestival" in msg.subject

    def test_subject_contains_project_number(self, app):
        mail = MagicMock()
        with app.app_context():
            send_event_summary_report(
                mail, "Sommerfestival", "PRJ-2025-001", [_make_defect()], "chef@test.com"
            )
        msg = mail.send.call_args[0][0]
        assert "PRJ-2025-001" in msg.subject

    def test_recipient_correct(self, app):
        mail = MagicMock()
        with app.app_context():
            send_event_summary_report(
                mail, "Sommerfestival", "PRJ-2025-001", [_make_defect()], "chef@test.com"
            )
        msg = mail.send.call_args[0][0]
        assert "chef@test.com" in msg.recipients

    def test_body_contains_defect_details(self, app):
        mail = MagicMock()
        with app.app_context():
            send_event_summary_report(
                mail, "Sommerfestival", "PRJ-2025-001", [_make_defect()], "chef@test.com"
            )
        msg = mail.send.call_args[0][0]
        assert "Mechanischer Schaden" in msg.body
        assert "Gehäuse gerissen" in msg.body

    def test_body_contains_defect_count(self, app):
        mail = MagicMock()
        with app.app_context():
            send_event_summary_report(
                mail, "Event", "PRJ-001", [_make_defect(), _make_defect()], "chef@test.com"
            )
        msg = mail.send.call_args[0][0]
        assert "2" in msg.body

    def test_empty_defects_sends_no_defects_message(self, app):
        mail = MagicMock()
        with app.app_context():
            send_event_summary_report(mail, "Leeres Event", "PRJ-EMPTY", [], "chef@test.com")
        mail.send.assert_called_once()
        msg = mail.send.call_args[0][0]
        assert "Keine Defekte" in msg.body

    def test_resolved_defect_shows_resolved_date(self, app):
        mail = MagicMock()
        resolved_at = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)
        defect = _make_defect(status="Behoben", resolved_at=resolved_at)
        with app.app_context():
            send_event_summary_report(mail, "Event", "PRJ-001", [defect], "chef@test.com")
        msg = mail.send.call_args[0][0]
        assert "16.06.2025" in msg.body

    def test_resolved_defect_shows_behoben_status(self, app):
        mail = MagicMock()
        resolved_at = datetime(2025, 6, 16, 10, 0, tzinfo=timezone.utc)
        defect = _make_defect(status="Behoben", resolved_at=resolved_at)
        with app.app_context():
            send_event_summary_report(mail, "Event", "PRJ-001", [defect], "chef@test.com")
        msg = mail.send.call_args[0][0]
        assert "Behoben" in msg.body

    def test_mail_exception_propagates_to_caller(self, app):
        """Exceptions must propagate so the view can show a user-facing error."""
        mail = MagicMock()
        mail.send.side_effect = Exception("Server unreachable")
        with app.app_context():
            import pytest as _pytest
            with _pytest.raises(Exception, match="Server unreachable"):
                send_event_summary_report(
                    mail, "Event", "PRJ-001", [_make_defect()], "chef@test.com"
                )
