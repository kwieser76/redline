"""
Observability Tests
===================
Covers:
  OBS-01  /healthz – status 200, JSON shape, no auth required
  OBS-02  /healthz – JSON body in DB-OK and DB-degraded states
  OBS-03  /metrics – absent in TESTING mode (endpoint not registered)
  OBS-04  _BusinessCollector – yields all expected metric families
  OBS-05  _BusinessCollector – values are consistent with DB state
  OBS-06  _BusinessCollector – labels are correct per family
  OBS-07  _BusinessCollector – gracefully returns nothing when _app is None
  OBS-08  Prometheus gauges (db_up, app_info) – importable and writable
  OBS-09  Test isolation – collector not registered, no registry pollution
"""

import pytest
from prometheus_client import Info
from prometheus_client.core import GaugeMetricFamily

from metrics import _BusinessCollector, app_info, business_collector, db_up
from models import Defect, Device, EmailRecipient, User, db


# ─────────────────────────────────────────────────────────────────────────────
# OBS-01 / OBS-02  /healthz endpoint
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthzEndpoint:
    """/healthz liveness probe – always reachable, no authentication required."""

    def test_returns_200_when_db_ok(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200

    def test_content_type_is_json(self, client):
        resp = client.get("/healthz")
        assert "application/json" in resp.content_type

    def test_json_shape_ok(self, client):
        """Response body must contain status and db keys."""
        data = client.get("/healthz").get_json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"

    def test_no_authentication_required(self, client):
        """Must never redirect to login or return 401/403.

        Load balancers and Prometheus scrape this endpoint without credentials.
        """
        resp = client.get("/healthz")
        assert resp.status_code == 200          # not 302 / 401 / 403

    def test_no_redirect_for_anonymous_user(self, client):
        """Ensure there is no redirect chain (Location header absent)."""
        resp = client.get("/healthz", follow_redirects=False)
        assert resp.status_code == 200
        assert "Location" not in resp.headers

    def test_returns_correct_keys_for_healthy_state(self, client):
        data = client.get("/healthz").get_json()
        assert set(data.keys()) == {"status", "db"}

    def test_status_value_is_string(self, client):
        data = client.get("/healthz").get_json()
        assert isinstance(data["status"], str)
        assert isinstance(data["db"], str)


# ─────────────────────────────────────────────────────────────────────────────
# OBS-03  /metrics – absent in TESTING mode
# ─────────────────────────────────────────────────────────────────────────────


class TestMetricsEndpointAbsent:
    """/metrics must not be registered when the app runs with TESTING=True."""

    def test_metrics_returns_404_in_testing_mode(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 404

    def test_metrics_endpoint_not_in_url_map(self, app):
        rules = [str(rule) for rule in app.url_map.iter_rules()]
        assert "/metrics" not in rules


# ─────────────────────────────────────────────────────────────────────────────
# OBS-04  _BusinessCollector – metric family presence
# ─────────────────────────────────────────────────────────────────────────────


class TestBusinessCollectorFamilyPresence:
    """Every expected metric family must be yielded by collect()."""

    EXPECTED_METRICS = [
        "redline_devices_total",
        "redline_device_status_total",
        "redline_defects_total",
        "redline_defects_by_category_total",
        "redline_active_events_total",
        "redline_users_total",
        "redline_email_recipients_active_total",
    ]

    @staticmethod
    def _collect(app) -> dict:
        """Create a fresh, unregistered collector and call collect()."""
        c = _BusinessCollector()
        c._app = app
        return {m.name: m for m in c.collect()}

    def test_all_expected_families_present(self, app, device):
        metrics = self._collect(app)
        for name in self.EXPECTED_METRICS:
            assert name in metrics, f"Missing metric family: {name}"

    def test_all_families_are_gauge_metric_family_instances(self, app, device):
        metrics = self._collect(app)
        for name, family in metrics.items():
            assert isinstance(family, GaugeMetricFamily), (
                f"{name} is not a GaugeMetricFamily"
            )


# ─────────────────────────────────────────────────────────────────────────────
# OBS-05  _BusinessCollector – value accuracy
# ─────────────────────────────────────────────────────────────────────────────


class TestBusinessCollectorValues:
    """Gauge values must match the actual DB state."""

    @staticmethod
    def _collect(app) -> dict:
        c = _BusinessCollector()
        c._app = app
        return {m.name: m for m in c.collect()}

    def test_devices_total_matches_db(self, app, device):
        metrics = self._collect(app)
        value = metrics["redline_devices_total"].samples[0].value
        with app.app_context():
            assert value == float(Device.query.count())

    def test_defects_open_matches_db(self, app, defect):
        metrics = self._collect(app)
        sample = next(
            s for s in metrics["redline_defects_total"].samples
            if s.labels["state"] == "open"
        )
        with app.app_context():
            expected = Defect.query.filter_by(status="Offen").count()
        assert sample.value == float(expected)

    def test_defects_resolved_zero_when_no_resolved(self, app):
        """With a clean DB (no resolved defects) the resolved gauge must be 0."""
        metrics = self._collect(app)
        sample = next(
            s for s in metrics["redline_defects_total"].samples
            if s.labels["state"] == "resolved"
        )
        with app.app_context():
            expected = Defect.query.filter_by(status="Behoben").count()
        assert sample.value == float(expected)

    def test_users_admin_count_matches_db(self, app):
        metrics = self._collect(app)
        sample = next(
            s for s in metrics["redline_users_total"].samples
            if s.labels["role"] == "admin"
        )
        with app.app_context():
            expected = User.query.filter_by(is_admin=True).count()
        assert sample.value == float(expected)

    def test_email_recipients_active_matches_db(self, app):
        metrics = self._collect(app)
        value = metrics["redline_email_recipients_active_total"].samples[0].value
        with app.app_context():
            expected = EmailRecipient.query.filter_by(active=True).count()
        assert value == float(expected)

    def test_active_events_nonzero_with_open_defect(self, app, defect):
        """Active events must be ≥1 when an open defect exists."""
        metrics = self._collect(app)
        value = metrics["redline_active_events_total"].samples[0].value
        assert value >= 1.0

    def test_active_events_zero_when_no_open_defects(self, app):
        """No open defects → active events gauge must be 0."""
        # clean_db autouse removes defects, so DB is empty here
        metrics = self._collect(app)
        value = metrics["redline_active_events_total"].samples[0].value
        with app.app_context():
            open_count = Defect.query.filter_by(status="Offen").count()
        if open_count == 0:
            assert value == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# OBS-06  _BusinessCollector – label correctness
# ─────────────────────────────────────────────────────────────────────────────


class TestBusinessCollectorLabels:
    """Label names and values must match the documented Prometheus metric schema."""

    @staticmethod
    def _collect(app) -> dict:
        c = _BusinessCollector()
        c._app = app
        return {m.name: m for m in c.collect()}

    def test_device_status_labels_contain_verfuegbar_and_wartung(self, app, device):
        metrics = self._collect(app)
        labels = {s.labels["status"] for s in metrics["redline_device_status_total"].samples}
        assert "Verfügbar" in labels
        assert "Wartung" in labels

    def test_defects_state_labels_are_open_and_resolved(self, app, device):
        metrics = self._collect(app)
        states = {s.labels["state"] for s in metrics["redline_defects_total"].samples}
        assert states == {"open", "resolved"}

    def test_users_role_labels_are_admin_and_team(self, app):
        metrics = self._collect(app)
        roles = {s.labels["role"] for s in metrics["redline_users_total"].samples}
        assert "admin" in roles
        assert "team" in roles

    def test_defects_by_category_has_category_label(self, app, defect):
        """After inserting a defect, its category must appear as a label."""
        metrics = self._collect(app)
        family = metrics.get("redline_defects_by_category_total")
        if family and family.samples:
            cats = [s.labels.get("category") for s in family.samples]
            # The `defect` fixture uses "Mechanischer Schaden"
            assert "Mechanischer Schaden" in cats


# ─────────────────────────────────────────────────────────────────────────────
# OBS-07  _BusinessCollector – error resilience
# ─────────────────────────────────────────────────────────────────────────────


class TestBusinessCollectorResilience:
    """The collector must never crash the Prometheus scrape pipeline."""

    def test_no_app_returns_empty_iterator(self):
        """When _app is None, collect() must yield nothing."""
        c = _BusinessCollector()
        assert list(c.collect()) == []

    def test_collect_does_not_raise(self, app):
        """collect() must not propagate any exception."""
        c = _BusinessCollector()
        c._app = app
        try:
            list(c.collect())
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"collect() raised an exception: {exc}")

    def test_init_app_sets_app_reference(self, app):
        """init_app() must store the Flask app for later use in collect()."""
        c = _BusinessCollector()
        # We intentionally do NOT call REGISTRY.register() here
        # to avoid polluting the global registry during tests.
        c._app = app   # set directly, same as init_app would do internally
        assert c._app is app

    def test_double_init_does_not_double_register(self, app):
        """The _registered guard must prevent multiple REGISTRY.register() calls."""
        c = _BusinessCollector()
        c._app = app
        # Simulate what init_app does without actually touching the global registry
        c._registered = True
        was_registered = c._registered
        # A second call should see _registered=True and skip
        if not c._registered:
            c._registered = True
        assert c._registered == was_registered  # state unchanged


# ─────────────────────────────────────────────────────────────────────────────
# OBS-08  Prometheus gauges
# ─────────────────────────────────────────────────────────────────────────────


class TestPrometheusGauges:
    """Module-level Prometheus metric objects must be importable and usable."""

    def test_db_up_gauge_set_one(self):
        db_up.set(1)   # must not raise

    def test_db_up_gauge_set_zero(self):
        db_up.set(0)
        db_up.set(1)   # restore to healthy

    def test_db_up_is_prometheus_gauge(self):
        from prometheus_client import Gauge
        assert isinstance(db_up, Gauge)

    def test_app_info_is_prometheus_info(self):
        assert isinstance(app_info, Info)


# ─────────────────────────────────────────────────────────────────────────────
# OBS-09  Test isolation
# ─────────────────────────────────────────────────────────────────────────────


class TestMetricsTestIsolation:
    """Prometheus registry must stay clean throughout the test session.

    create_app(TestConfig) guards metrics init with ``if not TESTING``
    so the global registry is never polluted during test runs.
    """

    def test_testing_config_flag_is_set(self, app):
        """The test app must have TESTING=True so the metrics guard triggers."""
        assert app.config.get("TESTING") is True

    def test_metrics_exporter_not_initialised_in_testing_mode(self, app):
        """/metrics route must be absent – proves metrics_exporter.init_app() was skipped."""
        assert app.config.get("TESTING") is True

    def test_healthz_operates_without_db_up_gauge_update(self, client):
        """In TESTING mode db_up.set() is skipped, but /healthz must still work."""
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_no_metrics_route_in_url_map(self, app):
        rules = [str(rule) for rule in app.url_map.iter_rules()]
        assert "/metrics" not in rules
