"""
Shared pytest fixtures for the Redline test suite.

The app is created once per session with an in-memory SQLite database.
Between tests the autouse clean_db fixture rolls back and removes all
test-generated rows while preserving the seeded defaults (admin/team_login/
disponent users, default categories, default workshop recipient).
"""

import base64

import pytest

from app import create_app
from config import Config, TestConfig
from models import AuditLog, Comment, db as _db, Defect, DefectCategory, Device, DeviceCategory, EmailRecipient, User


# --------------------------------------------------------------------------- #
#  Session-scoped app (DB created once, cleaned between tests)                 #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def app():
    """Create the Flask application once for the entire test session."""
    application = create_app(TestConfig)
    return application


@pytest.fixture(autouse=True)
def clean_db(app):
    """
    Autouse fixture: after each test, remove all test-generated rows while
    keeping the seeded defaults intact.
    """
    yield
    with app.app_context():
        _db.session.rollback()
        # Delete child tables before parents (SQLite doesn't enforce FK cascades
        # during bulk DELETE statements).
        AuditLog.query.delete()
        Comment.query.delete()
        Defect.query.delete()
        Device.query.delete()
        seeded_cat_names = [name for name, _ in Config.DEVICE_CATEGORIES]
        DeviceCategory.query.filter(
            ~DeviceCategory.name.in_(seeded_cat_names)
        ).delete(synchronize_session="fetch")
        EmailRecipient.query.filter(
            EmailRecipient.email != Config.WORKSHOP_EMAIL
        ).delete()
        User.query.filter(
            ~User.username.in_(["admin", "team_login", "disponent", "werkstatt", "api"])
        ).delete()
        DefectCategory.query.filter(
            ~DefectCategory.name.in_(Config.DEFECT_CATEGORIES)
        ).delete()
        _db.session.commit()


# --------------------------------------------------------------------------- #
#  HTTP client fixtures                                                         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_headers():
    """HTTP Basic Auth header for the seeded admin user."""
    creds = base64.b64encode(b"admin:admin123").decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def team_headers():
    """HTTP Basic Auth header for the seeded team_login user."""
    creds = base64.b64encode(b"team_login:team2025").decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def api_headers():
    """HTTP Basic Auth header for the seeded api user (is_api_user=True)."""
    creds = base64.b64encode(b"api:api2025").decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def admin_client(client):
    """Test client with an active admin session."""
    client.post("/auth/login", data={"username": "admin", "password": "admin123"})
    return client


@pytest.fixture
def team_client(client):
    """Test client with an active team_login session."""
    client.post(
        "/auth/login", data={"username": "team_login", "password": "team2025"}
    )
    return client


@pytest.fixture
def disponent_client(client):
    """Test client with an active disponent session (seeded default user)."""
    client.post(
        "/auth/login", data={"username": "disponent", "password": "disp2025"}
    )
    return client


@pytest.fixture
def werkstatt_client(client):
    """Test client with an active werkstatt session (seeded default user)."""
    client.post(
        "/auth/login", data={"username": "werkstatt", "password": "werk2025"}
    )
    return client


# --------------------------------------------------------------------------- #
#  Data fixtures (return plain dicts to avoid DetachedInstanceError)           #
# --------------------------------------------------------------------------- #


@pytest.fixture
def device(app):
    """Insert a test device and return its key attributes as a dict."""
    with app.app_context():
        d = Device(
            device_id="CAM-001", name="Kamera Alpha", description="Testbeschreibung"
        )
        _db.session.add(d)
        _db.session.commit()
        return {"id": d.id, "device_id": d.device_id, "name": d.name}


@pytest.fixture
def defect(app, device):
    """Insert a test defect (status=Offen) and return its key attributes."""
    with app.app_context():
        dev = Device.query.filter_by(device_id=device["device_id"]).first()
        df = Defect(
            device_id=dev.id,
            category="Mechanischer Schaden",
            description="Gehäuse gerissen",
            event_name="Sommerfestival",
            project_number="PRJ-2025-001",
            reporter="admin",
        )
        _db.session.add(df)
        dev.status = "Wartung"
        _db.session.commit()
        return {"id": df.id, "device_id": device["device_id"]}
