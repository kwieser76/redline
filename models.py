from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_community = db.Column(db.Boolean, default=False)  # team_login user
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(
        db.String(20),
        default="Verfügbar",
        nullable=False,
    )  # "Verfügbar" | "Wartung"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    defects = db.relationship(
        "Defect", backref="device", lazy=True, order_by="Defect.created_at.desc()"
    )

    @property
    def open_defect_count(self) -> int:
        return sum(1 for d in self.defects if d.status == "Offen")

    def __repr__(self) -> str:
        return f"<Device {self.device_id}: {self.name}>"


class DefectCategory(db.Model):
    __tablename__ = "defect_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<DefectCategory {self.name}>"


class Defect(db.Model):
    __tablename__ = "defects"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    event_name = db.Column(db.String(120), nullable=False)
    project_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="Offen", nullable=False)  # "Offen" | "Behoben"
    reporter = db.Column(db.String(80), default="team_login")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_notes = db.Column(db.Text, default="")

    def __repr__(self) -> str:
        return f"<Defect {self.id} device={self.device_id} status={self.status}>"
