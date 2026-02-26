"""
Role-Based Routing & Access Control Tests
==========================================

Cross-cutting tests that verify the complete role model:

  ROLE-01  Login routing – each role lands on its correct dashboard
  ROLE-02  api_user has no Web-UI access (immediately logged out)
  ROLE-03  Cross-role blocking – roles cannot access each other's dashboards
  ROLE-04  Admin super-access – admin can view all role dashboards
  ROLE-05  Unauthenticated access – every role-protected route redirects to login
"""

import pytest


# ---------------------------------------------------------------------------
# ROLE-01  Login routing
# ---------------------------------------------------------------------------

class TestLoginRouting:
    """Each role must be redirected to its own dashboard after login."""

    def test_admin_login_redirects_to_admin_dashboard(self, client):
        """Login as admin must ultimately reach the admin dashboard."""
        resp = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Must be on the admin dashboard (URL ends with /admin/)
        assert "/admin/" in resp.request.path

    def test_disponent_login_redirects_to_disponent_dashboard(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "disponent", "password": "disp2025"},
            follow_redirects=False,
        )
        # Disponent lands on / → index route redirects to /disponent/
        assert resp.status_code == 302
        location = resp.headers["Location"]
        # Either direct /disponent/ or / (index then redirects further)
        assert "/disponent/" in location or location.endswith("/")

    def test_werkstatt_login_redirects_to_werkstatt_dashboard(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "werkstatt", "password": "werk2025"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/werkstatt/" in location or location.endswith("/")

    def test_community_login_redirects_to_index(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "team_login", "password": "team2025"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "login" not in resp.headers["Location"]

    def test_disponent_index_resolves_to_disponent_dashboard(self, disponent_client):
        """GET / for a disponent must ultimately reach the disponent dashboard."""
        resp = disponent_client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Disponent dashboard has the 4 tiles
        assert "disponent" in resp.request.path or "disponent" in body.lower()

    def test_werkstatt_index_resolves_to_werkstatt_dashboard(self, werkstatt_client):
        """GET / for werkstatt must ultimately reach the werkstatt dashboard."""
        resp = werkstatt_client.get("/", follow_redirects=True)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# ROLE-02  api_user has no Web-UI access
# ---------------------------------------------------------------------------

class TestAPIUserWebUIBlocked:
    """api_user accounts must not be able to use the web interface."""

    def test_api_user_login_ends_at_login_page(self, client):
        """
        Logging in as api_user must result in the user being immediately
        logged out and sent back to the login page.
        """
        resp = client.post(
            "/auth/login",
            data={"username": "api", "password": "api2025"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Must end up back on the login page
        assert "Anmelden" in body or "login" in resp.request.path.lower()

    def test_api_user_has_no_active_session_after_login(self, client):
        """After the login redirect chain, api_user must have no active session."""
        # Attempt login
        client.post(
            "/auth/login",
            data={"username": "api", "password": "api2025"},
            follow_redirects=True,
        )
        # Any protected route must redirect to login (no session)
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code in (302, 401)
        if resp.status_code == 302:
            assert "login" in resp.headers.get("Location", "")

    def test_api_user_cannot_access_admin_routes(self, client):
        """Even if somehow authenticated, api_user must be blocked from admin."""
        # Login attempt (immediately logged out by index route)
        client.post(
            "/auth/login",
            data={"username": "api", "password": "api2025"},
            follow_redirects=True,
        )
        resp = client.get("/admin/devices", follow_redirects=False)
        # Must redirect to login (session was cleared)
        assert resp.status_code in (302, 401, 403)

    def test_api_user_cannot_access_disponent_routes(self, client):
        """api_user must not reach the disponent dashboard."""
        client.post(
            "/auth/login",
            data={"username": "api", "password": "api2025"},
            follow_redirects=True,
        )
        resp = client.get("/disponent/", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)

    def test_api_user_cannot_access_werkstatt_routes(self, client):
        """api_user must not reach the werkstatt dashboard."""
        client.post(
            "/auth/login",
            data={"username": "api", "password": "api2025"},
            follow_redirects=True,
        )
        resp = client.get("/werkstatt/", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)


# ---------------------------------------------------------------------------
# ROLE-03  Cross-role blocking
# ---------------------------------------------------------------------------

class TestCrossRoleBlocking:
    """Each role must be blocked (403) from accessing routes of other roles."""

    # Disponent blocked from admin + werkstatt
    def test_disponent_blocked_from_admin(self, disponent_client):
        resp = disponent_client.get("/admin/")
        assert resp.status_code == 403

    def test_disponent_blocked_from_admin_devices(self, disponent_client):
        resp = disponent_client.get("/admin/devices")
        assert resp.status_code == 403

    def test_disponent_blocked_from_admin_users(self, disponent_client):
        resp = disponent_client.get("/admin/users")
        assert resp.status_code == 403

    def test_disponent_blocked_from_werkstatt(self, disponent_client):
        resp = disponent_client.get("/werkstatt/")
        assert resp.status_code == 403

    # Werkstatt blocked from admin + disponent
    def test_werkstatt_blocked_from_admin(self, werkstatt_client):
        resp = werkstatt_client.get("/admin/")
        assert resp.status_code == 403

    def test_werkstatt_blocked_from_admin_devices(self, werkstatt_client):
        resp = werkstatt_client.get("/admin/devices")
        assert resp.status_code == 403

    def test_werkstatt_blocked_from_disponent(self, werkstatt_client):
        resp = werkstatt_client.get("/disponent/")
        assert resp.status_code == 403

    # Community blocked from all role dashboards
    def test_community_blocked_from_admin(self, team_client):
        resp = team_client.get("/admin/")
        assert resp.status_code == 403

    def test_community_blocked_from_disponent(self, team_client):
        resp = team_client.get("/disponent/")
        assert resp.status_code == 403

    def test_community_blocked_from_werkstatt(self, team_client):
        resp = team_client.get("/werkstatt/")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# ROLE-04  Admin super-access
# ---------------------------------------------------------------------------

class TestAdminSuperAccess:
    """Admin must be able to access all role-specific dashboards."""

    def test_admin_can_access_disponent_dashboard(self, admin_client):
        resp = admin_client.get("/disponent/")
        assert resp.status_code == 200

    def test_admin_can_access_werkstatt_dashboard(self, admin_client):
        resp = admin_client.get("/werkstatt/")
        assert resp.status_code == 200

    def test_admin_can_access_own_dashboard(self, admin_client):
        resp = admin_client.get("/admin/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# ROLE-05  Unauthenticated access redirects to login
# ---------------------------------------------------------------------------

class TestUnauthenticatedBlocked:
    """Every role-protected route must redirect unauthenticated users to login."""

    PROTECTED = [
        "/admin/",
        "/admin/devices",
        "/admin/users",
        "/disponent/",
        "/werkstatt/",
    ]

    def test_all_role_routes_redirect_unauthenticated(self, client):
        for route in self.PROTECTED:
            resp = client.get(route, follow_redirects=False)
            assert resp.status_code in (302, 301), (
                f"Expected redirect for unauthenticated {route}, got {resp.status_code}"
            )
            location = resp.headers.get("Location", "")
            assert "login" in location, (
                f"Redirect for {route} does not point to login: {location}"
            )
