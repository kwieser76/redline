"""
Authentication blueprint – /auth/*
"""

from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import limiter
from models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# --------------------------------------------------------------------------- #
#  NFR-SEC-002 – Generic RBAC decorator factory                                #
# --------------------------------------------------------------------------- #


def require_role(*roles: str):
    """Decorator factory that enforces role-based access control (NFR-SEC-002).

    Checks ``current_user.role`` which is one of:
    ``'admin'``, ``'disponent'``, ``'werkstatt'``, ``'api'``, ``'community'``.

    Usage::

        @require_role('admin')
        def admin_only_view(): ...

        @require_role('admin', 'disponent')
        def manager_view(): ...

    The existing ``@admin_required``, ``@disponent_required``,
    ``@werkstatt_required`` decorators are semantically equivalent to
    ``@require_role('admin')``, ``@require_role('admin', 'disponent')``,
    ``@require_role('admin', 'werkstatt')`` respectively.
    """

    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return decorator


def _is_safe_url(target: str | None) -> bool:
    """Return True only if *target* is a relative URL with no host or scheme.

    This prevents open-redirect attacks where an attacker supplies a
    ``?next=http://evil.com`` parameter to redirect victims off-site after
    a successful login.
    """
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.netloc and not parsed.scheme


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=False)
            # NFR-SEC-006: record login time for time-based session expiry
            session["_login_time"] = datetime.now(timezone.utc).isoformat()
            next_page = request.args.get("next")
            safe_next = next_page if _is_safe_url(next_page) else None
            return redirect(safe_next or url_for("index"))
        flash("Ungültiger Benutzername oder Passwort.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sie wurden abgemeldet.", "info")
    return redirect(url_for("auth.login"))
