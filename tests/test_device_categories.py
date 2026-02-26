"""
Tests for Produktkategorien (DeviceCategory) feature and clickable admin kacheln.

Covers:
  - DeviceCategory model (seeded categories exist)
  - Admin CRUD: add / edit / delete categories via /admin/device-categories
  - Device assignment: category field in add form and set_category action
  - Device list filter by category and status
  - Admin kachel detail view (/admin/kachel/<filter_key>)
  - Disponent tile_detail shows Kategorie column
  - Disponent availability filter by device_cat
  - Access control: non-admin cannot reach category management
"""

import pytest

from config import Config
from models import Device, DeviceCategory, db as _db


# --------------------------------------------------------------------------- #
#  Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_device(app, device_id="TST-001", name="Testgerät", category_id=None):
    with app.app_context():
        d = Device(device_id=device_id, name=name, category_id=category_id)
        _db.session.add(d)
        _db.session.commit()
        return {"id": d.id, "device_id": d.device_id}


def _first_seeded_cat_id(app):
    """Return the id of the first seeded DeviceCategory."""
    with app.app_context():
        cat = DeviceCategory.query.order_by(DeviceCategory.sort_order).first()
        return cat.id if cat else None


# --------------------------------------------------------------------------- #
#  1. Seeded categories                                                         #
# --------------------------------------------------------------------------- #


class TestSeededCategories:
    def test_seeded_categories_exist(self, app):
        with app.app_context():
            count = DeviceCategory.query.count()
            assert count == len(Config.DEVICE_CATEGORIES)

    def test_seeded_category_names(self, app):
        with app.app_context():
            names = {c.name for c in DeviceCategory.query.all()}
            for name, _ in Config.DEVICE_CATEGORIES:
                assert name in names

    def test_seeded_category_colors(self, app):
        with app.app_context():
            for cat in DeviceCategory.query.all():
                assert cat.color.startswith("#")
                assert len(cat.color) == 7


# --------------------------------------------------------------------------- #
#  2. Admin category management page                                            #
# --------------------------------------------------------------------------- #


class TestAdminDeviceCategoriesPage:
    def test_page_loads_for_admin(self, admin_client):
        resp = admin_client.get("/admin/device-categories")
        assert resp.status_code == 200
        assert b"Produktkategorien" in resp.data

    def test_page_shows_seeded_categories(self, admin_client):
        resp = admin_client.get("/admin/device-categories")
        first_name = Config.DEVICE_CATEGORIES[0][0].encode()
        assert first_name in resp.data

    def test_page_denied_for_disponent(self, disponent_client):
        resp = disponent_client.get("/admin/device-categories")
        assert resp.status_code == 403

    def test_page_denied_for_werkstatt(self, werkstatt_client):
        resp = werkstatt_client.get("/admin/device-categories")
        assert resp.status_code == 403

    def test_page_redirects_anonymous(self, client):
        resp = client.get("/admin/device-categories")
        assert resp.status_code in (302, 403)


# --------------------------------------------------------------------------- #
#  3. Add / edit / delete category (admin POST)                                 #
# --------------------------------------------------------------------------- #


class TestCategoryCRUD:
    def test_add_category(self, app, admin_client):
        resp = admin_client.post(
            "/admin/device-categories",
            data={"action": "add", "name": "Spezial", "color": "#ff0000"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            cat = DeviceCategory.query.filter_by(name="Spezial").first()
            assert cat is not None
            assert cat.color == "#ff0000"

    def test_add_duplicate_category_rejected(self, admin_client):
        first_name = Config.DEVICE_CATEGORIES[0][0]
        resp = admin_client.post(
            "/admin/device-categories",
            data={"action": "add", "name": first_name, "color": "#aabbcc"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "existiert bereits".encode() in resp.data

    def test_add_empty_name_rejected(self, admin_client):
        resp = admin_client.post(
            "/admin/device-categories",
            data={"action": "add", "name": "", "color": "#aabbcc"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "erforderlich".encode() in resp.data

    def test_edit_category(self, app, admin_client):
        with app.app_context():
            cat = DeviceCategory(name="Altname", color="#111111", sort_order=99)
            _db.session.add(cat)
            _db.session.commit()
            cat_id = cat.id

        resp = admin_client.post(
            "/admin/device-categories",
            data={
                "action": "edit",
                "cat_id": cat_id,
                "name": "Neuname",
                "color": "#222222",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            cat = _db.session.get(DeviceCategory, cat_id)
            assert cat.name == "Neuname"
            assert cat.color == "#222222"

    def test_delete_category(self, app, admin_client):
        with app.app_context():
            cat = DeviceCategory(name="ZuLöschen", color="#333333", sort_order=98)
            _db.session.add(cat)
            _db.session.commit()
            cat_id = cat.id

        resp = admin_client.post(
            "/admin/device-categories",
            data={"action": "delete", "cat_id": cat_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            assert _db.session.get(DeviceCategory, cat_id) is None

    def test_delete_category_unlinks_devices(self, app, admin_client):
        """Deleting a category must set device.category_id to NULL, not error."""
        with app.app_context():
            cat = DeviceCategory(name="TempKat", color="#444444", sort_order=97)
            _db.session.add(cat)
            _db.session.flush()
            dev = Device(device_id="TMP-DEL", name="TempGerät", category_id=cat.id)
            _db.session.add(dev)
            _db.session.commit()
            cat_id = cat.id
            dev_id = dev.id

        resp = admin_client.post(
            "/admin/device-categories",
            data={"action": "delete", "cat_id": cat_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            dev = _db.session.get(Device, dev_id)
            assert dev is not None
            assert dev.category_id is None


# --------------------------------------------------------------------------- #
#  4. Device category assignment                                                #
# --------------------------------------------------------------------------- #


class TestDeviceCategoryAssignment:
    def test_add_device_with_category(self, app, admin_client):
        cat_id = _first_seeded_cat_id(app)
        resp = admin_client.post(
            "/admin/devices",
            data={
                "action": "add",
                "device_id": "CAT-001",
                "name": "Kamera mit Kategorie",
                "category_id": cat_id,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            dev = Device.query.filter_by(device_id="CAT-001").first()
            assert dev is not None
            assert dev.category_id == cat_id

    def test_set_category_action(self, app, admin_client):
        _make_device(app, device_id="SETCAT-001", name="Kat-Test")
        cat_id = _first_seeded_cat_id(app)

        with app.app_context():
            dev = Device.query.filter_by(device_id="SETCAT-001").first()
            dev_id = dev.id

        resp = admin_client.post(
            "/admin/devices",
            data={"action": "set_category", "dev_id": dev_id, "category_id": cat_id},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            dev = _db.session.get(Device, dev_id)
            assert dev.category_id == cat_id

    def test_devices_page_shows_category_badge(self, app, admin_client):
        cat_id = _first_seeded_cat_id(app)
        _make_device(app, device_id="BADGE-001", name="Badge-Gerät", category_id=cat_id)
        resp = admin_client.get("/admin/devices")
        assert resp.status_code == 200
        assert b"cat-badge" in resp.data


# --------------------------------------------------------------------------- #
#  5. Device list filter by category                                            #
# --------------------------------------------------------------------------- #


class TestDeviceListFilter:
    def test_filter_by_category(self, app, admin_client):
        cat_id = _first_seeded_cat_id(app)
        _make_device(app, device_id="FILT-001", name="FiltGerät", category_id=cat_id)
        _make_device(app, device_id="FILT-002", name="OhneKat", category_id=None)

        resp = admin_client.get(f"/admin/devices?cat={cat_id}")
        assert resp.status_code == 200
        assert b"FiltGer" in resp.data
        assert b"OhneKat" not in resp.data

    def test_filter_by_status(self, app, admin_client):
        _make_device(app, device_id="FSTS-001", name="StatusTestDevice")
        resp = admin_client.get("/admin/devices?status=Verfügbar")
        assert resp.status_code == 200
        assert b"StatusTestDevice" in resp.data

    def test_filter_by_search(self, app, admin_client):
        _make_device(app, device_id="SRCH-001", name="ZielGerät")
        _make_device(app, device_id="SRCH-002", name="AnderesDing")
        resp = admin_client.get("/admin/devices?search=Ziel")
        assert resp.status_code == 200
        assert b"ZielGer" in resp.data
        assert b"AnderesDing" not in resp.data


# --------------------------------------------------------------------------- #
#  6. Admin kachel detail view                                                  #
# --------------------------------------------------------------------------- #


class TestAdminKachelDetail:
    def test_kachel_alle_loads(self, admin_client):
        resp = admin_client.get("/admin/kachel/alle")
        assert resp.status_code == 200
        assert "Alle Geräte".encode() in resp.data

    def test_kachel_wartung_loads(self, admin_client):
        resp = admin_client.get("/admin/kachel/wartung")
        assert resp.status_code == 200
        assert "Wartung".encode() in resp.data

    def test_kachel_verfuegbar_loads(self, admin_client):
        resp = admin_client.get("/admin/kachel/verfuegbar")
        assert resp.status_code == 200
        assert "Verfügbar".encode() in resp.data

    def test_kachel_invalid_returns_404(self, admin_client):
        resp = admin_client.get("/admin/kachel/gibtsNicht")
        assert resp.status_code == 404

    def test_kachel_denied_for_disponent(self, disponent_client):
        resp = disponent_client.get("/admin/kachel/alle")
        assert resp.status_code == 403

    def test_kachel_shows_devices(self, app, admin_client):
        _make_device(app, device_id="KACH-001", name="KachelGerät")
        resp = admin_client.get("/admin/kachel/alle")
        assert resp.status_code == 200
        assert b"KachelGer" in resp.data

    def test_kachel_filter_by_cat(self, app, admin_client):
        cat_id = _first_seeded_cat_id(app)
        _make_device(app, device_id="KFLT-001", name="MitKat", category_id=cat_id)
        _make_device(app, device_id="KFLT-002", name="OhneKat2", category_id=None)

        resp = admin_client.get(f"/admin/kachel/alle?cat={cat_id}")
        assert resp.status_code == 200
        assert b"MitKat" in resp.data
        assert b"OhneKat2" not in resp.data

    def test_kachel_shows_cat_badge(self, app, admin_client):
        cat_id = _first_seeded_cat_id(app)
        _make_device(app, device_id="KBDG-001", name="BadgeTest", category_id=cat_id)
        resp = admin_client.get("/admin/kachel/alle")
        assert b"cat-badge" in resp.data

    def test_kachel_search(self, app, admin_client):
        _make_device(app, device_id="KSRCH-001", name="Suchgerät")
        _make_device(app, device_id="KSRCH-002", name="AnderesSuch")
        resp = admin_client.get("/admin/kachel/alle?search=Suchger")
        assert resp.status_code == 200
        assert b"Suchger" in resp.data
        assert b"AnderesSuch" not in resp.data

    def test_dashboard_links_to_kachel(self, admin_client):
        resp = admin_client.get("/admin/")
        assert resp.status_code == 200
        assert b"/admin/kachel/alle" in resp.data
        assert b"/admin/kachel/wartung" in resp.data


# --------------------------------------------------------------------------- #
#  7. Disponent tile_detail category column                                     #
# --------------------------------------------------------------------------- #


class TestDisponentTileCategory:
    def test_tile_alle_shows_category_column(self, app, disponent_client):
        cat_id = _first_seeded_cat_id(app)
        _make_device(app, device_id="DTILE-001", name="DispoTile", category_id=cat_id)
        resp = disponent_client.get("/disponent/kachel/alle")
        assert resp.status_code == 200
        assert b"cat-badge" in resp.data

    def test_tile_shows_no_category_dash(self, app, disponent_client):
        _make_device(app, device_id="DTILE-002", name="OhneKatDispo", category_id=None)
        resp = disponent_client.get("/disponent/kachel/alle")
        assert resp.status_code == 200
        assert b"OhneKatDispo" in resp.data


# --------------------------------------------------------------------------- #
#  8. Disponent availability product category filter                            #
# --------------------------------------------------------------------------- #


class TestAvailabilityProductCategoryFilter:
    def test_filter_dropdown_present(self, disponent_client):
        resp = disponent_client.get("/disponent/verfuegbarkeit")
        assert resp.status_code == 200
        assert b"device_cat" in resp.data
        assert b"Produktkategorie" in resp.data

    def test_filter_by_device_cat_no_match(self, app, disponent_client):
        """Filter by a category that has no defects should return empty list."""
        cat_id = _first_seeded_cat_id(app)
        # no defects associated with this category
        resp = disponent_client.get(f"/disponent/verfuegbarkeit?device_cat={cat_id}")
        assert resp.status_code == 200
        # Should show "Keine nicht verfügbaren Geräte"
        assert "Keine".encode() in resp.data or b"0 Eintr" in resp.data

    def test_product_category_column_visible(self, disponent_client):
        """Produktkategorie column header should be visible in results table."""
        resp = disponent_client.get("/disponent/verfuegbarkeit")
        assert resp.status_code == 200
        assert b"Produktkategorie" in resp.data
