"""
Redline – SQLAlchemy database models.

All timestamps are stored in UTC.  Status fields use German values to match
the UI and FileMaker integration:
  Device.status          : "Verfügbar" | "Wartung" | "Reserviert"
  Defect.status          : "Offen"     | "Behoben"
  Defect.werkstatt_status: "Ausstehend" | "In Prüfung" | "In Reparatur" | "Repariert"
  User roles             : is_admin | is_disponent | is_werkstatt | is_api_user | (none → community)
"""

import json
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
    is_api_user = db.Column(db.Boolean, default=False, nullable=False)
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
        if self.is_api_user:
            return "api"
        return "community"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role}>"


class DeviceCategory(db.Model):
    """Product category for devices (e.g. Ton, Licht, Bühne, Video)."""

    __tablename__ = "device_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    color = db.Column(db.String(7), default="#6b7280", nullable=False)  # CSS hex color
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    devices = db.relationship("Device", back_populates="product_category", lazy=True)

    def __repr__(self) -> str:
        return f"<DeviceCategory {self.name}>"


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
    category_id = db.Column(
        db.Integer, db.ForeignKey("device_categories.id"), nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    product_category = db.relationship(
        "DeviceCategory", back_populates="devices", lazy=True
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


# --------------------------------------------------------------------------- #
#  NFR-SEC-003 – Audit Trail                                                   #
# --------------------------------------------------------------------------- #


class AuditLog(db.Model):
    """Immutable audit trail for security-relevant CRUD operations.

    Every CREATE / UPDATE / DELETE on core entities (Device, Defect, User,
    EmailRecipient) is recorded with a snapshot of the before/after values,
    the acting user, and the client IP address.

    Records are never updated or deleted – they form a tamper-evident log.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        db.Index("ix_audit_log_timestamp", "timestamp"),
        db.Index("ix_audit_log_user_id", "user_id"),
        db.Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # Nullable so the row survives if the user account is later deleted.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Denormalized for display after user deletion.
    username = db.Column(db.String(80), nullable=True)
    # "CREATE" | "UPDATE" | "DELETE"
    action = db.Column(db.String(20), nullable=False)
    # Human-readable model name: "Device", "Defect", "User", "EmailRecipient"…
    entity_type = db.Column(db.String(50), nullable=False)
    # Natural or primary key of the record (device_id string, defect int, etc.)
    entity_id = db.Column(db.String(50), nullable=True)
    # JSON snapshot of the record before the change (UPDATE / DELETE).
    old_value = db.Column(db.Text, nullable=True)
    # JSON snapshot of the record after the change (CREATE / UPDATE).
    new_value = db.Column(db.Text, nullable=True)
    # IPv4 or IPv6 address of the client.
    ip_address = db.Column(db.String(45), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog {self.action} {self.entity_type}/{self.entity_id}"
            f" by={self.username}>"
        )


def log_audit(
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    old: dict | None = None,
    new: dict | None = None,
) -> None:
    """Append an AuditLog entry to the current DB session (caller must commit).

    This function is intentionally a no-op if called outside a request context
    (e.g. during seeding) so it never breaks startup.

    Parameters
    ----------
    action      : ``"CREATE"``, ``"UPDATE"``, or ``"DELETE"``
    entity_type : model name, e.g. ``"Device"``, ``"Defect"``, ``"User"``
    entity_id   : natural or primary key of the changed record
    old         : dict snapshot before the change (UPDATE / DELETE)
    new         : dict snapshot after the change (CREATE / UPDATE)
    """
    try:
        from flask import g, request as _req
        from flask_login import current_user as _cu

        # Resolve acting user: web session (Flask-Login) or API (g.api_user).
        if _cu.is_authenticated:
            uid = _cu.id
            uname = _cu.username
        elif hasattr(g, "api_user") and g.api_user:
            uid = g.api_user.id
            uname = g.api_user.username
        else:
            uid = None
            uname = "system"

        entry = AuditLog(
            user_id=uid,
            username=uname,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            old_value=json.dumps(old, ensure_ascii=False, default=str) if old is not None else None,
            new_value=json.dumps(new, ensure_ascii=False, default=str) if new is not None else None,
            ip_address=_req.remote_addr,
        )
        db.session.add(entry)
    except RuntimeError:
        # Outside request context (seed, tests without request) – skip silently.
        pass
