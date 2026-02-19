"""
Tests for the REST JSON API (v1).
All endpoints require HTTP Basic Auth.
"""
from models import db, Defect, Device


class TestAPIAuthentication:
    def test_no_auth_returns_401(self, client):
        resp = client.get("/api/v1/devices")
        assert resp.status_code == 401

    def test_invalid_password_returns_401(self, client):
        import base64
        creds = base64.b64encode(b"admin:completely_wrong").decode()
        resp = client.get("/api/v1/devices", headers={"Authorization": f"Basic {creds}"})
        assert resp.status_code == 401

    def test_unknown_user_returns_401(self, client):
        import base64
        creds = base64.b64encode(b"ghost:anything").decode()
        resp = client.get("/api/v1/devices", headers={"Authorization": f"Basic {creds}"})
        assert resp.status_code == 401

    def test_valid_admin_auth_returns_200(self, client, admin_headers):
        resp = client.get("/api/v1/devices", headers=admin_headers)
        assert resp.status_code == 200

    def test_valid_team_auth_returns_200(self, client, team_headers):
        resp = client.get("/api/v1/devices", headers=team_headers)
        assert resp.status_code == 200

    def test_team_user_blocked_from_admin_endpoint(self, client, team_headers):
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": "X-001", "name": "Test"},
            headers=team_headers,
        )
        assert resp.status_code == 403

    def test_error_response_is_json(self, client):
        resp = client.get("/api/v1/devices")
        assert resp.content_type == "application/json"
        assert "error" in resp.json


class TestAPIDevicesList:
    def test_empty_list(self, client, admin_headers):
        resp = client.get("/api/v1/devices", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json == []

    def test_returns_existing_device(self, client, admin_headers, device):
        resp = client.get("/api/v1/devices", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json) == 1
        assert resp.json[0]["device_id"] == device["device_id"]
        assert resp.json[0]["name"] == device["name"]

    def test_response_includes_expected_fields(self, client, admin_headers, device):
        resp = client.get("/api/v1/devices", headers=admin_headers)
        d = resp.json[0]
        for field in ("device_id", "name", "description", "status", "open_defect_count", "created_at"):
            assert field in d

    def test_filter_by_status_verfuegbar(self, client, admin_headers, device):
        resp = client.get("/api/v1/devices?status=Verfügbar", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json) == 1

    def test_filter_by_status_wartung_empty(self, client, admin_headers, device):
        resp = client.get("/api/v1/devices?status=Wartung", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json) == 0

    def test_filter_by_status_wartung_shows_result(self, client, admin_headers, defect):
        resp = client.get("/api/v1/devices?status=Wartung", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json) == 1


class TestAPIDeviceCRUD:
    def test_create_device(self, app, client, admin_headers):
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": "API-NEW", "name": "API Gerät", "description": "Beschreibung"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json["device_id"] == "API-NEW"
        assert resp.json["status"] == "Verfügbar"
        assert resp.json["open_defect_count"] == 0
        with app.app_context():
            assert Device.query.filter_by(device_id="API-NEW").first() is not None

    def test_create_device_missing_device_id_returns_400(self, client, admin_headers):
        resp = client.post(
            "/api/v1/devices",
            json={"name": "Kein ID"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_create_device_missing_name_returns_400(self, client, admin_headers):
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": "NOID-001"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_create_device_duplicate_id_returns_409(self, client, admin_headers, device):
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": device["device_id"], "name": "Duplikat"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_get_device(self, client, admin_headers, device):
        resp = client.get(f"/api/v1/devices/{device['device_id']}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json["device_id"] == device["device_id"]
        assert resp.json["name"] == device["name"]

    def test_get_device_not_found_returns_404(self, client, admin_headers):
        resp = client.get("/api/v1/devices/GHOST-999", headers=admin_headers)
        assert resp.status_code == 404

    def test_update_device_name(self, client, admin_headers, device):
        resp = client.patch(
            f"/api/v1/devices/{device['device_id']}",
            json={"name": "Umbenanntes Gerät"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json["name"] == "Umbenanntes Gerät"

    def test_update_device_description(self, client, admin_headers, device):
        resp = client.patch(
            f"/api/v1/devices/{device['device_id']}",
            json={"description": "Neue Beschreibung"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json["description"] == "Neue Beschreibung"

    def test_update_device_status_to_wartung(self, client, admin_headers, device):
        resp = client.patch(
            f"/api/v1/devices/{device['device_id']}",
            json={"status": "Wartung"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json["status"] == "Wartung"

    def test_update_device_invalid_status_returns_400(self, client, admin_headers, device):
        resp = client.patch(
            f"/api/v1/devices/{device['device_id']}",
            json={"status": "KAPUTT"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_update_device_not_found_returns_404(self, client, admin_headers):
        resp = client.patch(
            "/api/v1/devices/GHOST-999",
            json={"name": "Test"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_delete_device(self, app, client, admin_headers, device):
        resp = client.delete(
            f"/api/v1/devices/{device['device_id']}",
            headers=admin_headers,
        )
        assert resp.status_code == 204
        with app.app_context():
            assert Device.query.filter_by(device_id=device["device_id"]).first() is None

    def test_delete_device_not_found_returns_404(self, client, admin_headers):
        resp = client.delete("/api/v1/devices/GHOST-999", headers=admin_headers)
        assert resp.status_code == 404

    def test_get_device_qr_code(self, client, admin_headers, device):
        resp = client.get(f"/api/v1/devices/{device['device_id']}/qr", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.content_type == "image/png"
        assert len(resp.data) > 0

    def test_get_device_qr_code_not_found_returns_404(self, client, admin_headers):
        resp = client.get("/api/v1/devices/GHOST-999/qr", headers=admin_headers)
        assert resp.status_code == 404


class TestAPIDefectsList:
    def test_empty_list(self, client, admin_headers):
        resp = client.get("/api/v1/defects", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json["items"] == []
        assert resp.json["total"] == 0

    def test_returns_existing_defect(self, client, admin_headers, defect):
        resp = client.get("/api/v1/defects", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json["total"] == 1
        assert resp.json["items"][0]["id"] == defect["id"]

    def test_response_includes_expected_fields(self, client, admin_headers, defect):
        resp = client.get("/api/v1/defects", headers=admin_headers)
        item = resp.json["items"][0]
        for field in ("id", "device_id", "device_name", "category", "description",
                      "event_name", "project_number", "status", "reporter",
                      "created_at", "resolved_at", "resolution_notes"):
            assert field in item

    def test_filter_by_status_offen(self, client, admin_headers, defect):
        resp = client.get("/api/v1/defects?status=Offen", headers=admin_headers)
        assert resp.json["total"] == 1

    def test_filter_by_status_behoben_empty(self, client, admin_headers, defect):
        resp = client.get("/api/v1/defects?status=Behoben", headers=admin_headers)
        assert resp.json["total"] == 0

    def test_filter_by_device_id(self, client, admin_headers, defect):
        resp = client.get(f"/api/v1/defects?device_id={defect['device_id']}", headers=admin_headers)
        assert resp.json["total"] == 1

    def test_filter_by_unknown_device_returns_empty(self, client, admin_headers):
        resp = client.get("/api/v1/defects?device_id=GHOST-999", headers=admin_headers)
        assert resp.json["total"] == 0

    def test_filter_by_event_name_partial_match(self, client, admin_headers, defect):
        resp = client.get("/api/v1/defects?event_name=Sommer", headers=admin_headers)
        assert resp.json["total"] == 1

    def test_filter_by_project_number(self, client, admin_headers, defect):
        resp = client.get("/api/v1/defects?project_number=PRJ-2025", headers=admin_headers)
        assert resp.json["total"] == 1

    def test_pagination_meta(self, client, admin_headers, defect):
        resp = client.get("/api/v1/defects", headers=admin_headers)
        assert "page" in resp.json
        assert "per_page" in resp.json
        assert "pages" in resp.json


class TestAPIDefectCRUD:
    def test_create_defect(self, app, client, admin_headers, device):
        resp = client.post(
            "/api/v1/defects",
            json={
                "device_id": device["device_id"],
                "category": "Mechanischer Schaden",
                "description": "API Defekt",
                "event_name": "API Test Event",
                "project_number": "PRJ-API-001",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json["status"] == "Offen"
        assert resp.json["category"] == "Mechanischer Schaden"
        assert resp.json["device_id"] == device["device_id"]

        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            assert dev.status == "Wartung"

    def test_create_defect_missing_fields_returns_400(self, client, admin_headers, device):
        resp = client.post(
            "/api/v1/defects",
            json={"device_id": device["device_id"]},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "fields" in resp.json

    def test_create_defect_invalid_category_returns_400(self, client, admin_headers, device):
        resp = client.post(
            "/api/v1/defects",
            json={
                "device_id": device["device_id"],
                "category": "UNGÜLTIGE KATEGORIE",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_create_defect_unknown_device_returns_404(self, client, admin_headers):
        resp = client.post(
            "/api/v1/defects",
            json={
                "device_id": "GHOST-999",
                "category": "Mechanischer Schaden",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_create_defect_reporter_is_api_user(self, client, admin_headers, device):
        resp = client.post(
            "/api/v1/defects",
            json={
                "device_id": device["device_id"],
                "category": "Mechanischer Schaden",
                "description": "Test",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            headers=admin_headers,
        )
        assert resp.json["reporter"] == "admin"

    def test_get_defect(self, client, admin_headers, defect):
        resp = client.get(f"/api/v1/defects/{defect['id']}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json["id"] == defect["id"]

    def test_get_defect_not_found_returns_404(self, client, admin_headers):
        resp = client.get("/api/v1/defects/99999", headers=admin_headers)
        assert resp.status_code == 404

    def test_resolve_defect(self, app, client, admin_headers, defect):
        resp = client.patch(
            f"/api/v1/defects/{defect['id']}/resolve",
            json={"resolution_notes": "Repariert und getestet"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json["status"] == "Behoben"
        assert resp.json["resolution_notes"] == "Repariert und getestet"
        assert resp.json["resolved_at"] is not None

        with app.app_context():
            dev = Device.query.filter_by(device_id=defect["device_id"]).first()
            assert dev.status == "Verfügbar"

    def test_resolve_defect_already_resolved_returns_409(self, client, admin_headers, defect):
        client.patch(f"/api/v1/defects/{defect['id']}/resolve", json={}, headers=admin_headers)
        resp = client.patch(
            f"/api/v1/defects/{defect['id']}/resolve", json={}, headers=admin_headers
        )
        assert resp.status_code == 409

    def test_resolve_defect_not_found_returns_404(self, client, admin_headers):
        resp = client.patch("/api/v1/defects/99999/resolve", json={}, headers=admin_headers)
        assert resp.status_code == 404

    def test_resolve_defect_requires_admin(self, client, team_headers, defect):
        resp = client.patch(
            f"/api/v1/defects/{defect['id']}/resolve", json={}, headers=team_headers
        )
        assert resp.status_code == 403

    def test_team_user_can_create_defect(self, client, team_headers, device):
        resp = client.post(
            "/api/v1/defects",
            json={
                "device_id": device["device_id"],
                "category": "Mechanischer Schaden",
                "description": "Team Defekt",
                "event_name": "Event",
                "project_number": "PRJ-001",
            },
            headers=team_headers,
        )
        assert resp.status_code == 201
        assert resp.json["reporter"] == "team_login"


class TestAPIEvents:
    def test_list_events_empty(self, client, admin_headers):
        resp = client.get("/api/v1/events", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json == []

    def test_list_events_with_defect(self, client, admin_headers, defect):
        resp = client.get("/api/v1/events", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json) == 1
        assert resp.json[0]["project_number"] == "PRJ-2025-001"
        assert resp.json[0]["event_name"] == "Sommerfestival"

    def test_get_event_defects(self, client, admin_headers, defect):
        resp = client.get("/api/v1/events/PRJ-2025-001", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json["project_number"] == "PRJ-2025-001"
        assert resp.json["defect_count"] == 1
        assert len(resp.json["defects"]) == 1

    def test_get_event_defects_not_found_returns_404(self, client, admin_headers):
        resp = client.get("/api/v1/events/PRJ-NONEXISTENT", headers=admin_headers)
        assert resp.status_code == 404

    def test_get_event_defects_filter_by_event_name(self, client, admin_headers, defect):
        resp = client.get(
            "/api/v1/events/PRJ-2025-001?event_name=Sommerfestival",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json["defect_count"] == 1

    def test_get_event_defects_wrong_event_name_returns_404(self, client, admin_headers, defect):
        resp = client.get(
            "/api/v1/events/PRJ-2025-001?event_name=WrongEvent",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_team_user_can_list_events(self, client, team_headers, defect):
        resp = client.get("/api/v1/events", headers=team_headers)
        assert resp.status_code == 200
