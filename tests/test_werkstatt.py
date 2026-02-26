"""
Tests for the Werkstatt role and /werkstatt/* routes.

Coverage:
  Access control       – unauthenticated / community / disponent / werkstatt / admin
  Login routing        – werkstatt lands on /werkstatt/ after login
  Admin access guard   – werkstatt cannot reach /admin/* pages
  Dashboard            – shows open defects, empty state
  Defect detail        – shows full defect, comments, photo
  Status change        – valid and invalid werkstatt_status
  Comment creation     – text, optional photo, oversized, invalid extension
  User model           – is_werkstatt flag, User.role property
  Admin user creation  – admin can create werkstatt users via form
"""

import io
from datetime import datetime, timezone

import pytest

from models import Comment, Defect, Device, User, db as _db


# =========================================================================== #
#  Helpers / shared fixtures                                                    #
# =========================================================================== #


@pytest.fixture
def dev(app):
    """A device in Wartung (has an open defect)."""
    with app.app_context():
        d = Device(device_id="WS-CAM-01", name="Kamera WS", status="Wartung")
        _db.session.add(d)
        _db.session.commit()
        return {"id": d.id, "device_id": d.device_id}


@pytest.fixture
def open_defect(app, dev):
    """An open defect on *dev* with werkstatt_status=Ausstehend."""
    with app.app_context():
        device = Device.query.filter_by(device_id=dev["device_id"]).first()
        df = Defect(
            device_id=device.id,
            category="Mechanischer Schaden",
            description="Linse verkratzt",
            event_name="Sommerfest",
            project_number="PRJ-WS-001",
            reporter="team_login",
            created_at=datetime(2025, 7, 1, 9, 0, tzinfo=timezone.utc),
        )
        _db.session.add(df)
        _db.session.commit()
        return {"id": df.id, "device_id": dev["device_id"]}


@pytest.fixture
def comment(app, open_defect):
    """A comment on *open_defect*."""
    with app.app_context():
        c = Comment(
            defect_id=open_defect["id"],
            username="werkstatt",
            user_role="werkstatt",
            text="Erstbefund: Linse austauschen.",
            photo_path=None,
        )
        _db.session.add(c)
        _db.session.commit()
        return {"id": c.id, "defect_id": open_defect["id"]}


# =========================================================================== #
#  1. Access control                                                            #
# =========================================================================== #


class TestWerkstattAccessControl:
    """Route guards: /werkstatt/* has correct access rules."""

    ROUTES = [
        "/werkstatt/",
    ]

    def test_unauthenticated_redirected_to_login(self, client):
        for route in self.ROUTES:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code == 302
            assert "/auth/login" in resp.headers["Location"]

    def test_community_user_gets_403(self, team_client):
        for route in self.ROUTES:
            resp = team_client.get(route)
            assert resp.status_code == 403

    def test_disponent_gets_403(self, disponent_client):
        for route in self.ROUTES:
            resp = disponent_client.get(route)
            assert resp.status_code == 403

    def test_werkstatt_user_can_access(self, werkstatt_client):
        resp = werkstatt_client.get("/werkstatt/")
        assert resp.status_code == 200

    def test_admin_can_access_werkstatt_routes(self, admin_client):
        resp = admin_client.get("/werkstatt/")
        assert resp.status_code == 200


# =========================================================================== #
#  2. Login routing                                                             #
# =========================================================================== #


class TestWerkstattLoginRouting:
    def test_werkstatt_redirected_to_dashboard_after_login(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "werkstatt", "password": "werk2025"},
            follow_redirects=False,
        )
        # Should redirect to / which then redirects to /werkstatt/
        assert resp.status_code == 302
        assert resp.headers["Location"] in ("/", "http://localhost/")

    def test_index_redirects_werkstatt_to_dashboard(self, werkstatt_client):
        resp = werkstatt_client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/werkstatt/" in resp.headers["Location"]

    def test_werkstatt_cannot_reach_admin_pages(self, werkstatt_client):
        resp = werkstatt_client.get("/admin/")
        assert resp.status_code == 403


# =========================================================================== #
#  3. User model                                                                #
# =========================================================================== #


class TestWerkstattUserModel:
    def test_seeded_werkstatt_user_exists(self, app):
        with app.app_context():
            u = User.query.filter_by(username="werkstatt").first()
            assert u is not None
            assert u.is_werkstatt is True
            assert u.is_admin is False
            assert u.is_disponent is False

    def test_werkstatt_role_property(self, app):
        with app.app_context():
            u = User.query.filter_by(username="werkstatt").first()
            assert u.role == "werkstatt"

    def test_admin_can_create_werkstatt_user(self, admin_client):
        resp = admin_client.post(
            "/admin/users",
            data={
                "action": "add",
                "username": "ws_test",
                "password": "Passwort12",
                "is_werkstatt": "on",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"ws_test" in resp.data


# =========================================================================== #
#  4. Dashboard                                                                 #
# =========================================================================== #


class TestWerkstattDashboard:
    def test_empty_dashboard(self, werkstatt_client):
        resp = werkstatt_client.get("/werkstatt/")
        assert resp.status_code == 200
        assert "Keine offenen Defekte".encode() in resp.data

    def test_dashboard_shows_open_defect(self, werkstatt_client, open_defect):
        resp = werkstatt_client.get("/werkstatt/")
        assert resp.status_code == 200
        assert b"Kamera WS" in resp.data
        assert b"Linse verkratzt" in resp.data

    def test_dashboard_shows_device_id(self, werkstatt_client, open_defect):
        resp = werkstatt_client.get("/werkstatt/")
        assert resp.status_code == 200
        assert b"WS-CAM-01" in resp.data

    def test_dashboard_shows_werkstatt_status(self, werkstatt_client, open_defect):
        resp = werkstatt_client.get("/werkstatt/")
        assert resp.status_code == 200
        assert "Ausstehend".encode() in resp.data


# =========================================================================== #
#  5. Defect detail                                                             #
# =========================================================================== #


class TestWerkstattDefektDetail:
    def test_detail_returns_200(self, werkstatt_client, open_defect):
        resp = werkstatt_client.get(f"/werkstatt/defekt/{open_defect['id']}")
        assert resp.status_code == 200

    def test_detail_shows_defect_info(self, werkstatt_client, open_defect):
        resp = werkstatt_client.get(f"/werkstatt/defekt/{open_defect['id']}")
        assert b"Linse verkratzt" in resp.data
        assert b"Mechanischer Schaden" in resp.data
        assert b"Sommerfest" in resp.data

    def test_detail_shows_comment(self, werkstatt_client, open_defect, comment):
        resp = werkstatt_client.get(f"/werkstatt/defekt/{open_defect['id']}")
        assert b"Erstbefund: Linse austauschen." in resp.data

    def test_detail_404_for_unknown_defect(self, werkstatt_client):
        resp = werkstatt_client.get("/werkstatt/defekt/99999")
        assert resp.status_code == 404

    def test_detail_shows_status_dropdown(self, werkstatt_client, open_defect):
        resp = werkstatt_client.get(f"/werkstatt/defekt/{open_defect['id']}")
        assert b"In Pr" in resp.data  # "In Prüfung" (ü may be encoded)
        assert b"In Reparatur" in resp.data
        assert b"Repariert" in resp.data


# =========================================================================== #
#  6. Status change                                                             #
# =========================================================================== #


class TestWerkstattStatusChange:
    def test_valid_status_change(self, werkstatt_client, open_defect, app):
        resp = werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/status",
            data={"werkstatt_status": "In Reparatur"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "In Reparatur".encode() in resp.data
        with app.app_context():
            df = _db.session.get(Defect, open_defect["id"])
            assert df.werkstatt_status == "In Reparatur"

    def test_status_cycles_through_all_values(self, werkstatt_client, open_defect, app):
        for status in ["In Prüfung", "In Reparatur", "Repariert"]:
            resp = werkstatt_client.post(
                f"/werkstatt/defekt/{open_defect['id']}/status",
                data={"werkstatt_status": status},
                follow_redirects=True,
            )
            assert resp.status_code == 200
        with app.app_context():
            df = _db.session.get(Defect, open_defect["id"])
            assert df.werkstatt_status == "Repariert"

    def test_invalid_status_returns_error(self, werkstatt_client, open_defect):
        resp = werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/status",
            data={"werkstatt_status": "UNGÜLTIG"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Ung" in resp.data  # "Ungültiger Status."

    def test_community_user_cannot_change_status(self, team_client, open_defect):
        resp = team_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/status",
            data={"werkstatt_status": "In Reparatur"},
        )
        assert resp.status_code == 403


# =========================================================================== #
#  7. Comment creation                                                          #
# =========================================================================== #


class TestWerkstattComments:
    def test_add_text_comment(self, werkstatt_client, open_defect, app):
        resp = werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={"text": "Ersatzteil bestellt."},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Ersatzteil bestellt." in resp.data
        with app.app_context():
            comments = Comment.query.filter_by(defect_id=open_defect["id"]).all()
            assert any(c.text == "Ersatzteil bestellt." for c in comments)

    def test_comment_author_is_current_user(self, werkstatt_client, open_defect, app):
        werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={"text": "Befund abgeschlossen."},
            follow_redirects=True,
        )
        with app.app_context():
            c = Comment.query.filter_by(
                defect_id=open_defect["id"], text="Befund abgeschlossen."
            ).first()
            assert c is not None
            assert c.username == "werkstatt"
            assert c.user_role == "werkstatt"

    def test_comment_has_created_at_timestamp(self, werkstatt_client, open_defect, app):
        """Every comment must be stored with a non-null created_at timestamp."""
        from datetime import datetime, timezone
        before = datetime.now(timezone.utc)
        werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={"text": "Zeitstempel-Check."},
            follow_redirects=True,
        )
        with app.app_context():
            c = Comment.query.filter_by(
                defect_id=open_defect["id"], text="Zeitstempel-Check."
            ).first()
            assert c is not None
            assert c.created_at is not None, "Comment.created_at must not be None"
            # created_at must be a datetime (stored as UTC-naive or aware)
            assert isinstance(c.created_at, datetime)

    def test_empty_comment_rejected(self, werkstatt_client, open_defect):
        resp = werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={"text": "   "},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"leer" in resp.data  # "Kommentartext darf nicht leer sein."

    def test_oversized_comment_rejected(self, werkstatt_client, open_defect):
        long_text = "x" * 2001
        resp = werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={"text": long_text},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"lang" in resp.data  # "Kommentar ist zu lang"

    def test_comment_with_photo_upload(self, werkstatt_client, open_defect, app):
        photo_data = io.BytesIO(b"\xff\xd8\xff\xe0fake_jpeg_data")
        resp = werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={
                "text": "Foto vom Schaden.",
                "photo": (photo_data, "schaden.jpg"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            c = Comment.query.filter_by(
                defect_id=open_defect["id"], text="Foto vom Schaden."
            ).first()
            assert c is not None
            assert c.photo_path is not None
            assert c.photo_path.endswith(".jpg")

    def test_comment_with_invalid_photo_extension_rejected(
        self, werkstatt_client, open_defect, app
    ):
        exe_data = io.BytesIO(b"MZfake_exe")
        resp = werkstatt_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={
                "text": "Malicious upload attempt.",
                "photo": (exe_data, "virus.exe"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            c = Comment.query.filter_by(
                defect_id=open_defect["id"], text="Malicious upload attempt."
            ).first()
            # Comment should be saved but photo_path must be None
            assert c is not None
            assert c.photo_path is None

    def test_admin_can_add_comment(self, admin_client, open_defect, app):
        resp = admin_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={"text": "Admin-Notiz."},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            c = Comment.query.filter_by(
                defect_id=open_defect["id"], text="Admin-Notiz."
            ).first()
            assert c is not None
            assert c.username == "admin"
            assert c.user_role == "admin"

    def test_community_user_cannot_add_comment(self, team_client, open_defect):
        resp = team_client.post(
            f"/werkstatt/defekt/{open_defect['id']}/kommentar",
            data={"text": "Darf nicht."},
        )
        assert resp.status_code == 403


# =========================================================================== #
#  8. Report form: initial photo upload                                         #
# =========================================================================== #


class TestReportFormPhotoUpload:
    """Ensure the defect report form accepts an optional photo."""

    @pytest.fixture
    def report_device(self, app):
        with app.app_context():
            d = Device(device_id="RP-CAM-01", name="Report-Kamera", status="Verfügbar")
            _db.session.add(d)
            _db.session.commit()
            return {"device_id": d.device_id}

    def test_report_without_photo_works(self, team_client, report_device):
        resp = team_client.post(
            f"/report/{report_device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "Kratzer am Gehäuse",
                "event_name": "Stadtfest",
                "project_number": "PRJ-123",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_report_with_photo_creates_initial_comment(
        self, team_client, report_device, app
    ):
        photo_data = io.BytesIO(b"\x89PNGfake_png_data")
        resp = team_client.post(
            f"/report/{report_device['device_id']}",
            data={
                "category": "Mechanischer Schaden",
                "description": "Riss im Gehäuse",
                "event_name": "Stadtfest",
                "project_number": "PRJ-124",
                "photo": (photo_data, "schaden.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            dev = Device.query.filter_by(device_id=report_device["device_id"]).first()
            df = Defect.query.filter_by(device_id=dev.id).first()
            assert df is not None
            comments = Comment.query.filter_by(defect_id=df.id).all()
            photo_comments = [c for c in comments if c.photo_path]
            assert len(photo_comments) == 1
            assert photo_comments[0].photo_path.endswith(".png")
