"""
Redline – SQLAlchemy database models.

All timestamps are stored in UTC.  Status fields use German values to match
the UI and FileMaker integration:
  Device.status          : "Verfügbar" | "Wartung" | "Reserviert"
  Defect.status          : "Offen"     | "Behoben"
  Defect.werkstatt_status: "Ausstehend" | "In Prüfung" | "In Reparatur" | "Repariert"
  User roles             : is_admin=True | is_disponent=True | is_werkstatt=True | (none → community)
"""

from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_disponent = db.Column(db.Boolean, default=False, nullable=False)
    is_werkstatt = db.Column(db.Boolean, default=False, nullable=False)
    is_community = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    @property
    def role(self) -> str:
        """Human-readable role string for templates and logging."""
        if self.is_admin:
            return "admin"
        if self.is_disponent:
            return "disponent"
        if self.is_werkstatt:
            return "werkstatt"
        return "community"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role}>"


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(
        db.String(20),
        default="Verfügbar",
        nullable=False,
        index=True,
    )  # "Verfügbar" | "Wartung" | "Reserviert"
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Cascade: deleting a device also deletes all its defect records.
    defects = db.relationship(
        "Defect",
        backref="device",
        lazy=True,
        order_by="Defect.created_at.desc()",
        cascade="all, delete-orphan",
    )

    @property
    def open_defect_count(self) -> int:
        return sum(1 for d in self.defects if d.status == "Offen")

    def __repr__(self) -> str:
        return f"<Device {self.device_id}: {self.name}>"


class EmailRecipient(db.Model):
    __tablename__ = "email_recipients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EmailRecipient {self.email}>"


class DefectCategory(db.Model):
    __tablename__ = "defect_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DefectCategory {self.name}>"


class Defect(db.Model):
    __tablename__ = "defects"
    __table_args__ = (
        # Indexes on the most common filter/join columns
        db.Index("ix_defects_device_id", "device_id"),
        db.Index("ix_defects_status", "status"),
        db.Index("ix_defects_project_number", "project_number"),
        db.Index("ix_defects_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    event_name = db.Column(db.String(120), nullable=False)
    project_number = db.Column(db.String(50), nullable=False)
    status = db.Column(
        db.String(20), default="Offen", nullable=False
    )  # "Offen" | "Behoben"
    werkstatt_status = db.Column(
        db.String(20), default="Ausstehend", nullable=False
    )  # "Ausstehend" | "In Prüfung" | "In Reparatur" | "Repariert"
    reporter = db.Column(db.String(80), default="team_login", nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_notes = db.Column(db.Text, default="")

    # Comments (werkstatt notes + photos)
    comments = db.relationship(
        "Comment",
        backref="defect",
        lazy=True,
        order_by="Comment.created_at.asc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Defect {self.id} device={self.device_id} status={self.status}>"


class Comment(db.Model):
    """A werkstatt note (with optional photo) attached to a defect."""

    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    defect_id = db.Column(
        db.Integer,
        db.ForeignKey("defects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized author info: survives user deletion
    username = db.Column(db.String(80), nullable=False)
    user_role = db.Column(db.String(20), nullable=False, default="community")
    text = db.Column(db.Text, nullable=False)
    photo_path = db.Column(db.String(500), nullable=True)  # filename in uploads folder
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Comment {self.id} defect={self.defect_id} by={self.username}>"
