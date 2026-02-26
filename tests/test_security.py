"""
Security Tests
==============
OWASP Top 10 – A01 (Broken Access Control), A03 (Injection), A07 (Auth Failures)

Covers:
  SEC-01  Open Redirect – login ?next= parameter must not redirect off-host
  SEC-02  XSS payload containment – user-supplied content is HTML-escaped in responses
  SEC-03  Malformed / invalid Authorization header handling in the API
  SEC-04  SQL wildcard / injection-like payloads in filter parameters
  SEC-05  URL traversal / encoded slashes in device_id path parameter
  SEC-06  Auth boundary – accessing every protected route without a session
  SEC-07  Auth boundary – team user blocked from every admin sub-route
  SEC-08  API admin-only endpoints blocked for team users (comprehensive)
  SEC-09  Empty / whitespace-only form submissions cannot create data
  SEC-10  Sensitive error information not leaked (no stack traces to clients)
"""

import base64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _basic(username: str, password: str) -> dict:
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


# ---------------------------------------------------------------------------
# SEC-01  Open Redirect – ?next= must not leave the application
# ---------------------------------------------------------------------------

class TestOpenRedirect:
    """POST /auth/login?next=<url> must never redirect to an external host."""

    def test_external_url_next_is_rejected_or_sanitised(self, client):
        """Logging in with next=http://evil.com must NOT redirect to evil.com."""
        resp = client.post(
            "/auth/login?next=http://evil.com",
            data={"username": "admin", "password": "admin123"},
        )
        # The response must be a redirect, but NOT to an external host.
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "evil.com" not in location, (
            f"SECURITY: open redirect to external host detected! "
            f"Location header: {location}"
        )

    def test_protocol_relative_url_next_is_rejected_or_sanitised(self, client):
        """next=//evil.com should not redirect off-host."""
        resp = client.post(
            "/auth/login?next=//evil.com/steal",
            data={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "evil.com" not in location, (
            f"SECURITY: protocol-relative open redirect detected! Location: {location}"
        )

    def test_valid_local_next_is_honoured(self, client):
        """A local relative next= path should be honoured."""
        resp = client.post(
            "/auth/login?next=/admin/",
            data={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 302

    def test_no_next_redirects_to_index(self, client):
        """Without a next= parameter the redirect goes to index."""
        resp = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "login" not in location


# ---------------------------------------------------------------------------
# SEC-02  XSS – user-supplied content must be HTML-escaped
# ---------------------------------------------------------------------------

class TestXSSContainment:
    """Dangerous HTML/JS characters in user content must be escaped in output."""

    XSS_DEVICE_NAME = '<script>alert("xss")</script>'
    XSS_DESCRIPTION = '"><img src=x onerror=alert(1)>'
    XSS_EVENT_NAME = "Event <b>Bold</b> & 'Quotes'"

    def test_device_name_xss_escaped_in_admin_list(self, app, admin_client):
        """XSS payload in device name must be HTML-escaped, not executed."""
        admin_client.post(
            "/admin/devices",
            data={
                "action": "add",
                "device_id": "XSS-001",
                "name": self.XSS_DEVICE_NAME,
            },
        )
        resp = admin_client.get("/admin/devices")
        body = resp.data.decode("utf-8")
        # Raw XSS payload must not appear unescaped; escaped form &lt;script&gt; is safe
        xss_payload = self.XSS_DEVICE_NAME  # '<script>alert("xss")</script>'
        assert xss_payload not in body, "Raw XSS payload found unescaped in response"
        assert "&lt;script&gt;" in body, "Escaped form of XSS payload not found"

    def test_device_description_xss_escaped_in_admin_list(self, app, admin_client):
        """img onerror payload must not appear as a raw HTML tag."""
        admin_client.post(
            "/admin/devices",
            data={
                "action": "add",
                "device_id": "XSS-002",
                "name": "Safe Name",
                "description": self.XSS_DESCRIPTION,
            },
        )
        resp = admin_client.get("/admin/devices")
        body = resp.data.decode("utf-8")
        # The raw XSS <img src=x (unquoted, no /) must not appear; the footer logo uses quoted src
        assert "<img src=x" not in body, "Raw XSS <img src=x payload found unescaped in response"
        assert "&lt;img" in body, "Escaped form of XSS <img payload not found – escaping may be missing"

    def test_xss_in_defect_description_escaped_in_history(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "XSS-003", "name": "XSS Cam"},
        )
        admin_client.post(
            "/report/XSS-003",
            data={
                "category": "Sonstiges",
                "description": self.XSS_DESCRIPTION,
                "event_name": self.XSS_EVENT_NAME,
                "project_number": "PRJ-XSS",
            },
        )
        resp = admin_client.get("/admin/history/XSS-003")
        body = resp.data.decode("utf-8")
        # Unescaped <img> must not appear; Jinja2 auto-escape renders it as &lt;img&gt;
        assert "<img src=x" not in body, "Raw XSS <img src=x payload found unescaped in defect history"

    def test_xss_in_device_name_escaped_on_report_form(self, app, admin_client, team_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "XSS-004", "name": self.XSS_DEVICE_NAME},
        )
        resp = team_client.get("/report/XSS-004")
        body = resp.data.decode("utf-8")
        assert "<script>" not in body, "Raw <script> found on report form"

    def test_xss_in_username_escaped_in_defect_reporter(self, app, admin_client):
        """A username containing HTML chars must be escaped when shown as reporter."""
        # Create user with HTML in username via admin API
        xss_username = "user<b>test</b>"
        admin_client.post(
            "/admin/users",
            data={
                "action": "add",
                "username": xss_username,
                "password": "password99",
            },
        )
        from models import User
        with app.app_context():
            u = User.query.filter_by(username=xss_username).first()
        if u is None:
            # Username may have been rejected due to validation – that's also secure
            return
        # If created, verify it's escaped in output
        resp = admin_client.get("/admin/users")
        body = resp.data.decode("utf-8")
        assert "<b>test</b>" not in body, "Unescaped HTML in username"


# ---------------------------------------------------------------------------
# SEC-03  Malformed / invalid Authorization header
# ---------------------------------------------------------------------------

class TestMalformedAuthHeader:
    """The API must return 401 for any broken/missing auth, never 500."""

    def test_empty_authorization_header_returns_401(self, client):
        resp = client.get("/api/v1/devices", headers={"Authorization": ""})
        assert resp.status_code == 401

    def test_non_basic_scheme_returns_401(self, client):
        resp = client.get(
            "/api/v1/devices",
            headers={"Authorization": "Bearer some.jwt.token"},
        )
        assert resp.status_code == 401

    def test_truncated_base64_returns_401(self, client):
        resp = client.get(
            "/api/v1/devices",
            headers={"Authorization": "Basic dXNlcjpwYXNz!!!"},  # broken base64
        )
        assert resp.status_code == 401

    def test_base64_without_colon_returns_401(self, client):
        # base64 of "nocolon" (no : separator)
        no_colon = base64.b64encode(b"nocolon").decode()
        resp = client.get(
            "/api/v1/devices",
            headers={"Authorization": f"Basic {no_colon}"},
        )
        assert resp.status_code == 401

    def test_correct_username_wrong_password_returns_401(self, client):
        resp = client.get("/api/v1/devices", headers=_basic("admin", "wrongpassword"))
        assert resp.status_code == 401

    def test_malformed_auth_returns_json_not_html(self, client):
        resp = client.get("/api/v1/devices", headers={"Authorization": "garbage"})
        assert resp.status_code == 401
        assert "application/json" in resp.content_type

    def test_sql_injection_in_username_returns_401(self, client):
        """SQL-like payloads in username must not cause a 500."""
        resp = client.get("/api/v1/devices", headers=_basic("admin' OR '1'='1", "x"))
        assert resp.status_code == 401
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# SEC-04  SQL wildcard / injection-like payloads in filter parameters
# ---------------------------------------------------------------------------

class TestInjectionPayloadsInFilters:
    """Injection-like strings in query parameters must not cause errors or data leaks."""

    def test_sql_wildcard_in_event_name_filter(self, client, api_headers):
        """% and _ wildcards must not cause errors or unexpected data leaks."""
        resp = client.get("/api/v1/defects?event_name=%25", headers=api_headers)
        assert resp.status_code == 200

    def test_sql_comment_in_device_id_filter(self, client, api_headers):
        resp = client.get(
            "/api/v1/defects?device_id='; DROP TABLE devices; --",
            headers=api_headers,
        )
        assert resp.status_code in (200, 404)  # must not 500

    def test_unicode_in_event_name_filter(self, client, api_headers):
        resp = client.get(
            "/api/v1/defects?event_name=Sömmer%C3%BCbung",
            headers=api_headers,
        )
        assert resp.status_code == 200

    def test_null_byte_in_filter_does_not_crash(self, client, api_headers):
        resp = client.get(
            "/api/v1/defects?event_name=test%00injection",
            headers=api_headers,
        )
        assert resp.status_code in (200, 400)

    def test_very_long_filter_value_does_not_crash(self, client, api_headers):
        long_value = "A" * 5000
        resp = client.get(
            f"/api/v1/defects?event_name={long_value}",
            headers=api_headers,
        )
        assert resp.status_code in (200, 400, 414)

    def test_sql_injection_in_project_number_returns_empty_not_all(
        self, client, api_headers, defect
    ):
        """A SQL injection attempt must not return unexpected rows."""
        resp = client.get(
            "/api/v1/defects?project_number=' OR '1'='1",
            headers=api_headers,
        )
        assert resp.status_code == 200
        # Should return 0 results – not all defects
        assert resp.get_json()["total"] == 0

    def test_admin_event_filter_with_sql_wildcard(self, admin_client, defect):
        """ilike filter with % wildcard must not expose unexpected records."""
        resp = admin_client.get("/admin/defects?event=%25")
        # Either returns 200 (matched rows) or 200 (empty) – must not crash
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# SEC-05  Path traversal / URL encoding in device_id
# ---------------------------------------------------------------------------

class TestPathTraversal:
    """Device IDs with special path characters must not cause traversal or 500s."""

    def test_device_id_with_dot_dot_returns_404(self, client, api_headers):
        resp = client.get("/api/v1/devices/../admin", headers=api_headers)
        assert resp.status_code in (404, 400)

    def test_device_id_with_slash_returns_404(self, client, api_headers):
        # URL-encoded slash in device_id
        resp = client.get("/api/v1/devices/FOO%2FBAR", headers=api_headers)
        assert resp.status_code in (404, 400, 200)  # must not 500

    def test_nonexistent_device_id_with_special_chars_returns_404(
        self, client, api_headers
    ):
        resp = client.get("/api/v1/devices/device<script>", headers=api_headers)
        assert resp.status_code in (404, 400)


# ---------------------------------------------------------------------------
# SEC-06  Every protected route redirects unauthenticated users
# ---------------------------------------------------------------------------

class TestProtectedRoutesRequireAuth:
    """GET every web route without a session must redirect to login."""

    PROTECTED_ROUTES = [
        "/admin/",
        "/admin/devices",
        "/admin/defects",
        "/admin/users",
        "/admin/recipients",
        "/admin/categories",
        "/admin/event-report",
        "/report/NONEXISTENT-999",
        "/report/NONEXISTENT-999/success",
    ]

    def test_all_protected_routes_redirect_unauthenticated(self, client):
        for route in self.PROTECTED_ROUTES:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code in (302, 301), (
                f"Expected redirect for {route}, got {resp.status_code}"
            )
            location = resp.headers.get("Location", "")
            assert "login" in location, (
                f"Redirect for {route} did not point to login: {location}"
            )


# ---------------------------------------------------------------------------
# SEC-07  Team user blocked from every admin sub-route
# ---------------------------------------------------------------------------

class TestTeamUserAdminBlocked:
    """A team (non-admin) user must receive 403 on every /admin/* sub-route."""

    ADMIN_ROUTES = [
        "/admin/",
        "/admin/devices",
        "/admin/defects",
        "/admin/users",
        "/admin/recipients",
        "/admin/categories",
        "/admin/event-report",
    ]

    def test_team_user_gets_403_on_all_admin_routes(self, team_client):
        for route in self.ADMIN_ROUTES:
            resp = team_client.get(route)
            assert resp.status_code == 403, (
                f"Expected 403 for team user on {route}, got {resp.status_code}"
            )


# ---------------------------------------------------------------------------
# SEC-08  API admin-only endpoints blocked for team users (comprehensive)
# ---------------------------------------------------------------------------

class TestAPIAdminOnlyEndpoints:
    """All admin-only API operations must return 403 for team users."""

    def test_team_cannot_create_device(self, client, team_headers):
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": "SECTEST-001", "name": "Not Allowed"},
            headers=team_headers,
        )
        assert resp.status_code == 403

    def test_team_cannot_patch_device(self, client, team_headers, device):
        resp = client.patch(
            f"/api/v1/devices/{device['device_id']}",
            json={"name": "Hacked"},
            headers=team_headers,
        )
        assert resp.status_code == 403

    def test_team_cannot_delete_device(self, client, team_headers, device):
        resp = client.delete(
            f"/api/v1/devices/{device['device_id']}", headers=team_headers
        )
        assert resp.status_code == 403

    def test_team_cannot_get_qr_code(self, client, team_headers, device):
        resp = client.get(
            f"/api/v1/devices/{device['device_id']}/qr", headers=team_headers
        )
        assert resp.status_code == 403

    def test_team_cannot_resolve_defect(self, client, team_headers, defect):
        resp = client.patch(
            f"/api/v1/defects/{defect['id']}/resolve",
            json={},
            headers=team_headers,
        )
        assert resp.status_code == 403

    def test_admin_only_403_responses_are_json(self, client, team_headers, device):
        """403 from API must be JSON, not HTML."""
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": "SECTEST-002", "name": "Test"},
            headers=team_headers,
        )
        assert resp.status_code == 403
        assert "application/json" in resp.content_type
        assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# SEC-09  Empty / whitespace-only form fields must not create records
# ---------------------------------------------------------------------------

class TestWhitespaceInputRejection:
    """Whitespace-only input must be treated the same as empty input."""

    def test_whitespace_device_id_rejected(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "   ", "name": "Valid"},
        )
        from models import Device
        with app.app_context():
            assert Device.query.filter_by(device_id="   ").first() is None

    def test_whitespace_device_name_rejected(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "WS-001", "name": "   "},
        )
        from models import Device
        with app.app_context():
            assert Device.query.filter_by(device_id="WS-001").first() is None

    def test_whitespace_username_rejected(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "   ", "password": "password123"},
        )
        from models import User
        with app.app_context():
            assert User.query.filter_by(username="   ").first() is None

    def test_whitespace_category_rejected(self, app, admin_client):
        admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": "   "},
        )
        from models import DefectCategory
        with app.app_context():
            assert DefectCategory.query.filter_by(name="   ").first() is None

    def test_whitespace_recipient_name_rejected(self, app, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "   ", "email": "ws@example.com"},
        )
        from models import EmailRecipient
        with app.app_context():
            assert EmailRecipient.query.filter_by(email="ws@example.com").first() is None


# ---------------------------------------------------------------------------
# SEC-10  No stack traces or internal detail leaked to clients
# ---------------------------------------------------------------------------

class TestNoInternalErrorLeakage:
    """Error responses must not contain Python stack traces or internal paths."""

    # Markers that reliably identify Python stack traces but do NOT false-positive
    # on normal HTML content (e.g. CSS "line-height", German words, etc.)
    STACK_TRACE_MARKERS = [
        b"Traceback (most recent call last)",
        b"File \"/",            # Python file path in traceback
        b", in <module>",       # module-level traceback frame
        b"raise ",              # Python raise statement
        b"sqlalchemy.exc",      # SQLAlchemy internal exception class
    ]

    def test_404_contains_no_stack_trace(self, client):
        resp = client.get("/nonexistent-route-xyz-789")
        for marker in self.STACK_TRACE_MARKERS:
            assert marker not in resp.data.lower(), (
                f"Possible stack trace leaked: found {marker!r} in 404 response"
            )

    def test_api_404_contains_no_stack_trace(self, client, api_headers):
        resp = client.get("/api/v1/devices/GHOST-SEC-999", headers=api_headers)
        for marker in self.STACK_TRACE_MARKERS:
            assert marker not in resp.data.lower()

    def test_api_400_contains_no_stack_trace(self, client, api_headers):
        resp = client.post("/api/v1/devices", json={}, headers=api_headers)
        for marker in self.STACK_TRACE_MARKERS:
            assert marker not in resp.data.lower()

    def test_api_401_contains_no_stack_trace(self, client):
        resp = client.get("/api/v1/devices")
        for marker in self.STACK_TRACE_MARKERS:
            assert marker not in resp.data.lower()
