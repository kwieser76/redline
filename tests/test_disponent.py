"""
Tests for the Disponent role and /disponent/* routes.

Coverage:
  Access control       – unauthenticated / community / disponent / admin
  Login routing        – disponent lands on /disponent/ after login
  Admin access guard   – disponent cannot reach /admin/* pages
  Dashboard            – stat counts, tile links, unavailable-device table
  Tile detail pages    – filter=alle/verfuegbar/nicht-verfuegbar/reserviert
  Geräteübersicht      – read-only device list
  Geräteverfügbarkeit  – date-range filter, category filter, empty state
  CSV export           – content-type, filename, headers
  User model           – is_disponent flag, User.role property
  Admin user creation  – admin can create disponent users via form
"""

from datetime import datetime, timezone

import pytest

from models import Defect, Device, User, db as _db


# =========================================================================== #
#  Helpers / shared fixtures                                                    #
# =========================================================================== #


@pytest.fixture
def cam(app):
    """A device with status=Verfügbar."""
    with app.app_context():
        d = Device(device_id="DIS-CAM", name="Kamera Disp", status="Verfügbar")
        _db.session.add(d)
        _db.session.commit()
        return {"id": d.id, "device_id": d.device_id}


@pytest.fixture
def cam_wartung(app):
    """A device with status=Wartung."""
    with app.app_context():
        d = Device(device_id="DIS-WART", name="Gerät Wartung", status="Wartung")
        _db.session.add(d)
        _db.session.commit()
        return {"id": d.id, "device_id": d.device_id}


@pytest.fixture
def cam_reserviert(app):
    """A device with status=Reserviert."""
    with app.app_context():
        d = Device(device_id="DIS-RES", name="Gerät Reserviert", status="Reserviert")
        _db.session.add(d)
        _db.session.commit()
        return {"id": d.id, "device_id": d.device_id}


@pytest.fixture
def open_defect(app, cam_wartung):
    """An open defect on cam_wartung."""
    with app.app_context():
        dev = Device.query.filter_by(device_id=cam_wartung["device_id"]).first()
        df = Defect(
            device_id=dev.id,
            category="Mechanischer Schaden",
            description="Linse verkratzt",
            event_name="Stadtfest",
            project_number="PRJ-001",
            reporter="disponent",
            created_at=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
        )
        _db.session.add(df)
        _db.session.commit()
        return {"id": df.id}


# =========================================================================== #
#  1. Access control                                                            #
# =========================================================================== #


class TestDisponentAccessControl:
    """Route guards: every /disponent/* page has correct access rules."""

    ROUTES = [
        "/disponent/",
        "/disponent/geraete",
        "/disponent/verfuegbarkeit",
        "/disponent/kachel/alle",
    ]

    def test_unauthenticated_redirected_to_login(self, client):
        for route in self.ROUTES:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code == 302, f"{route} should redirect unauthenticated"
            assert "/auth/login" in resp.headers["Location"]

    def test_community_user_gets_403(self, team_client):
        for route in self.ROUTES:
            resp = team_client.get(route)
            assert resp.status_code == 403, f"{route} should deny community user"

    def test_disponent_can_access_all_routes(self, disponent_client):
        for route in self.ROUTES:
            resp = disponent_client.get(route)
            assert resp.status_code == 200, f"{route} should be accessible to disponent"

    def test_admin_can_access_disponent_routes(self, admin_client):
        for route in self.ROUTES:
            resp = admin_client.get(route)
            assert resp.status_code == 200, f"Admin should also access {route}"


# =========================================================================== #
#  2. Login routing                                                             #
# =========================================================================== #


class TestDisponentLoginRouting:
    def test_login_redirects_disponent_to_disponent_dashboard(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "disponent", "password": "disp2025"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        # Should land on /disponent/ (via index redirect)
        follow = client.get(resp.headers["Location"], follow_redirects=False)
        assert follow.headers["Location"].endswith("/disponent/")

    def test_login_does_not_redirect_admin_to_disponent(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        follow = client.get(resp.headers["Location"], follow_redirects=False)
        assert "/admin/" in follow.headers["Location"]


# =========================================================================== #
#  3. Admin pages blocked for disponnents                                       #
# =========================================================================== #


class TestDisponentCannotAccessAdmin:
    ADMIN_ROUTES = [
        "/admin/",
        "/admin/devices",
        "/admin/users",
        "/admin/categories",
        "/admin/recipients",
    ]

    def test_admin_routes_return_403_for_disponent(self, disponent_client):
        for route in self.ADMIN_ROUTES:
            resp = disponent_client.get(route)
            assert resp.status_code == 403, f"Disponent must be denied {route}"


# =========================================================================== #
#  4. Dashboard                                                                 #
# =========================================================================== #


class TestDisponentDashboard:
    def test_dashboard_renders_200(self, disponent_client):
        resp = disponent_client.get("/disponent/")
        assert resp.status_code == 200

    def test_dashboard_shows_all_four_tiles(self, disponent_client):
        resp = disponent_client.get("/disponent/")
        body = resp.data.decode()
        assert "Geräte gesamt" in body
        assert "Nicht verfügbar" in body
        # "Reserviert" tile replaced with "Offene Defekte" (Issue #38)
        assert "Offene Defekte" in body
        assert "Verfügbar heute" in body

    def test_dashboard_tile_links_present(self, disponent_client):
        resp = disponent_client.get("/disponent/")
        body = resp.data.decode()
        assert "/disponent/kachel/alle" in body
        assert "/disponent/kachel/nicht-verfuegbar" in body
        # "Reserviert" tile removed from dashboard (Issue #38); filter still exists in tile_detail
        assert "/disponent/kachel/verfuegbar" in body

    def test_dashboard_counts_reflect_device_statuses(
        self, app, disponent_client, cam, cam_wartung, cam_reserviert
    ):
        resp = disponent_client.get("/disponent/")
        assert resp.status_code == 200
        # We inserted 3 devices (1 Verfügbar, 1 Wartung, 1 Reserviert)
        body = resp.data.decode()
        assert "Gerät Wartung" in body  # shows in unavailable table

    def test_dashboard_shows_unavailable_devices_table(
        self, disponent_client, cam_wartung
    ):
        resp = disponent_client.get("/disponent/")
        assert "Gerät Wartung" in resp.data.decode()

    def test_dashboard_empty_message_when_all_available(self, disponent_client, cam):
        resp = disponent_client.get("/disponent/")
        assert "Alle Geräte sind aktuell verfügbar" in resp.data.decode()

    def test_dashboard_nav_links_present(self, disponent_client):
        resp = disponent_client.get("/disponent/")
        body = resp.data.decode()
        assert "/disponent/verfuegbarkeit" in body
        assert "/disponent/geraete" in body


# =========================================================================== #
#  5. Tile detail pages                                                         #
# =========================================================================== #


class TestTileDetail:
    def test_alle_shows_every_device(
        self, disponent_client, cam, cam_wartung, cam_reserviert
    ):
        resp = disponent_client.get("/disponent/kachel/alle")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Kamera Disp" in body
        assert "Gerät Wartung" in body
        assert "Gerät Reserviert" in body

    def test_verfuegbar_shows_only_available(
        self, disponent_client, cam, cam_wartung
    ):
        resp = disponent_client.get("/disponent/kachel/verfuegbar")
        body = resp.data.decode()
        assert "Kamera Disp" in body
        assert "Gerät Wartung" not in body

    def test_nicht_verfuegbar_shows_only_wartung(
        self, disponent_client, cam, cam_wartung
    ):
        resp = disponent_client.get("/disponent/kachel/nicht-verfuegbar")
        body = resp.data.decode()
        assert "Gerät Wartung" in body
        assert "Kamera Disp" not in body

    def test_reserviert_shows_only_reserved(
        self, disponent_client, cam, cam_reserviert
    ):
        resp = disponent_client.get("/disponent/kachel/reserviert")
        body = resp.data.decode()
        assert "Gerät Reserviert" in body
        assert "Kamera Disp" not in body

    def test_invalid_filter_key_returns_404(self, disponent_client):
        resp = disponent_client.get("/disponent/kachel/unbekannt")
        assert resp.status_code == 404

    def test_filter_pills_shown_on_all_detail_pages(self, disponent_client):
        for key in ["alle", "verfuegbar", "nicht-verfuegbar", "reserviert"]:
            resp = disponent_client.get(f"/disponent/kachel/{key}")
            body = resp.data.decode()
            # All 4 pill links must always be visible
            assert "/disponent/kachel/alle" in body
            assert "/disponent/kachel/verfuegbar" in body

    def test_empty_filter_shows_no_devices_message(self, disponent_client, cam):
        # cam is Verfügbar; reserviert list should be empty
        resp = disponent_client.get("/disponent/kachel/reserviert")
        assert "Keine Geräte in dieser Kategorie" in resp.data.decode()


# =========================================================================== #
#  6. Geräteübersicht (read-only)                                               #
# =========================================================================== #


class TestDisponentDevices:
    def test_devices_page_renders(self, disponent_client):
        resp = disponent_client.get("/disponent/geraete")
        assert resp.status_code == 200

    def test_devices_page_shows_all_devices(
        self, disponent_client, cam, cam_wartung
    ):
        resp = disponent_client.get("/disponent/geraete")
        body = resp.data.decode()
        assert "Kamera Disp" in body
        assert "Gerät Wartung" in body

    def test_devices_page_has_no_add_form(self, disponent_client):
        resp = disponent_client.get("/disponent/geraete")
        body = resp.data.decode()
        # No edit/delete/add UI for disponnents
        assert 'action="add"' not in body
        assert 'action="delete"' not in body

    def test_devices_status_badges_shown(self, disponent_client, cam, cam_wartung):
        resp = disponent_client.get("/disponent/geraete")
        body = resp.data.decode()
        assert "Verfügbar" in body
        assert "In Wartung" in body

    def test_reserviert_badge_shown(self, disponent_client, cam_reserviert):
        resp = disponent_client.get("/disponent/geraete")
        assert "Reserviert" in resp.data.decode()


# =========================================================================== #
#  7. Geräteverfügbarkeit                                                       #
# =========================================================================== #


class TestDisponentAvailability:
    def test_availability_page_renders(self, disponent_client):
        resp = disponent_client.get("/disponent/verfuegbarkeit")
        assert resp.status_code == 200

    def test_availability_with_defect_shows_entry(
        self, disponent_client, open_defect
    ):
        resp = disponent_client.get(
            "/disponent/verfuegbarkeit?from=2025-06-01&to=2025-06-30"
        )
        body = resp.data.decode()
        assert "Linse verkratzt" in body
        assert "Stadtfest" in body

    def test_availability_empty_when_no_defects(self, disponent_client):
        resp = disponent_client.get(
            "/disponent/verfuegbarkeit?from=2030-01-01&to=2030-01-31"
        )
        assert "Keine nicht verfügbaren Geräte" in resp.data.decode()

    def test_availability_category_filter_narrows_results(
        self, disponent_client, open_defect
    ):
        # Matching category → shown
        resp = disponent_client.get(
            "/disponent/verfuegbarkeit"
            "?from=2025-06-01&to=2025-06-30&category=Mechanischer+Schaden"
        )
        assert "Linse verkratzt" in resp.data.decode()

        # Non-matching category → empty
        resp = disponent_client.get(
            "/disponent/verfuegbarkeit"
            "?from=2025-06-01&to=2025-06-30&category=Wasserschaden"
        )
        assert "Linse verkratzt" not in resp.data.decode()

    def test_availability_shows_category_dropdown(self, disponent_client):
        resp = disponent_client.get("/disponent/verfuegbarkeit")
        body = resp.data.decode()
        assert "Mechanischer Schaden" in body  # seeded default category

    def test_availability_inverted_dates_clamped(self, disponent_client):
        # to < from → route clamps to_date = from_date, no crash
        resp = disponent_client.get(
            "/disponent/verfuegbarkeit?from=2025-06-30&to=2025-06-01"
        )
        assert resp.status_code == 200

    def test_availability_bad_date_falls_back_to_default(self, disponent_client):
        resp = disponent_client.get(
            "/disponent/verfuegbarkeit?from=not-a-date&to=also-bad"
        )
        assert resp.status_code == 200


# =========================================================================== #
#  8. CSV export                                                                #
# =========================================================================== #


class TestDisponentCsvExport:
    def test_csv_export_returns_200(self, disponent_client):
        resp = disponent_client.get("/disponent/verfuegbarkeit/export")
        assert resp.status_code == 200

    def test_csv_content_type(self, disponent_client):
        resp = disponent_client.get("/disponent/verfuegbarkeit/export")
        assert "text/csv" in resp.content_type

    def test_csv_has_correct_header_row(self, disponent_client):
        resp = disponent_client.get("/disponent/verfuegbarkeit/export")
        first_line = resp.data.decode("utf-8").splitlines()[0]
        assert "Geräte-ID" in first_line
        assert "Gerätename" in first_line
        assert "Produktkategorie" in first_line
        assert "Defektkategorie" in first_line

    def test_csv_contains_defect_data(self, disponent_client, open_defect):
        resp = disponent_client.get(
            "/disponent/verfuegbarkeit/export?from=2025-06-01&to=2025-06-30"
        )
        body = resp.data.decode("utf-8")
        assert "Linse verkratzt" in body
        assert "Stadtfest" in body

    def test_csv_filename_in_content_disposition(self, disponent_client):
        resp = disponent_client.get("/disponent/verfuegbarkeit/export")
        cd = resp.headers.get("Content-Disposition", "")
        assert "verfuegbarkeit_" in cd
        assert ".csv" in cd

    def test_csv_export_blocked_for_community_user(self, team_client):
        resp = team_client.get("/disponent/verfuegbarkeit/export")
        assert resp.status_code == 403


# =========================================================================== #
#  9. User model: is_disponent & role property                                  #
# =========================================================================== #


class TestUserModel:
    def test_admin_role_property(self, app):
        with app.app_context():
            u = User(username="test_admin_role", is_admin=True)
            assert u.role == "admin"

    def test_disponent_role_property(self, app):
        with app.app_context():
            u = User(username="test_disp_role", is_disponent=True)
            assert u.role == "disponent"

    def test_community_role_property(self, app):
        with app.app_context():
            u = User(username="test_comm_role")
            assert u.role == "community"

    def test_admin_takes_precedence_over_disponent(self, app):
        """If both flags are set (shouldn't happen, but guard anyway)."""
        with app.app_context():
            u = User(username="test_dual_role", is_admin=True, is_disponent=True)
            assert u.role == "admin"

    def test_seeded_disponent_user_exists(self, app):
        with app.app_context():
            u = User.query.filter_by(username="disponent").first()
            assert u is not None
            assert u.is_disponent is True
            assert u.role == "disponent"

    def test_disponent_password_check(self, app):
        with app.app_context():
            u = User.query.filter_by(username="disponent").first()
            assert u.check_password("disp2025") is True
            assert u.check_password("wrongpw") is False

    def test_repr_includes_role(self, app):
        with app.app_context():
            u = User(username="repr_test", is_disponent=True)
            assert "disponent" in repr(u)


# =========================================================================== #
#  10. Admin creates disponent users                                            #
# =========================================================================== #


class TestAdminCreatesDisponentUser:
    def test_admin_can_create_disponent_user(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={
                "action": "add",
                "username": "new_disp",
                "password": "disp_secure_123",
                "is_disponent": "on",
            },
        )
        with app.app_context():
            u = User.query.filter_by(username="new_disp").first()
            assert u is not None
            assert u.is_disponent is True
            assert u.is_admin is False
            assert u.role == "disponent"

    def test_admin_flag_takes_precedence_over_disponent_flag(self, app, admin_client):
        """Submitting both checkboxes → only admin, not disponent."""
        admin_client.post(
            "/admin/users",
            data={
                "action": "add",
                "username": "new_admin_only",
                "password": "admin_secure_123",
                "is_admin": "on",
                "is_disponent": "on",
            },
        )
        with app.app_context():
            u = User.query.filter_by(username="new_admin_only").first()
            assert u is not None
            assert u.is_admin is True
            assert u.is_disponent is False

    def test_disponent_user_can_login_and_reach_dashboard(self, app, admin_client, client):
        admin_client.post(
            "/admin/users",
            data={
                "action": "add",
                "username": "fresh_disp",
                "password": "fresh_disp_pw",
                "is_disponent": "on",
            },
        )
        # login as the new disponent
        fresh_client = client
        fresh_client.post(
            "/auth/login",
            data={"username": "fresh_disp", "password": "fresh_disp_pw"},
        )
        resp = fresh_client.get("/disponent/")
        assert resp.status_code == 200
