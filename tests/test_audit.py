"""
Audit Trail Tests  (NFR-SEC-003)
================================
Verifies that every create / update / delete operation on core entities
is recorded in the AuditLog table and that the admin audit-log view works.
"""

import json

import pytest

from models import AuditLog, Defect, Device, User, db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_audit(app, entity_type: str, action: str | None = None) -> AuditLog | None:
    """Return the most recent AuditLog entry for the given entity_type."""
    with app.app_context():
        q = AuditLog.query.filter_by(entity_type=entity_type)
        if action:
            q = q.filter_by(action=action)
        return q.order_by(AuditLog.timestamp.desc()).first()


# ---------------------------------------------------------------------------
# NFR-SEC-003  Device audit entries
# ---------------------------------------------------------------------------

class TestDeviceAudit:
    """Every device write operation must produce an AuditLog entry."""

    def test_device_create_via_admin_logs_create(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "AUDIT-001", "name": "Audit Cam"},
        )
        entry = _latest_audit(app, "Device", "CREATE")
        assert entry is not None, "No CREATE AuditLog entry found for Device"
        assert entry.entity_id == "AUDIT-001"

    def test_device_create_logs_new_value(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "AUDIT-002", "name": "Audit Cam 2"},
        )
        entry = _latest_audit(app, "Device", "CREATE")
        assert entry is not None
        new_val = json.loads(entry.new_value)
        assert new_val.get("device_id") == "AUDIT-002"
        assert new_val.get("name") == "Audit Cam 2"

    def test_device_delete_via_admin_logs_delete(self, app, admin_client, device):
        admin_client.post(
            "/admin/devices",
            data={"action": "delete", "dev_id": str(device["id"])},
        )
        entry = _latest_audit(app, "Device", "DELETE")
        assert entry is not None, "No DELETE AuditLog entry found for Device"

    def test_device_delete_logs_old_value(self, app, admin_client, device):
        admin_client.post(
            "/admin/devices",
            data={"action": "delete", "dev_id": str(device["id"])},
        )
        entry = _latest_audit(app, "Device", "DELETE")
        assert entry is not None
        old_val = json.loads(entry.old_value)
        assert old_val.get("device_id") == device["device_id"]

    def test_device_create_via_api_logs_create(self, app, client, api_headers):
        client.post(
            "/api/v1/devices",
            json={"device_id": "AUDIT-API-001", "name": "API Audit Device"},
            headers=api_headers,
        )
        entry = _latest_audit(app, "Device", "CREATE")
        assert entry is not None
        assert entry.entity_id == "AUDIT-API-001"

    def test_device_update_via_api_logs_update(self, app, client, api_headers, device):
        client.patch(
            f"/api/v1/devices/{device['device_id']}",
            json={"name": "Updated Name"},
            headers=api_headers,
        )
        entry = _latest_audit(app, "Device", "UPDATE")
        assert entry is not None

    def test_device_delete_via_api_logs_delete(self, app, client, api_headers, device):
        client.delete(
            f"/api/v1/devices/{device['device_id']}",
            headers=api_headers,
        )
        entry = _latest_audit(app, "Device", "DELETE")
        assert entry is not None
        assert entry.entity_id == device["device_id"]

    def test_device_status_change_via_disponent_logs_update(
        self, app, disponent_client, device
    ):
        disponent_client.post(
            f"/disponent/geraet/{device['id']}/status",
            data={"status": "Reserviert"},
        )
        entry = _latest_audit(app, "Device", "UPDATE")
        assert entry is not None
        new_val = json.loads(entry.new_value)
        assert new_val.get("status") == "Reserviert"


# ---------------------------------------------------------------------------
# NFR-SEC-003  Defect audit entries
# ---------------------------------------------------------------------------

class TestDefectAudit:
    """Defect resolve operations must be logged."""

    def test_defect_resolve_via_admin_logs_update(self, app, admin_client, defect):
        admin_client.post(
            f"/admin/repair/{defect['id']}",
            data={"resolution_notes": "Fixed the housing"},
        )
        entry = _latest_audit(app, "Defect", "UPDATE")
        assert entry is not None, "No UPDATE AuditLog entry found for Defect"

    def test_defect_resolve_logs_old_and_new_status(self, app, admin_client, defect):
        admin_client.post(
            f"/admin/repair/{defect['id']}",
            data={"resolution_notes": "Repaired"},
        )
        entry = _latest_audit(app, "Defect", "UPDATE")
        assert entry is not None
        old_val = json.loads(entry.old_value)
        new_val = json.loads(entry.new_value)
        assert old_val.get("status") == "Offen"
        assert new_val.get("status") == "Behoben"

    def test_defect_resolve_via_api_logs_update(self, app, client, api_headers, defect):
        client.patch(
            f"/api/v1/defects/{defect['id']}/resolve",
            json={"resolution_notes": "API resolved"},
            headers=api_headers,
        )
        entry = _latest_audit(app, "Defect", "UPDATE")
        assert entry is not None
        assert str(defect["id"]) == entry.entity_id


# ---------------------------------------------------------------------------
# NFR-SEC-003  User audit entries
# ---------------------------------------------------------------------------

class TestUserAudit:
    """User management operations must be logged."""

    def test_user_create_logs_create(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "audit_user1", "password": "password99"},
        )
        entry = _latest_audit(app, "User", "CREATE")
        assert entry is not None, "No CREATE AuditLog entry for User"
        assert entry.entity_id == "audit_user1"

    def test_user_create_logs_username_in_new_value(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "audit_user2", "password": "password99"},
        )
        entry = _latest_audit(app, "User", "CREATE")
        assert entry is not None
        new_val = json.loads(entry.new_value)
        assert new_val.get("username") == "audit_user2"

    def test_user_delete_logs_delete(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "audit_del_user", "password": "password99"},
        )
        with app.app_context():
            u = User.query.filter_by(username="audit_del_user").first()
            uid = u.id

        admin_client.post(
            "/admin/users",
            data={"action": "delete", "user_id": str(uid)},
        )
        entry = _latest_audit(app, "User", "DELETE")
        assert entry is not None, "No DELETE AuditLog entry for User"

    def test_password_change_logs_update(self, app, admin_client):
        admin_client.post(
            "/admin/users",
            data={"action": "add", "username": "audit_pw_user", "password": "password99"},
        )
        with app.app_context():
            u = User.query.filter_by(username="audit_pw_user").first()
            uid = u.id

        admin_client.post(
            "/admin/users",
            data={"action": "change_password", "user_id": str(uid), "new_password": "newpassword99"},
        )
        entry = _latest_audit(app, "User", "UPDATE")
        assert entry is not None, "No UPDATE AuditLog entry for User password change"
        new_val = json.loads(entry.new_value)
        assert new_val.get("action") == "password_changed"


# ---------------------------------------------------------------------------
# NFR-SEC-003  Audit entry metadata
# ---------------------------------------------------------------------------

class TestAuditMetadata:
    """Audit entries must record the acting user and IP address."""

    def test_audit_records_acting_username(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "META-001", "name": "Meta Cam"},
        )
        entry = _latest_audit(app, "Device", "CREATE")
        assert entry is not None
        assert entry.username == "admin"

    def test_audit_records_ip_address(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "META-002", "name": "IP Cam"},
        )
        entry = _latest_audit(app, "Device", "CREATE")
        assert entry is not None
        assert entry.ip_address is not None

    def test_api_audit_records_api_username(self, app, client, api_headers):
        client.post(
            "/api/v1/devices",
            json={"device_id": "META-API-001", "name": "API Meta Cam"},
            headers=api_headers,
        )
        entry = _latest_audit(app, "Device", "CREATE")
        assert entry is not None
        assert entry.username == "api"

    def test_audit_entry_has_timestamp(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "META-003", "name": "Timestamp Cam"},
        )
        entry = _latest_audit(app, "Device", "CREATE")
        assert entry is not None
        assert entry.timestamp is not None


# ---------------------------------------------------------------------------
# NFR-SEC-003  Admin audit-log view
# ---------------------------------------------------------------------------

class TestAdminAuditView:
    """The /admin/audit page must be accessible to admins and show entries."""

    def test_audit_page_accessible_to_admin(self, admin_client):
        resp = admin_client.get("/admin/audit")
        assert resp.status_code == 200

    def test_audit_page_blocked_for_team_user(self, team_client):
        resp = team_client.get("/admin/audit")
        assert resp.status_code == 403

    def test_audit_page_shows_entries_after_create(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "VIEW-001", "name": "View Cam"},
        )
        resp = admin_client.get("/admin/audit")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "CREATE" in body

    def test_audit_page_filter_by_action(self, admin_client):
        resp = admin_client.get("/admin/audit?action=CREATE")
        assert resp.status_code == 200

    def test_audit_page_filter_by_entity(self, admin_client):
        resp = admin_client.get("/admin/audit?entity=Device")
        assert resp.status_code == 200

    def test_audit_page_unauthenticated_redirects(self, client):
        resp = client.get("/admin/audit", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers.get("Location", "").lower()
