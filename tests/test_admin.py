"""
Tests for admin routes:
  /admin/              Dashboard
  /admin/devices       Device management
  /admin/history/...   Device defect history
  /admin/repair/...    Mark defect repaired
  /admin/defects       All defects overview
  /admin/users         User management
  /admin/recipients    E-mail recipient management
  /admin/categories    Defect category management
  /admin/event-report  Event summary report sending
"""
import smtplib
import socket
from unittest.mock import patch

from models import db, Defect, DefectCategory, Device, EmailRecipient, User


class TestAdminAccess:
    def test_dashboard_redirects_unauthenticated(self, client):
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 302

    def test_dashboard_returns_403_for_team_user(self, team_client):
        resp = team_client.get("/admin/")
        assert resp.status_code == 403

    def test_dashboard_accessible_for_admin(self, admin_client):
        resp = admin_client.get("/admin/")
        assert resp.status_code == 200

    def test_dashboard_shows_statistics(self, admin_client):
        resp = admin_client.get("/admin/")
        assert resp.status_code == 200
        # Some numeric stats should be present
        assert b"0" in resp.data


class TestDeviceManagement:
    def test_devices_page_renders(self, admin_client):
        resp = admin_client.get("/admin/devices")
        assert resp.status_code == 200

    def test_add_device_success(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "NEW-001", "name": "Neues Gerät", "description": ""},
        )
        with app.app_context():
            assert Device.query.filter_by(device_id="NEW-001").first() is not None

    def test_add_device_appears_in_list(self, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "LIST-001", "name": "Listenkamera", "description": ""},
        )
        resp = admin_client.get("/admin/devices")
        assert b"Listenkamera" in resp.data

    def test_add_device_duplicate_id_shows_error(self, admin_client, device):
        resp = admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": device["device_id"], "name": "Duplikat"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "vergeben" in resp.data.decode("utf-8")

    def test_add_device_missing_id_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "", "name": "Kein ID"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich" in resp.data.decode("utf-8")

    def test_add_device_missing_name_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "ID-NONAME", "name": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich" in resp.data.decode("utf-8")

    def test_delete_device_removes_from_db(self, app, admin_client, device):
        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            dev_pk = dev.id

        admin_client.post("/admin/devices", data={"action": "delete", "dev_id": dev_pk})

        with app.app_context():
            assert db.session.get(Device, dev_pk) is None

    def test_qr_code_download_returns_png(self, admin_client, device):
        resp = admin_client.get(f"/admin/qr/{device['device_id']}")
        assert resp.status_code == 200
        assert resp.content_type == "image/png"

    def test_qr_code_unknown_device_redirects(self, admin_client):
        resp = admin_client.get("/admin/qr/NONEXISTENT-999", follow_redirects=False)
        assert resp.status_code == 302

    def test_qr_page_renders(self, admin_client, device):
        resp = admin_client.get(f"/admin/qr-page/{device['device_id']}")
        assert resp.status_code == 200
        assert device["name"].encode() in resp.data

    def test_device_history_renders(self, admin_client, device):
        resp = admin_client.get(f"/admin/history/{device['device_id']}")
        assert resp.status_code == 200

    def test_device_history_shows_defects(self, admin_client, defect):
        resp = admin_client.get(f"/admin/history/{defect['device_id']}")
        assert resp.status_code == 200
        assert b"Mechanischer Schaden" in resp.data


class TestDefectManagement:
    def test_all_defects_page_renders(self, admin_client):
        resp = admin_client.get("/admin/defects")
        assert resp.status_code == 200

    def test_all_defects_lists_open_defect(self, admin_client, defect):
        resp = admin_client.get("/admin/defects")
        assert resp.status_code == 200
        assert b"Mechanischer Schaden" in resp.data

    def test_filter_by_status_offen(self, admin_client, defect):
        resp = admin_client.get("/admin/defects?status=Offen")
        assert resp.status_code == 200
        assert b"Mechanischer Schaden" in resp.data

    def test_filter_by_status_behoben_returns_empty(self, admin_client, defect):
        resp = admin_client.get("/admin/defects?status=Behoben")
        assert resp.status_code == 200
        # Our defect is Offen → should not appear
        assert b"Mechanischer Schaden" not in resp.data

    def test_filter_by_event_name(self, admin_client, defect):
        resp = admin_client.get("/admin/defects?event=Sommer")
        assert resp.status_code == 200
        assert b"Mechanischer Schaden" in resp.data

    def test_mark_repaired_sets_status_behoben(self, app, admin_client, defect):
        admin_client.post(
            f"/admin/repair/{defect['id']}",
            data={"resolution_notes": "Gehäuse ersetzt"},
        )
        with app.app_context():
            df = db.session.get(Defect, defect["id"])
            assert df.status == "Behoben"
            assert df.resolution_notes == "Gehäuse ersetzt"
            assert df.resolved_at is not None

    def test_mark_repaired_restores_device_to_verfuegbar(self, app, admin_client, defect):
        """When last open defect is resolved, device should return to Verfügbar."""
        admin_client.post(
            f"/admin/repair/{defect['id']}",
            data={"resolution_notes": "Fix"},
        )
        with app.app_context():
            dev = Device.query.filter_by(device_id=defect["device_id"]).first()
            assert dev.status == "Verfügbar"

    def test_mark_repaired_redirects_to_history(self, admin_client, defect):
        resp = admin_client.post(
            f"/admin/repair/{defect['id']}",
            data={"resolution_notes": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "history" in resp.headers["Location"]

    def test_mark_repaired_nonexistent_returns_404(self, admin_client):
        resp = admin_client.post("/admin/repair/99999", data={"resolution_notes": ""})
        assert resp.status_code == 404

    def test_device_stays_wartung_when_another_defect_open(self, app, admin_client, defect):
        """If a second open defect exists, device stays in Wartung after resolving first."""
        with app.app_context():
            dev = Device.query.filter_by(device_id=defect["device_id"]).first()
            second = Defect(
                device_id=dev.id,
                category="Sonstiges",
                description="Zweiter Defekt",
                event_name="Event",
                project_number="PRJ-001",
            )
            db.session.add(second)
            db.session.commit()
            second_id = second.id

        admin_client.post(f"/admin/repair/{defect['id']}", data={"resolution_notes": ""})

        with app.app_context():
            dev = Device.query.filter_by(device_id=defect["device_id"]).first()
            assert dev.status == "Wartung"


class TestUserManagement:
    def test_users_page_renders(self, admin_client):
        resp = admin_client.get("/admin/users")
        assert resp.status_code == 200

    def test_add_user_success(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "newuser", "password": "newpass123"},
        )
        with app.app_context():
            assert User.query.filter_by(username="newuser").first() is not None

    def test_add_admin_user(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "newadmin", "password": "securepass1", "is_admin": "on"},
        )
        with app.app_context():
            u = User.query.filter_by(username="newadmin").first()
            assert u is not None
            assert u.is_admin is True

    def test_add_duplicate_username_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "admin", "password": "anything"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "vergeben" in resp.data.decode("utf-8")

    def test_add_user_missing_password_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "nopassuser", "password": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich" in resp.data.decode("utf-8")

    def test_cannot_delete_admin_user(self, app, admin_client):
        with app.app_context():
            admin = User.query.filter_by(username="admin").first()
            admin_id = admin.id

        resp = admin_client.post(
            "/admin/users",
            data={"action": "delete", "user_id": admin_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            assert User.query.filter_by(username="admin").first() is not None

    def test_delete_regular_user(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "tobedeleted", "password": "password123"},
        )
        with app.app_context():
            u = User.query.filter_by(username="tobedeleted").first()
            uid = u.id

        admin_client.post("/admin/users", data={"action": "delete", "user_id": uid})

        with app.app_context():
            assert db.session.get(User, uid) is None

    def test_change_password(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "changepw", "password": "oldpass123"},
        )
        with app.app_context():
            u = User.query.filter_by(username="changepw").first()
            uid = u.id

        admin_client.post(
            "/admin/users",
            data={"action": "change_password", "user_id": uid, "new_password": "newpass456"},
        )

        with app.app_context():
            u = User.query.filter_by(username="changepw").first()
            assert u.check_password("newpass456") is True
            assert u.check_password("oldpass123") is False


class TestRecipientManagement:
    def test_recipients_page_renders(self, admin_client):
        resp = admin_client.get("/admin/recipients")
        assert resp.status_code == 200

    def test_add_recipient_success(self, app, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "Test Empfänger", "email": "test@example.com"},
        )
        with app.app_context():
            assert EmailRecipient.query.filter_by(email="test@example.com").first() is not None

    def test_add_duplicate_email_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "Dup", "email": "werkstatt@redline.local"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "eingetragen" in resp.data.decode("utf-8")

    def test_add_recipient_missing_fields_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "", "email": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich" in resp.data.decode("utf-8")

    def test_delete_recipient(self, app, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "Temp", "email": "temp@example.com"},
        )
        with app.app_context():
            rec = EmailRecipient.query.filter_by(email="temp@example.com").first()
            rec_id = rec.id

        admin_client.post("/admin/recipients", data={"action": "delete", "rec_id": rec_id})

        with app.app_context():
            assert db.session.get(EmailRecipient, rec_id) is None

    def test_toggle_recipient_deactivates(self, app, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "Toggle", "email": "toggle@example.com"},
        )
        with app.app_context():
            rec = EmailRecipient.query.filter_by(email="toggle@example.com").first()
            rec_id = rec.id
            assert rec.active is True

        admin_client.post("/admin/recipients", data={"action": "toggle", "rec_id": rec_id})

        with app.app_context():
            rec = db.session.get(EmailRecipient, rec_id)
            assert rec.active is False

    def test_toggle_recipient_reactivates(self, app, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "Toggle2", "email": "toggle2@example.com"},
        )
        with app.app_context():
            rec = EmailRecipient.query.filter_by(email="toggle2@example.com").first()
            rec_id = rec.id

        # Deactivate
        admin_client.post("/admin/recipients", data={"action": "toggle", "rec_id": rec_id})
        # Reactivate
        admin_client.post("/admin/recipients", data={"action": "toggle", "rec_id": rec_id})

        with app.app_context():
            rec = db.session.get(EmailRecipient, rec_id)
            assert rec.active is True


class TestCategoryManagement:
    def test_categories_page_renders(self, admin_client):
        resp = admin_client.get("/admin/categories")
        assert resp.status_code == 200

    def test_default_categories_visible(self, admin_client):
        resp = admin_client.get("/admin/categories")
        assert b"Mechanischer Schaden" in resp.data

    def test_add_category_success(self, app, admin_client):
        admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": "Neue Testkategorie"},
        )
        with app.app_context():
            assert DefectCategory.query.filter_by(name="Neue Testkategorie").first() is not None

    def test_add_duplicate_category_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": "Mechanischer Schaden"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "existiert" in resp.data.decode("utf-8")

    def test_add_category_missing_name_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich" in resp.data.decode("utf-8")

    def test_delete_category(self, app, admin_client):
        admin_client.post("/admin/categories", data={"action": "add", "name": "ZuLöschen"})
        with app.app_context():
            cat = DefectCategory.query.filter_by(name="ZuLöschen").first()
            cat_id = cat.id

        admin_client.post("/admin/categories", data={"action": "delete", "cat_id": cat_id})

        with app.app_context():
            assert db.session.get(DefectCategory, cat_id) is None

    def test_move_category_up_changes_sort_order(self, app, admin_client):
        admin_client.post("/admin/categories", data={"action": "add", "name": "Kat Alpha"})
        admin_client.post("/admin/categories", data={"action": "add", "name": "Kat Beta"})

        with app.app_context():
            beta = DefectCategory.query.filter_by(name="Kat Beta").first()
            beta_id = beta.id
            order_before = beta.sort_order

        admin_client.post("/admin/categories", data={"action": "move_up", "cat_id": beta_id})

        with app.app_context():
            beta = db.session.get(DefectCategory, beta_id)
            assert beta.sort_order < order_before

    def test_move_category_down_changes_sort_order(self, app, admin_client):
        admin_client.post("/admin/categories", data={"action": "add", "name": "Kat Gamma"})
        admin_client.post("/admin/categories", data={"action": "add", "name": "Kat Delta"})

        with app.app_context():
            gamma = DefectCategory.query.filter_by(name="Kat Gamma").first()
            gamma_id = gamma.id
            order_before = gamma.sort_order

        admin_client.post("/admin/categories", data={"action": "move_down", "cat_id": gamma_id})

        with app.app_context():
            gamma = db.session.get(DefectCategory, gamma_id)
            assert gamma.sort_order > order_before


class TestEventReport:
    """Tests for /admin/event-report – Ereignisbericht senden."""

    _FORM_DATA = {
        "event_name": "Testfest 2025",
        "project_number": "PRJ-2025-TEST",
        "recipient": "empfaenger@example.com",
    }

    # ------------------------------------------------------------------ #
    #  Access control                                                      #
    # ------------------------------------------------------------------ #

    def test_page_renders_for_admin(self, admin_client):
        resp = admin_client.get("/admin/event-report")
        assert resp.status_code == 200
        assert "Ereignisbericht" in resp.data.decode("utf-8")

    def test_redirects_unauthenticated(self, client):
        resp = client.get("/admin/event-report", follow_redirects=False)
        assert resp.status_code == 302

    def test_forbidden_for_team_user(self, team_client):
        resp = team_client.get("/admin/event-report")
        assert resp.status_code == 403

    # ------------------------------------------------------------------ #
    #  Validation                                                          #
    # ------------------------------------------------------------------ #

    def test_all_empty_fields_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/event-report",
            data={"event_name": "", "project_number": "", "recipient": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich" in resp.data.decode("utf-8")

    def test_missing_project_number_shows_error(self, admin_client):
        resp = admin_client.post(
            "/admin/event-report",
            data={"event_name": "Testfest", "project_number": "", "recipient": "a@b.de"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich" in resp.data.decode("utf-8")

    # ------------------------------------------------------------------ #
    #  Successful send                                                     #
    # ------------------------------------------------------------------ #

    def test_success_shows_success_message(self, admin_client):
        resp = admin_client.post(
            "/admin/event-report",
            data=self._FORM_DATA,
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "gesendet" in resp.data.decode("utf-8")

    def test_success_with_existing_defects_shows_count(self, admin_client, defect):
        resp = admin_client.post(
            "/admin/event-report",
            data={
                "event_name": "Sommerfestival",
                "project_number": "PRJ-2025-001",
                "recipient": "empfaenger@example.com",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "gesendet" in body
        assert "1" in body  # 1 Defekt im Bericht

    def test_success_with_no_matching_defects(self, admin_client):
        """Bericht für unbekanntes Event – 0 Defekte, trotzdem Erfolg."""
        resp = admin_client.post(
            "/admin/event-report",
            data={
                "event_name": "KeinEvent",
                "project_number": "PRJ-0000",
                "recipient": "empfaenger@example.com",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "gesendet" in body
        assert "0" in body

    # ------------------------------------------------------------------ #
    #  SMTP error messages                                                 #
    # ------------------------------------------------------------------ #

    def test_smtp_auth_error_shows_credential_hint(self, admin_client):
        with patch(
            "routes.admin.send_event_summary_report",
            side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed"),
        ):
            resp = admin_client.post(
                "/admin/event-report",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "MAIL_USERNAME" in body
        assert "MAIL_PASSWORD" in body

    def test_smtp_connect_error_shows_server_hint(self, admin_client):
        with patch(
            "routes.admin.send_event_summary_report",
            side_effect=smtplib.SMTPConnectError(421, b"Connection refused"),
        ):
            resp = admin_client.post(
                "/admin/event-report",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        assert resp.status_code == 200
        assert "MAIL_SERVER" in resp.data.decode("utf-8")

    def test_connection_refused_shows_server_hint(self, admin_client):
        with patch(
            "routes.admin.send_event_summary_report",
            side_effect=ConnectionRefusedError(),
        ):
            resp = admin_client.post(
                "/admin/event-report",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        assert resp.status_code == 200
        assert "MAIL_SERVER" in resp.data.decode("utf-8")

    def test_gaierror_shows_server_hint(self, admin_client):
        with patch(
            "routes.admin.send_event_summary_report",
            side_effect=socket.gaierror("Name or service not known"),
        ):
            resp = admin_client.post(
                "/admin/event-report",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        assert resp.status_code == 200
        assert "MAIL_SERVER" in resp.data.decode("utf-8")

    def test_recipients_refused_shows_recipient_hint(self, admin_client):
        with patch(
            "routes.admin.send_event_summary_report",
            side_effect=smtplib.SMTPRecipientsRefused(
                {"bad@mail.invalid": (550, b"Refused")}
            ),
        ):
            resp = admin_client.post(
                "/admin/event-report",
                data={**self._FORM_DATA, "recipient": "bad@mail.invalid"},
                follow_redirects=True,
            )
        assert resp.status_code == 200
        assert "abgelehnt" in resp.data.decode("utf-8")

    def test_no_success_flash_on_error(self, admin_client):
        """Bei SMTP-Fehler darf keine Erfolgsmeldung erscheinen."""
        with patch(
            "routes.admin.send_event_summary_report",
            side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed"),
        ):
            resp = admin_client.post(
                "/admin/event-report",
                data=self._FORM_DATA,
                follow_redirects=True,
            )
        body = resp.data.decode("utf-8")
        assert "gesendet" not in body
