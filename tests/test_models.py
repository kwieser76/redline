"""
Unit tests for SQLAlchemy models.
Tests run purely against the in-memory DB – no HTTP involved.
"""
import pytest

from models import db, Defect, DefectCategory, Device, EmailRecipient, User


class TestUserModel:
    def test_set_and_check_password_correct(self, app):
        with app.app_context():
            u = User(username="pw_test")
            u.set_password("secure123")
            assert u.check_password("secure123") is True

    def test_check_password_wrong_returns_false(self, app):
        with app.app_context():
            u = User(username="pw_test2")
            u.set_password("correct")
            assert u.check_password("wrong") is False

    def test_password_is_stored_hashed(self, app):
        with app.app_context():
            u = User(username="pw_test3")
            u.set_password("plaintext")
            assert u.password_hash != "plaintext"
            assert "plaintext" not in u.password_hash

    def test_repr_contains_username(self, app):
        with app.app_context():
            u = User(username="alice")
            assert "alice" in repr(u)

    def test_is_admin_defaults_to_false(self, app):
        with app.app_context():
            u = User(username="nonadmin")
            u.set_password("pass")
            db.session.add(u)
            db.session.commit()
            fetched = User.query.filter_by(username="nonadmin").first()
            assert fetched.is_admin is False
            assert fetched.is_community is False

    def test_admin_flag_persists(self, app):
        with app.app_context():
            u = User(username="superadmin", is_admin=True)
            u.set_password("pass")
            db.session.add(u)
            db.session.commit()
            fetched = User.query.filter_by(username="superadmin").first()
            assert fetched.is_admin is True

    def test_username_must_be_unique(self, app):
        with app.app_context():
            u1 = User(username="dupuser")
            u1.set_password("pass")
            u2 = User(username="dupuser")
            u2.set_password("pass")
            db.session.add(u1)
            db.session.commit()
            db.session.add(u2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()


class TestDeviceModel:
    def test_default_status_is_verfuegbar(self, app):
        with app.app_context():
            d = Device(device_id="DEV-NEW", name="Neues Gerät")
            db.session.add(d)
            db.session.commit()
            assert d.status == "Verfügbar"

    def test_repr_contains_device_id_and_name(self, app):
        with app.app_context():
            d = Device(device_id="DEV-REPR", name="Reprgerät")
            assert "DEV-REPR" in repr(d)
            assert "Reprgerät" in repr(d)

    def test_open_defect_count_zero_when_no_defects(self, app, device):
        with app.app_context():
            d = Device.query.filter_by(device_id=device["device_id"]).first()
            assert d.open_defect_count == 0

    def test_open_defect_count_counts_open_defects(self, app, defect):
        with app.app_context():
            d = Device.query.filter_by(device_id=defect["device_id"]).first()
            assert d.open_defect_count == 1

    def test_open_defect_count_excludes_resolved(self, app, defect):
        with app.app_context():
            from datetime import datetime, timezone
            df = db.session.get(Defect, defect["id"])
            df.status = "Behoben"
            df.resolved_at = datetime.now(timezone.utc)
            db.session.commit()
            d = Device.query.filter_by(device_id=defect["device_id"]).first()
            assert d.open_defect_count == 0

    def test_device_id_must_be_unique(self, app):
        with app.app_context():
            d1 = Device(device_id="DUPDEV-001", name="Original")
            d2 = Device(device_id="DUPDEV-001", name="Duplikat")
            db.session.add(d1)
            db.session.commit()
            db.session.add(d2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_defects_relationship(self, app, defect):
        with app.app_context():
            d = Device.query.filter_by(device_id=defect["device_id"]).first()
            assert len(d.defects) == 1
            assert d.defects[0].id == defect["id"]


class TestDefectModel:
    def test_default_status_is_offen(self, app, device):
        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            df = Defect(
                device_id=dev.id,
                category="Sonstiges",
                description="Kleiner Schaden",
                event_name="Testfest",
                project_number="PRJ-999",
            )
            db.session.add(df)
            db.session.commit()
            assert df.status == "Offen"

    def test_default_reporter_is_team_login(self, app, device):
        with app.app_context():
            dev = Device.query.filter_by(device_id=device["device_id"]).first()
            df = Defect(
                device_id=dev.id,
                category="Sonstiges",
                description="Test",
                event_name="Event",
                project_number="PRJ-001",
            )
            db.session.add(df)
            db.session.commit()
            assert df.reporter == "team_login"

    def test_resolved_at_is_nullable(self, app, defect):
        with app.app_context():
            df = db.session.get(Defect, defect["id"])
            assert df.resolved_at is None

    def test_repr_contains_defect_id(self, app, defect):
        with app.app_context():
            df = db.session.get(Defect, defect["id"])
            assert str(defect["id"]) in repr(df)

    def test_resolution_notes_default_empty(self, app, defect):
        with app.app_context():
            df = db.session.get(Defect, defect["id"])
            assert df.resolution_notes == ""

    def test_device_backref(self, app, defect):
        with app.app_context():
            df = db.session.get(Defect, defect["id"])
            assert df.device is not None
            assert df.device.device_id == defect["device_id"]


class TestEmailRecipientModel:
    def test_active_defaults_to_true(self, app):
        with app.app_context():
            r = EmailRecipient(name="Neuer Empfänger", email="new@example.com")
            db.session.add(r)
            db.session.commit()
            assert r.active is True

    def test_repr_contains_email(self, app):
        with app.app_context():
            r = EmailRecipient(name="Test", email="repr@example.com")
            assert "repr@example.com" in repr(r)

    def test_email_must_be_unique(self, app):
        with app.app_context():
            r1 = EmailRecipient(name="A", email="dup@example.com")
            r2 = EmailRecipient(name="B", email="dup@example.com")
            db.session.add(r1)
            db.session.commit()
            db.session.add(r2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_can_be_deactivated(self, app):
        with app.app_context():
            r = EmailRecipient(name="Inaktiv", email="inactive@example.com", active=False)
            db.session.add(r)
            db.session.commit()
            assert r.active is False


class TestDefectCategoryModel:
    def test_repr_contains_name(self, app):
        with app.app_context():
            cat = DefectCategory(name="Testschaden")
            assert "Testschaden" in repr(cat)

    def test_sort_order_default_zero(self, app):
        with app.app_context():
            cat = DefectCategory(name="Sonderschaden")
            db.session.add(cat)
            db.session.commit()
            assert cat.sort_order == 0

    def test_name_must_be_unique(self, app):
        with app.app_context():
            c1 = DefectCategory(name="Dupkategorie")
            c2 = DefectCategory(name="Dupkategorie")
            db.session.add(c1)
            db.session.commit()
            db.session.add(c2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_default_categories_are_seeded(self, app):
        """Verify all 9 default categories exist after app initialisation."""
        with app.app_context():
            from config import Config
            count = DefectCategory.query.filter(
                DefectCategory.name.in_(Config.DEFECT_CATEGORIES)
            ).count()
            assert count == len(Config.DEFECT_CATEGORIES)
