"""
Tests for authentication routes:
  GET/POST /auth/login
  GET      /auth/logout
  GET      /           (root redirect)
"""


class TestLoginPage:
    def test_login_page_renders(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 200

    def test_login_page_contains_form(self, client):
        resp = client.get("/auth/login")
        assert b"username" in resp.data or b"Benutzername" in resp.data

    def test_valid_admin_login_redirects(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_valid_team_login_redirects(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "team_login", "password": "team2025"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_invalid_password_shows_error(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "admin", "password": "totally_wrong"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Ung" in resp.data.decode("utf-8")  # "Ungültiger"

    def test_unknown_username_shows_error(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "nobody", "password": "anything"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Ung" in resp.data.decode("utf-8")

    def test_already_authenticated_redirects(self, admin_client):
        resp = admin_client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 302


class TestLogout:
    def test_logout_redirects_to_login(self, admin_client):
        resp = admin_client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_logout_unauthenticated_redirects(self, client):
        """Flask-Login redirects unauthenticated users to the login view."""
        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302

    def test_after_logout_protected_routes_redirect(self, admin_client):
        admin_client.get("/auth/logout")
        resp = admin_client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 302


class TestRootRedirect:
    def test_unauthenticated_root_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_admin_root_redirects_to_dashboard(self, admin_client):
        resp = admin_client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/" in resp.headers["Location"]

    def test_team_root_redirects_to_defects(self, team_client):
        resp = team_client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "defects" in resp.headers["Location"]
