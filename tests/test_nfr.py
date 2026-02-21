"""
Non-Functional Requirements (NFR) Tests
========================================
Covers: security headers · API response contract · cascade delete ·
        password policy · config validation · DB integrity · error handlers
"""

import pytest
from datetime import datetime

from models import db, Defect, Device, User


# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    """Every HTTP response must carry the required defensive headers."""

    REQUIRED = {
        "X-Frame-Options":        "SAMEORIGIN",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy":        "strict-origin-when-cross-origin",
    }

    def _assert_headers(self, resp):
        for header, value in self.REQUIRED.items():
            assert header in resp.headers, f"Missing header: {header}"
            assert resp.headers[header] == value, (
                f"{header}: expected '{value}', got '{resp.headers[header]}'"
            )

    def test_headers_on_login_page(self, client):
        self._assert_headers(client.get("/auth/login"))

    def test_headers_on_admin_dashboard(self, admin_client):
        self._assert_headers(admin_client.get("/admin/"))

    def test_headers_on_api_response(self, client, admin_headers):
        self._assert_headers(client.get("/api/v1/devices", headers=admin_headers))

    def test_headers_on_404_error(self, client):
        self._assert_headers(client.get("/this-route-does-not-exist-xyz"))

    def test_headers_on_report_form(self, admin_client, device):
        self._assert_headers(admin_client.get(f"/report/{device['device_id']}"))

    def test_permissions_policy_present(self, client):
        resp = client.get("/auth/login")
        assert "Permissions-Policy" in resp.headers
        assert "geolocation=()" in resp.headers["Permissions-Policy"]

    def test_no_hsts_in_test_environment(self, client):
        """HSTS must NOT be set when APP_BASE_URL is http:// (test env)."""
        resp = client.get("/auth/login")
        assert "Strict-Transport-Security" not in resp.headers


# ---------------------------------------------------------------------------
# API 401 WWW-Authenticate
# ---------------------------------------------------------------------------

class TestWWWAuthenticate:
    """Unauthenticated API requests must return WWW-Authenticate header."""

    def test_www_authenticate_on_401(self, client):
        resp = client.get("/api/v1/devices")
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers
        assert 'Basic realm="Redline API"' in resp.headers["WWW-Authenticate"]

    def test_www_authenticate_on_bad_credentials(self, client):
        import base64
        bad = base64.b64encode(b"admin:wrongpassword").decode()
        resp = client.get("/api/v1/devices", headers={"Authorization": f"Basic {bad}"})
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers

    def test_no_www_authenticate_on_200(self, client, admin_headers):
        resp = client.get("/api/v1/devices", headers=admin_headers)
        assert resp.status_code == 200
        assert "WWW-Authenticate" not in resp.headers


# ---------------------------------------------------------------------------
# API Response Contract
# ---------------------------------------------------------------------------

class TestAPIResponseContract:
    """API responses must be well-formed JSON with consistent shapes."""

    def test_error_responses_contain_error_key(self, client, admin_headers):
        cases = [
            client.get("/api/v1/devices"),                               # 401
            client.get("/api/v1/devices/GHOST-999", headers=admin_headers),  # 404
            client.post("/api/v1/devices", json={}, headers=admin_headers),  # 400
        ]
        for resp in cases:
            data = resp.get_json()
            assert data is not None, "Response body is not JSON"
            assert "error" in data, f"'error' key missing in: {data}"

    def test_successful_responses_are_json(self, client, admin_headers, device):
        endpoints = [
            "/api/v1/devices",
            f"/api/v1/devices/{device['device_id']}",
            "/api/v1/defects",
            "/api/v1/events",
        ]
        for url in endpoints:
            resp = client.get(url, headers=admin_headers)
            assert resp.status_code == 200
            assert "application/json" in resp.content_type, (
                f"Wrong content-type for {url}: {resp.content_type}"
            )

    def test_delete_returns_empty_body_204(self, client, admin_headers, device):
        resp = client.delete(
            f"/api/v1/devices/{device['device_id']}", headers=admin_headers
        )
        assert resp.status_code == 204
        assert resp.data == b""

    def test_device_response_has_all_required_fields(self, client, admin_headers, device):
        resp = client.get(f"/api/v1/devices/{device['device_id']}", headers=admin_headers)
        required = {"device_id", "name", "description", "status",
                    "open_defect_count", "created_at"}
        assert required.issubset(resp.get_json().keys())

    def test_defect_response_has_all_required_fields(self, client, admin_headers, defect):
        resp = client.get(f"/api/v1/defects/{defect['id']}", headers=admin_headers)
        required = {
            "id", "device_id", "device_name", "category", "description",
            "event_name", "project_number", "status", "reporter",
            "created_at", "resolved_at", "resolution_notes",
        }
        assert required.issubset(resp.get_json().keys())

    def test_defect_list_has_pagination_envelope(self, client, admin_headers):
        resp = client.get("/api/v1/defects", headers=admin_headers)
        data = resp.get_json()
        for key in ("items", "total", "page", "per_page", "pages"):
            assert key in data, f"Pagination key '{key}' missing"

    def test_per_page_capped_at_200(self, client, admin_headers):
        resp = client.get("/api/v1/defects?per_page=9999", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["per_page"] <= 200

    def test_default_page_is_1(self, client, admin_headers):
        resp = client.get("/api/v1/defects", headers=admin_headers)
        assert resp.get_json()["page"] == 1

    def test_created_at_is_iso8601(self, client, admin_headers, defect):
        resp = client.get(f"/api/v1/defects/{defect['id']}", headers=admin_headers)
        ts = resp.get_json()["created_at"]
        # Must parse without raising
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None

    def test_resolved_at_is_null_when_open(self, client, admin_headers, defect):
        resp = client.get(f"/api/v1/defects/{defect['id']}", headers=admin_headers)
        assert resp.get_json()["resolved_at"] is None

    def test_resolved_at_is_set_after_resolution(self, client, admin_headers, defect):
        client.patch(
            f"/api/v1/defects/{defect['id']}/resolve",
            json={"resolution_notes": "fixed"},
            headers=admin_headers,
        )
        resp = client.get(f"/api/v1/defects/{defect['id']}", headers=admin_headers)
        ts = resp.get_json()["resolved_at"]
        assert ts is not None
        datetime.fromisoformat(ts)  # must be valid ISO 8601

    def test_validation_error_includes_fields_map(self, client, admin_headers, device):
        resp = client.post(
            "/api/v1/defects",
            json={"device_id": device["device_id"]},   # missing required fields
            headers=admin_headers,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "fields" in data
        assert isinstance(data["fields"], dict)


# ---------------------------------------------------------------------------
# Cascade Delete
# ---------------------------------------------------------------------------

class TestCascadeDelete:
    """Deleting a device must automatically delete all its defect records."""

    def test_single_defect_deleted_with_device(self, app, client, admin_headers, defect):
        defect_id = defect["id"]
        resp = client.delete(
            f"/api/v1/devices/{defect['device_id']}", headers=admin_headers
        )
        assert resp.status_code == 204
        with app.app_context():
            assert db.session.get(Defect, defect_id) is None

    def test_multiple_defects_deleted_with_device(self, app, client, admin_headers, device):
        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            ids = []
            for i in range(3):
                df = Defect(
                    device_id=dev.id,
                    category="Sonstiges",
                    description=f"Cascade defect {i}",
                    event_name="Cascade Test",
                    project_number="PRJ-CASCADE",
                    reporter="admin",
                )
                db.session.add(df)
            db.session.commit()
            ids = [d.id for d in dev.defects]

        resp = client.delete(
            f"/api/v1/devices/{device['device_id']}", headers=admin_headers
        )
        assert resp.status_code == 204

        with app.app_context():
            for did in ids:
                assert db.session.get(Defect, did) is None

    def test_device_gone_after_delete(self, app, client, admin_headers, device):
        client.delete(f"/api/v1/devices/{device['device_id']}", headers=admin_headers)
        with app.app_context():
            assert Device.query.filter_by(device_id=device["device_id"]).first() is None


# ---------------------------------------------------------------------------
# Password Policy
# ---------------------------------------------------------------------------

class TestPasswordPolicy:
    """Minimum 8-character password enforced in admin user management."""

    def test_password_shorter_than_8_rejected(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "shortpw_nfr", "password": "abc"},
        )
        with app.app_context():
            assert User.query.filter_by(username="shortpw_nfr").first() is None

    def test_exactly_7_chars_rejected(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "sevenpw_nfr", "password": "seven77"},
        )
        with app.app_context():
            assert User.query.filter_by(username="sevenpw_nfr").first() is None

    def test_exactly_8_chars_accepted(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "eightpw_nfr", "password": "eight123"},
        )
        with app.app_context():
            assert User.query.filter_by(username="eightpw_nfr").first() is not None

    def test_flash_message_on_short_password(self, admin_client):
        resp = admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "shortmsg_nfr", "password": "abc"},
            follow_redirects=True,
        )
        assert "mindestens" in resp.data.decode("utf-8").lower()

    def test_change_password_minimum_enforced(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "pwchange_nfr", "password": "validpass1"},
        )
        with app.app_context():
            uid = User.query.filter_by(username="pwchange_nfr").first().id

        admin_client.post(
            "/admin/users",
            data={"action": "change_password", "user_id": uid, "new_password": "short"},
        )
        with app.app_context():
            u = User.query.filter_by(username="pwchange_nfr").first()
            assert u.check_password("validpass1") is True
            assert u.check_password("short") is False


# ---------------------------------------------------------------------------
# Configuration Validation (TestConfig)
# ---------------------------------------------------------------------------

class TestConfigNFR:
    """The TestConfig must have the correct safety overrides."""

    def test_csrf_disabled_in_tests(self, app):
        assert app.config["WTF_CSRF_ENABLED"] is False

    def test_mail_suppressed_in_tests(self, app):
        assert app.config["MAIL_SUPPRESS_SEND"] is True

    def test_in_memory_db_in_tests(self, app):
        assert ":memory:" in app.config["SQLALCHEMY_DATABASE_URI"]

    def test_rate_limiting_disabled_in_tests(self, app):
        assert app.config.get("RATELIMIT_ENABLED") is False

    def test_app_base_url_is_testserver(self, app):
        assert app.config["APP_BASE_URL"] == "http://testserver"

    def test_secret_key_is_set_and_non_empty(self, app):
        sk = app.config["SECRET_KEY"]
        assert sk is not None
        assert len(sk) > 8

    def test_9_default_categories_seeded(self, app):
        from config import Config
        from models import DefectCategory
        with app.app_context():
            count = DefectCategory.query.filter(
                DefectCategory.name.in_(Config.DEFECT_CATEGORIES)
            ).count()
            assert count == 9


# ---------------------------------------------------------------------------
# Rate Limiting disabled in tests
# ---------------------------------------------------------------------------

class TestRateLimitingDisabled:
    """With RATELIMIT_ENABLED=False, repeated requests must not get 429."""

    def test_repeated_login_attempts_not_throttled(self, client):
        for _ in range(20):
            resp = client.post(
                "/auth/login",
                data={"username": "admin", "password": "wrongpassword"},
            )
            assert resp.status_code == 200, (
                f"Got unexpected {resp.status_code} on attempt – rate limiter active?"
            )


# ---------------------------------------------------------------------------
# Database Integrity
# ---------------------------------------------------------------------------

class TestDatabaseIntegrity:
    """DB constraints must prevent invalid data from being committed."""

    def test_defect_fk_references_existing_device(self, app):
        with app.app_context():
            # SQLite requires an explicit PRAGMA per connection to enforce FK constraints
            from sqlalchemy import text
            db.session.execute(text("PRAGMA foreign_keys=ON"))
            df = Defect(
                device_id=99999,  # nonexistent
                category="Sonstiges",
                description="Orphan",
                event_name="Test",
                project_number="PRJ-X",
            )
            db.session.add(df)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_device_created_at_set_automatically(self, app, device):
        with app.app_context():
            d = Device.query.filter_by(device_id=device["device_id"]).first()
            assert d.created_at is not None

    def test_defect_created_at_set_automatically(self, app, defect):
        with app.app_context():
            df = db.session.get(Defect, defect["id"])
            assert df.created_at is not None

    def test_duplicate_device_id_raises(self, app):
        with app.app_context():
            d1 = Device(device_id="DUP-NFR-001", name="Original")
            d2 = Device(device_id="DUP-NFR-001", name="Kopie")
            db.session.add(d1)
            db.session.commit()
            db.session.add(d2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_duplicate_username_raises(self, app):
        with app.app_context():
            u1 = User(username="dupnfr")
            u1.set_password("password123")
            u2 = User(username="dupnfr")
            u2.set_password("password456")
            db.session.add(u1)
            db.session.commit()
            db.session.add(u2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

class TestErrorHandlers:
    """Error pages must return correct status codes and render the error template."""

    def test_404_returns_correct_status(self, client):
        resp = client.get("/nonexistent-route-abc-xyz")
        assert resp.status_code == 404

    def test_404_renders_error_template(self, client):
        resp = client.get("/nonexistent-route-abc-xyz")
        assert b"nicht gefunden" in resp.data.lower() or b"not found" in resp.data.lower()

    def test_403_returned_for_non_admin_on_admin_route(self, team_client):
        resp = team_client.get("/admin/")
        assert resp.status_code == 403

    def test_403_renders_error_template(self, team_client):
        resp = team_client.get("/admin/")
        assert resp.status_code == 403
        assert b"zugriff" in resp.data.lower() or b"forbidden" in resp.data.lower()

    def test_api_403_is_json(self, client, team_headers):
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": "X-001", "name": "Test"},
            headers=team_headers,
        )
        assert resp.status_code == 403
        assert "application/json" in resp.content_type
        assert "error" in resp.get_json()
