"""
Tests for defect report routes:
  GET/POST /report/<device_id>
  GET      /report/<device_id>/success
"""
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from models import Defect, Device


class TestDefectForm:
    def test_form_requires_login(self, client, device):
        resp = client.get(f"/report/{device['device_id']}", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_form_renders_for_valid_device(self, admin_client, device):
        resp = admin_client.get(f"/report/{device['device_id']}")
        assert resp.status_code == 200
        assert device["name"].encode() in resp.data

    def test_form_contains_category_dropdown(self, admin_client, device):
        resp = admin_client.get(f"/report/{device['device_id']}")
        assert resp.status_code == 200
        assert b"Mechanischer Schaden" in resp.data

    def test_form_returns_404_for_unknown_device(self, admin_client):
        resp = admin_client.get("/report/NONEXISTENT-999")
        assert resp.status_code == 404

    def test_submit_valid_data_creates_defect(self, app, admin_client, device):
        resp = admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "Gehäuse ist beschädigt",
                "event_name": "Sommerfestival 2025",
                "project_number": "PRJ-2025-001",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "success" in resp.headers["Location"]

        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            assert dev.status == "Wartung"
            df = Defect.query.filter_by(device_id=dev.id).first()
            assert df is not None
            assert df.category == "Mechanischer Schaden"
            assert df.description == "Gehäuse ist beschädigt"
            assert df.event_name == "Sommerfestival 2025"
            assert df.project_number == "PRJ-2025-001"

    def test_submit_sets_device_status_to_wartung(self, app, admin_client, device):
        admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
        )
        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            assert dev.status == "Wartung"

    def test_submit_records_reporter_as_current_user(self, app, admin_client, device):
        admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
        )
        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            df = Defect.query.filter_by(device_id=dev.id).first()
            assert df.reporter == "admin"

    def test_missing_category_shows_validation_error(self, admin_client, device):
        resp = admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Kategorie" in resp.data

    def test_invalid_category_shows_validation_error(self, admin_client, device):
        resp = admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "NICHT EXISTIERENDE KATEGORIE",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Kategorie" in resp.data

    def test_missing_description_shows_validation_error(self, admin_client, device):
        resp = admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Beschreibung" in resp.data

    def test_missing_event_name_shows_validation_error(self, admin_client, device):
        resp = admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "Test",
                "event_name": "",
                "project_number": "PRJ-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Event" in resp.data

    def test_missing_project_number_shows_validation_error(self, admin_client, device):
        resp = admin_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "Test",
                "event_name": "Event",
                "project_number": "",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Projektnummer" in resp.data


class TestDefectSuccess:
    def test_success_page_renders(self, admin_client, defect):
        resp = admin_client.get(f"/report/{defect['device_id']}/success")
        assert resp.status_code == 200

    def test_success_page_requires_login(self, client, defect):
        resp = client.get(f"/report/{defect['device_id']}/success", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_success_page_has_mailto_link_with_active_recipients(self, admin_client, defect):
        """The seeded werkstatt recipient is active → mailto: should appear."""
        resp = admin_client.get(f"/report/{defect['device_id']}/success")
        assert resp.status_code == 200
        assert b"mailto:" in resp.data

    def test_success_page_404_for_unknown_device(self, admin_client):
        resp = admin_client.get("/report/UNKNOWN-999/success")
        assert resp.status_code == 404

    def test_success_page_shows_device_name(self, admin_client, defect, device):
        resp = admin_client.get(f"/report/{defect['device_id']}/success")
        assert device["name"].encode() in resp.data


class TestDefectFormDatabaseErrors:
    """DB-Commit-Fehler bei der Defektmeldung zeigen verständliche Meldung."""

    _DB_ERROR = OperationalError("db error", {}, Exception("connection lost"))
    _FORM_DATA = {
        "category": "Mechanischer Schaden",
        "description": "Testschaden",
        "event_name": "Testfest",
        "project_number": "PRJ-001",
    }

    def test_db_error_shows_flash_message(self, admin_client, device):
        with patch("routes.report.db.session.commit", side_effect=self._DB_ERROR):
            resp = admin_client.post(
                f"/report/{device['device_id']}",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "konnte nicht gespeichert werden" in body

    def test_db_error_does_not_show_success(self, admin_client, device):
        with patch("routes.report.db.session.commit", side_effect=self._DB_ERROR):
            resp = admin_client.post(
                f"/report/{device['device_id']}",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        body = resp.data.decode("utf-8")
        assert "erfolgreich" not in body

    def test_db_error_re_renders_form_with_data(self, admin_client, device):
        """Nach DB-Fehler wird das Formular mit den eingegebenen Daten erneut angezeigt."""
        with patch("routes.report.db.session.commit", side_effect=self._DB_ERROR):
            resp = admin_client.post(
                f"/report/{device['device_id']}",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        assert resp.status_code == 200
        # The form should be rendered (not a redirect to success)
        assert device["name"].encode() in resp.data
