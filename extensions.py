"""
Shared Flask extension instances.

Initialized here so that blueprints (in the routes/ package) can import
them without creating circular dependencies.  The app factory in app.py
calls .init_app(app) on each of them.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from prometheus_flask_exporter import PrometheusMetrics

# Rate limiter – key on the real client IP.
# init_app() is called in create_app(); blueprints import and use decorators.
limiter = Limiter(key_func=get_remote_address)

# Database migration manager (Alembic via Flask-Migrate).
migrate = Migrate()

# Prometheus HTTP metrics exporter.
# Exposes /metrics and auto-instruments every Flask route with:
#   flask_http_request_total{method, path, status}
#   flask_http_request_duration_seconds{method, path, status}
# init_app() is called in create_app() (skipped in TESTING mode).
metrics_exporter = PrometheusMetrics.for_app_factory()
