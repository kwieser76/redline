"""
Redline – Prometheus metrics.

Two layers:
  1. HTTP metrics – auto-instrumented by prometheus-flask-exporter (see extensions.py).
  2. Business & health metrics – defined here via a lazy custom collector that
     queries SQLAlchemy only when Prometheus scrapes /metrics, so there is zero
     overhead on normal request paths.

Usage in create_app():
    from metrics import db_up, business_collector, app_info
    business_collector.init_app(app)
    app_info.info({"version": "1.0", "env": env})
"""

from prometheus_client import Gauge, Info, REGISTRY
from prometheus_client.core import GaugeMetricFamily

# ---------------------------------------------------------------------------
# Singleton gauges updated by the /healthz endpoint
# ---------------------------------------------------------------------------

db_up: Gauge = Gauge(
    "redline_db_up",
    "1 if the database is reachable, 0 otherwise",
)

# ---------------------------------------------------------------------------
# App info (labels set once at startup)
# ---------------------------------------------------------------------------

app_info: Info = Info(
    "redline_app",
    "Redline application metadata (version, environment).",
)

# ---------------------------------------------------------------------------
# Business collector – queries DB on every Prometheus scrape
# ---------------------------------------------------------------------------


class _BusinessCollector:
    """Custom Prometheus collector that fetches business metrics from the DB.

    Registered with REGISTRY once via init_app() so that Prometheus pulls
    fresh data on every scrape without any background thread.
    """

    def __init__(self) -> None:
        self._app = None
        self._registered = False

    def init_app(self, flask_app) -> None:
        """Bind the Flask application and register this collector."""
        self._app = flask_app
        if not self._registered:
            REGISTRY.register(self)
            self._registered = True

    # ------------------------------------------------------------------ #
    # prometheus_client protocol                                           #
    # ------------------------------------------------------------------ #

    def collect(self):  # noqa: C901
        if self._app is None:
            return

        from models import db, Device, Defect, User, EmailRecipient
        from sqlalchemy import func

        try:
            with self._app.app_context():
                # ── Devices ────────────────────────────────────────────
                yield GaugeMetricFamily(
                    "redline_devices_total",
                    "Total registered devices.",
                    value=float(Device.query.count()),
                )

                # Device status breakdown
                dsf = GaugeMetricFamily(
                    "redline_device_status_total",
                    "Devices grouped by status.",
                    labels=["status"],
                )
                for status_val in ["Verfügbar", "Wartung"]:
                    dsf.add_metric(
                        [status_val],
                        float(Device.query.filter_by(status=status_val).count()),
                    )
                yield dsf

                # ── Defects ────────────────────────────────────────────
                df = GaugeMetricFamily(
                    "redline_defects_total",
                    "Defects grouped by status.",
                    labels=["state"],
                )
                df.add_metric(
                    ["open"], float(Defect.query.filter_by(status="Offen").count())
                )
                df.add_metric(
                    ["resolved"],
                    float(Defect.query.filter_by(status="Behoben").count()),
                )
                yield df

                # Defects per category
                cat_counts = (
                    db.session.query(Defect.category, func.count(Defect.id))
                    .group_by(Defect.category)
                    .all()
                )
                cf = GaugeMetricFamily(
                    "redline_defects_by_category_total",
                    "Total defects per category (all time).",
                    labels=["category"],
                )
                for cat, cnt in cat_counts:
                    cf.add_metric([cat], float(cnt))
                yield cf

                # ── Events ────────────────────────────────────────────
                active_events = (
                    db.session.query(
                        func.count(func.distinct(Defect.project_number))
                    )
                    .filter(Defect.status == "Offen")
                    .scalar()
                    or 0
                )
                yield GaugeMetricFamily(
                    "redline_active_events_total",
                    "Distinct project numbers that have at least one open defect.",
                    value=float(active_events),
                )

                # ── Users ─────────────────────────────────────────────
                uf = GaugeMetricFamily(
                    "redline_users_total",
                    "Users by role.",
                    labels=["role"],
                )
                uf.add_metric(
                    ["admin"], float(User.query.filter_by(is_admin=True).count())
                )
                uf.add_metric(
                    ["team"], float(User.query.filter_by(is_admin=False).count())
                )
                yield uf

                # ── Email recipients ───────────────────────────────────
                yield GaugeMetricFamily(
                    "redline_email_recipients_active_total",
                    "Active email recipients.",
                    value=float(
                        EmailRecipient.query.filter_by(active=True).count()
                    ),
                )

        except Exception:
            # Collector must never crash Prometheus scrape.
            pass


# Singleton – imported and wired by app.py
business_collector = _BusinessCollector()
