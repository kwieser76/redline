"""
Business Workflow Tests
========================
End-to-end scenarios that mirror real business processes:

  BW-01  Full defect lifecycle (report → resolve → device available)
  BW-02  Multi-defect device (stays in Wartung until ALL resolved)
  BW-03  Event reporting and filtering
  BW-04  Email recipient workflow (active/inactive in mailto URL)
  BW-05  Access control – technician vs. admin
  BW-06  Category management (add, delete, reorder)
  BW-07  QR code encodes correct URL
  BW-08  Admin self-protection rules
  BW-09  Defect reporter captured correctly (web + API)
  BW-10  Device onboarding workflow
"""

from models import db, Defect, Device, DefectCategory, EmailRecipient, User


# ---------------------------------------------------------------------------
# BW-01  Full defect lifecycle
# ---------------------------------------------------------------------------

class TestDefectLifecycle:
    """Report a defect, then resolve it and verify the device becomes available."""

    def _create_device(self, admin_client, device_id="LC-001", name="Lifecycle Cam"):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": device_id, "name": name},
        )

    def test_device_starts_as_verfuegbar(self, app, admin_client):
        self._create_device(admin_client)
        with app.app_context():
            d = Device.query.filter_by(device_id="LC-001").first()
            assert d.status == "Verfügbar"

    def test_reporting_defect_sets_device_to_wartung(self, app, admin_client, team_client):
        self._create_device(admin_client, "LC-002")
        team_client.post(
            "/report/LC-002",
            data={
                "category": "Sonstiges",
                "description": "Kleiner Kratzer",
                "event_name": "LC Event",
                "project_number": "PRJ-LC-001",
            },
        )
        with app.app_context():
            d = Device.query.filter_by(device_id="LC-002").first()
            assert d.status == "Wartung"

    def test_defect_status_is_offen_after_report(self, app, admin_client, team_client):
        self._create_device(admin_client, "LC-003")
        team_client.post(
            "/report/LC-003",
            data={
                "category": "Sonstiges",
                "description": "Kratzer am Gehäuse",
                "event_name": "LC Event",
                "project_number": "PRJ-LC-002",
            },
        )
        with app.app_context():
            dev = Device.query.filter_by(device_id="LC-003").first()
            df = Defect.query.filter_by(device_id=dev.id).first()
            assert df is not None
            assert df.status == "Offen"
            assert df.resolved_at is None

    def test_resolving_defect_sets_it_to_behoben(self, app, admin_client, defect):
        with app.app_context():
            df_id = defect["id"]

        admin_client.post(
            f"/admin/repair/{df_id}",
            data={"resolution_notes": "Repariert"},
        )
        with app.app_context():
            df = db.session.get(Defect, df_id)
            assert df.status == "Behoben"
            assert df.resolved_at is not None
            assert df.resolution_notes == "Repariert"

    def test_resolving_last_defect_restores_device_to_verfuegbar(
        self, app, admin_client, defect
    ):
        admin_client.post(
            f"/admin/repair/{defect['id']}",
            data={"resolution_notes": "OK"},
        )
        with app.app_context():
            d = Device.query.filter_by(device_id=defect["device_id"]).first()
            assert d.status == "Verfügbar"

    def test_full_api_lifecycle(self, app, client, api_headers):
        """Complete lifecycle via REST API."""
        # Create device
        r = client.post(
            "/api/v1/devices",
            json={"device_id": "API-LC-001", "name": "API Lifecycle Device"},
            headers=api_headers,
        )
        assert r.status_code == 201
        assert r.get_json()["status"] == "Verfügbar"

        # Report defect
        r = client.post(
            "/api/v1/defects",
            json={
                "device_id": "API-LC-001",
                "category": "Sonstiges",
                "description": "API lifecycle test",
                "event_name": "API Event",
                "project_number": "PRJ-API-LC",
            },
            headers=api_headers,
        )
        assert r.status_code == 201
        defect_id = r.get_json()["id"]

        # Verify device in Wartung
        r = client.get("/api/v1/devices/API-LC-001", headers=api_headers)
        assert r.get_json()["status"] == "Wartung"

        # Resolve defect
        r = client.patch(
            f"/api/v1/defects/{defect_id}/resolve",
            json={"resolution_notes": "Behoben via API"},
            headers=api_headers,
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "Behoben"

        # Verify device back to Verfügbar
        r = client.get("/api/v1/devices/API-LC-001", headers=api_headers)
        assert r.get_json()["status"] == "Verfügbar"


# ---------------------------------------------------------------------------
# BW-02  Multi-defect device
# ---------------------------------------------------------------------------

class TestMultiDefectDevice:
    """Device stays in Wartung until every open defect is resolved."""

    def _report_defect(self, client, headers, device_id, desc):
        return client.post(
            "/api/v1/defects",
            json={
                "device_id": device_id,
                "category": "Sonstiges",
                "description": desc,
                "event_name": "Multi-Defect Event",
                "project_number": "PRJ-MULTI",
            },
            headers=headers,
        )

    def test_device_stays_wartung_when_one_defect_remains(
        self, app, client, api_headers, device
    ):
        # Report 2 defects
        r1 = self._report_defect(client, api_headers, device["device_id"], "Defect A")
        r2 = self._report_defect(client, api_headers, device["device_id"], "Defect B")
        id1, id2 = r1.get_json()["id"], r2.get_json()["id"]

        # Resolve only the first
        client.patch(
            f"/api/v1/defects/{id1}/resolve",
            json={"resolution_notes": "fixed A"},
            headers=api_headers,
        )

        with app.app_context():
            d = Device.query.filter_by(device_id=device["device_id"]).first()
            assert d.status == "Wartung", "Device should still be in Wartung"
            assert d.open_defect_count == 1

    def test_device_becomes_verfuegbar_when_all_resolved(
        self, app, client, api_headers, device
    ):
        r1 = self._report_defect(client, api_headers, device["device_id"], "Defect X")
        r2 = self._report_defect(client, api_headers, device["device_id"], "Defect Y")
        id1, id2 = r1.get_json()["id"], r2.get_json()["id"]

        client.patch(f"/api/v1/defects/{id1}/resolve", json={}, headers=api_headers)
        client.patch(f"/api/v1/defects/{id2}/resolve", json={}, headers=api_headers)

        with app.app_context():
            d = Device.query.filter_by(device_id=device["device_id"]).first()
            assert d.status == "Verfügbar"
            assert d.open_defect_count == 0

    def test_open_defect_count_is_accurate(self, app, client, api_headers, device):
        self._report_defect(client, api_headers, device["device_id"], "One")
        self._report_defect(client, api_headers, device["device_id"], "Two")
        self._report_defect(client, api_headers, device["device_id"], "Three")

        with app.app_context():
            d = Device.query.filter_by(device_id=device["device_id"]).first()
            assert d.open_defect_count == 3


# ---------------------------------------------------------------------------
# BW-03  Event reporting and filtering
# ---------------------------------------------------------------------------

class TestEventReporting:
    """Event-based filtering and defect aggregation."""

    def _create_defect(self, client, headers, device_id, event, project, desc="Test"):
        return client.post(
            "/api/v1/defects",
            json={
                "device_id": device_id,
                "category": "Sonstiges",
                "description": desc,
                "event_name": event,
                "project_number": project,
            },
            headers=headers,
        )

    def test_events_endpoint_lists_distinct_projects(
        self, client, api_headers, device
    ):
        self._create_defect(client, api_headers, device["device_id"],
                            "Summer Fest", "PRJ-SF-01")
        self._create_defect(client, api_headers, device["device_id"],
                            "Winter Gala", "PRJ-WG-01")

        resp = client.get("/api/v1/events", headers=api_headers)
        projects = [e["project_number"] for e in resp.get_json()]
        assert "PRJ-SF-01" in projects
        assert "PRJ-WG-01" in projects

    def test_event_defects_returns_correct_count(
        self, client, api_headers, device
    ):
        for i in range(3):
            self._create_defect(
                client, api_headers, device["device_id"],
                "Summer Fest", "PRJ-COUNT-01", f"Defect {i}"
            )
        resp = client.get("/api/v1/events/PRJ-COUNT-01", headers=api_headers)
        assert resp.get_json()["defect_count"] == 3

    def test_defect_filter_by_status_offen(
        self, client, api_headers, device
    ):
        r = self._create_defect(client, api_headers, device["device_id"],
                                "Filter Event", "PRJ-FILT-01")
        defect_id = r.get_json()["id"]

        # Open defects
        resp = client.get(
            "/api/v1/defects?status=Offen&project_number=PRJ-FILT-01",
            headers=api_headers,
        )
        assert resp.get_json()["total"] == 1

        # Resolve, then filter again
        client.patch(
            f"/api/v1/defects/{defect_id}/resolve", json={}, headers=api_headers
        )
        resp = client.get(
            "/api/v1/defects?status=Offen&project_number=PRJ-FILT-01",
            headers=api_headers,
        )
        assert resp.get_json()["total"] == 0

    def test_event_filter_by_event_name_partial_match(
        self, client, api_headers, device
    ):
        self._create_defect(client, api_headers, device["device_id"],
                            "Sommerfestival 2025", "PRJ-PART-01")
        resp = client.get(
            "/api/v1/defects?event_name=Sommer", headers=api_headers
        )
        assert resp.get_json()["total"] >= 1

    def test_admin_defects_page_filter_by_status(self, admin_client, defect):
        resp = admin_client.get("/admin/defects?status=Offen")
        assert resp.status_code == 200
        assert "Sommerfestival" in resp.data.decode("utf-8")

    def test_admin_defects_page_filter_by_event(self, admin_client, defect):
        resp = admin_client.get("/admin/defects?event=Sommer")
        assert resp.status_code == 200
        assert "Sommerfestival" in resp.data.decode("utf-8")


# ---------------------------------------------------------------------------
# BW-04  Email recipient workflow
# ---------------------------------------------------------------------------

class TestEmailRecipientWorkflow:
    """Manage recipients and verify only active ones appear in mailto URL."""

    def test_add_recipient_appears_in_db(self, app, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "BW Empfänger", "email": "bw@example.com"},
        )
        with app.app_context():
            r = EmailRecipient.query.filter_by(email="bw@example.com").first()
            assert r is not None
            assert r.active is True

    def test_deactivated_recipient_excluded_from_mailto_url(
        self, app, admin_client, team_client, device
    ):
        # Add and immediately deactivate
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "Inactive", "email": "inactive@example.com"},
        )
        with app.app_context():
            rec = EmailRecipient.query.filter_by(email="inactive@example.com").first()
            rec_id = rec.id

        admin_client.post(
            "/admin/recipients",
            data={"action": "toggle", "rec_id": rec_id},
        )

        # Submit defect, check success page
        team_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Sonstiges",
                "description": "Test für Empfänger",
                "event_name": "BW Event",
                "project_number": "PRJ-BW-01",
            },
        )
        resp = team_client.get(f"/report/{device['device_id']}/success")
        assert "inactive@example.com" not in resp.data.decode("utf-8")

    def test_duplicate_email_rejected(self, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "First", "email": "dup@example.com"},
        )
        resp = admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "Second", "email": "dup@example.com"},
            follow_redirects=True,
        )
        assert "bereits" in resp.data.decode("utf-8").lower()

    def test_deleted_recipient_not_in_db(self, app, admin_client):
        admin_client.post(
            "/admin/recipients",
            data={"action": "add", "name": "To Delete", "email": "del@example.com"},
        )
        with app.app_context():
            rec_id = EmailRecipient.query.filter_by(email="del@example.com").first().id

        admin_client.post(
            "/admin/recipients",
            data={"action": "delete", "rec_id": rec_id},
        )
        with app.app_context():
            assert EmailRecipient.query.filter_by(email="del@example.com").first() is None


# ---------------------------------------------------------------------------
# BW-05  Access control – technician vs admin
# ---------------------------------------------------------------------------

class TestAccessControl:
    """Role-based access control prevents unauthorised operations."""

    def test_unauthenticated_redirected_to_login(self, client, device):
        resp = client.get(f"/report/{device['device_id']}")
        assert resp.status_code in (302, 301)
        assert "/auth/login" in resp.headers["Location"]

    def test_team_user_blocked_from_admin_dashboard(self, team_client):
        resp = team_client.get("/admin/")
        assert resp.status_code == 403

    def test_team_user_blocked_from_device_management(self, team_client):
        resp = team_client.get("/admin/devices")
        assert resp.status_code == 403

    def test_team_user_blocked_from_user_management(self, team_client):
        resp = team_client.get("/admin/users")
        assert resp.status_code == 403

    def test_team_user_can_access_report_form(self, team_client, device):
        resp = team_client.get(f"/report/{device['device_id']}")
        assert resp.status_code == 200

    def test_admin_can_access_dashboard(self, admin_client):
        assert admin_client.get("/admin/").status_code == 200

    def test_admin_can_access_device_management(self, admin_client):
        assert admin_client.get("/admin/devices").status_code == 200

    def test_team_api_cannot_create_device(self, client, team_headers):
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": "NOPERM-001", "name": "No Permission"},
            headers=team_headers,
        )
        assert resp.status_code == 403

    def test_team_api_cannot_delete_device(self, client, team_headers, device):
        resp = client.delete(
            f"/api/v1/devices/{device['device_id']}", headers=team_headers
        )
        assert resp.status_code == 403

    def test_team_api_cannot_resolve_defect(self, client, team_headers, defect):
        resp = client.patch(
            f"/api/v1/defects/{defect['id']}/resolve",
            json={},
            headers=team_headers,
        )
        assert resp.status_code == 403

    def test_root_redirects_admin_to_dashboard(self, admin_client):
        resp = admin_client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/" in resp.headers["Location"]

    def test_root_redirects_unauthenticated_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# BW-06  Category management
# ---------------------------------------------------------------------------

class TestCategoryManagement:
    """Defect categories can be added, deleted, and reordered."""

    def test_add_category_appears_in_form(self, app, admin_client, device, team_client):
        admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": "Spezialkategorie"},
        )
        resp = team_client.get(f"/report/{device['device_id']}")
        assert "Spezialkategorie" in resp.data.decode("utf-8")

    def test_delete_category_removed_from_form(self, app, admin_client, device, team_client):
        admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": "ZuLoeschend"},
        )
        with app.app_context():
            cat_id = DefectCategory.query.filter_by(name="ZuLoeschend").first().id

        admin_client.post(
            "/admin/categories",
            data={"action": "delete", "cat_id": cat_id},
        )
        resp = team_client.get(f"/report/{device['device_id']}")
        assert "ZuLoeschend" not in resp.data.decode("utf-8")

    def test_duplicate_category_rejected(self, admin_client):
        admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": "DupKat"},
        )
        resp = admin_client.post(
            "/admin/categories",
            data={"action": "add", "name": "DupKat"},
            follow_redirects=True,
        )
        assert "bereits" in resp.data.decode("utf-8").lower()

    def test_category_move_up(self, app, admin_client):
        admin_client.post("/admin/categories", data={"action": "add", "name": "KatAlpha"})
        admin_client.post("/admin/categories", data={"action": "add", "name": "KatBeta"})
        with app.app_context():
            beta = DefectCategory.query.filter_by(name="KatBeta").first()
            beta_id = beta.id
            original_order = beta.sort_order

        admin_client.post(
            "/admin/categories",
            data={"action": "move_up", "cat_id": beta_id},
        )
        with app.app_context():
            beta_after = DefectCategory.query.filter_by(name="KatBeta").first()
            assert beta_after.sort_order <= original_order

    def test_invalid_category_on_report_form_rejected(self, admin_client, team_client, device):
        resp = team_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "NON_EXISTENT_CATEGORY",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "kategorie" in resp.data.decode("utf-8").lower()


# ---------------------------------------------------------------------------
# BW-07  QR code encodes correct URL
# ---------------------------------------------------------------------------

class TestQRCodeGeneration:
    """QR code PNG is generated and contains the correct report URL."""

    def test_qr_download_returns_png(self, admin_client, device):
        resp = admin_client.get(f"/admin/qr/{device['device_id']}")
        assert resp.status_code == 200
        assert resp.content_type == "image/png"
        assert len(resp.data) > 100  # non-trivial PNG

    def test_qr_page_shows_report_url(self, admin_client, device):
        resp = admin_client.get(f"/admin/qr-page/{device['device_id']}")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert f"/report/{device['device_id']}" in body

    def test_api_qr_endpoint_returns_png(self, client, api_headers, device):
        resp = client.get(
            f"/api/v1/devices/{device['device_id']}/qr", headers=api_headers
        )
        assert resp.status_code == 200
        assert resp.content_type == "image/png"

    def test_qr_for_unknown_device_returns_404(self, admin_client):
        resp = admin_client.get("/admin/qr/GHOST-QR-999")
        # Redirects to devices page with flash, or returns 404/redirect
        assert resp.status_code in (302, 404)


# ---------------------------------------------------------------------------
# BW-08  Admin self-protection
# ---------------------------------------------------------------------------

class TestAdminSelfProtection:
    """The 'admin' account and the current user cannot be deleted."""

    def test_admin_user_cannot_be_deleted(self, app, admin_client):
        with app.app_context():
            admin_id = User.query.filter_by(username="admin").first().id

        resp = admin_client.post(
            "/admin/users",
            data={"action": "delete", "user_id": admin_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            assert User.query.filter_by(username="admin").first() is not None

    def test_current_user_cannot_delete_themselves(self, app, admin_client):
        # admin_client is logged in as admin
        with app.app_context():
            admin_id = User.query.filter_by(username="admin").first().id

        admin_client.post(
            "/admin/users",
            data={"action": "delete", "user_id": admin_id},
        )
        with app.app_context():
            assert User.query.filter_by(username="admin").first() is not None


# ---------------------------------------------------------------------------
# BW-09  Reporter captured correctly
# ---------------------------------------------------------------------------

class TestReporterTracking:
    """The reporter field must reflect who submitted the defect."""

    def test_reporter_is_team_login_when_using_web_form(
        self, app, team_client, device
    ):
        team_client.post(
            f"/report/{device['device_id']}",
            data={
                "category": "Sonstiges",
                "description": "Reporter Test",
                "event_name": "Reporter Event",
                "project_number": "PRJ-REP-01",
            },
        )
        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            df = (
                Defect.query.filter_by(device_id=dev.id)
                .order_by(Defect.created_at.desc())
                .first()
            )
            assert df.reporter == "team_login"

    def test_reporter_is_api_user_when_using_api(
        self, app, client, api_headers, device
    ):
        resp = client.post(
            "/api/v1/defects",
            json={
                "device_id": device["device_id"],
                "category": "Sonstiges",
                "description": "API Reporter Test",
                "event_name": "API Event",
                "project_number": "PRJ-REP-02",
            },
            headers=api_headers,
        )
        assert resp.get_json()["reporter"] == "api"

    def test_web_ui_user_blocked_from_api(
        self, app, client, team_headers, device
    ):
        """Web-UI users (team_login) must not be able to submit via the API."""
        resp = client.post(
            "/api/v1/defects",
            json={
                "device_id": device["device_id"],
                "category": "Sonstiges",
                "description": "Should be blocked",
                "event_name": "API Event",
                "project_number": "PRJ-REP-03",
            },
            headers=team_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# BW-10  Device onboarding
# ---------------------------------------------------------------------------

class TestDeviceOnboarding:
    """Complete device onboarding: create → verify → QR code ready."""

    def test_create_device_via_admin_ui(self, app, admin_client):
        admin_client.post(
            "/admin/devices",
            data={
                "action": "add",
                "device_id": "ON-001",
                "name": "Onboarding Kamera",
                "description": "Test Gerät",
            },
        )
        with app.app_context():
            d = Device.query.filter_by(device_id="ON-001").first()
            assert d is not None
            assert d.name == "Onboarding Kamera"
            assert d.status == "Verfügbar"
            assert d.open_defect_count == 0

    def test_duplicate_device_id_rejected(self, admin_client, device):
        resp = admin_client.post(
            "/admin/devices",
            data={
                "action": "add",
                "device_id": device["device_id"],
                "name": "Duplikat",
            },
            follow_redirects=True,
        )
        assert "bereits" in resp.data.decode("utf-8").lower()

    def test_new_device_appears_in_api_list(self, app, admin_client, client, api_headers):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "ON-002", "name": "API List Test"},
        )
        resp = client.get("/api/v1/devices", headers=api_headers)
        device_ids = [d["device_id"] for d in resp.get_json()]
        assert "ON-002" in device_ids

    def test_new_device_report_url_is_accessible(self, admin_client, team_client):
        admin_client.post(
            "/admin/devices",
            data={"action": "add", "device_id": "ON-003", "name": "Report URL Test"},
        )
        resp = team_client.get("/report/ON-003")
        assert resp.status_code == 200
        assert "ON-003" in resp.data.decode("utf-8")

    def test_delete_device_removes_from_list(self, app, admin_client, device):
        admin_client.post(
            "/admin/devices",
            data={"action": "delete", "dev_id": device["id"]},
        )
        with app.app_context():
            assert Device.query.filter_by(device_id=device["device_id"]).first() is None
