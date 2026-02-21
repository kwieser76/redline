# Redline – Technical Documentation

**Version:** 1.0.0
**Stack:** Python 3.11 · Flask 3.0 · SQLAlchemy 2.0 · SQLite / PostgreSQL
**Last updated:** 2026-02

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Project Structure](#2-project-structure)
3. [Architecture](#3-architecture)
4. [Database Schema](#4-database-schema)
5. [Configuration & Environments](#5-configuration--environments)
6. [Security Architecture](#6-security-architecture)
7. [Blueprint & Route Map](#7-blueprint--route-map)
8. [Email Flow](#8-email-flow)
9. [QR Code Generation](#9-qr-code-generation)
10. [FileMaker Integration](#10-filemaker-integration)
11. [Rate Limiting](#11-rate-limiting)
12. [Logging](#12-logging)
13. [Testing Strategy](#13-testing-strategy)
14. [Deployment Architecture](#14-deployment-architecture)
15. [Non-Functional Requirements](#15-non-functional-requirements)
16. [Observability](#16-observability)

---

## 1. System Overview

Redline is a **mobile-first, QR-code-based defect reporting system** for event engineering.

```
┌─────────────────────────────────────────────────────────────┐
│                        USERS                                │
│                                                             │
│  Technician (iPhone)    Admin (PC-Browser)  Ops (Browser)  │
│  ┌──────────────────┐   ┌────────────────┐  ┌────────────┐ │
│  │  Scan QR Code    │   │ Admin Dashboard│  │  Grafana   │ │
│  │  Fill Form       │   │ Manage Devices │  │ Dashboard  │ │
│  │  Send mailto:    │   │ Resolve Defects│  │            │ │
│  └────────┬─────────┘   └──────┬─────────┘  └─────┬──────┘ │
└───────────┼────────────────────┼─────────────────┼────────┘
            │ HTTPS              │ HTTPS            │ HTTP
            ▼                    ▼                  ▼
┌─────────────────────────┐   ┌─────────┐  ┌────────────────┐
│    Flask Application    │   │Prometheus│  │    Grafana     │
│                         │◄──│ scrapes │  │ (provisioned)  │
│  /healthz  /metrics     │   │/metrics │  └────────┬───────┘
│  routes/   api.py       │   │every 15s│           │
│  models.py metrics.py   │   └─────────┘           │ pulls
│       │                 │        ▲                 │
│   SQLAlchemy ORM        │        └─────────────────┘
│       │                 │
│  SQLite / PostgreSQL    │
└─────────────────────────┘
       │                │
       ▼                ▼
FileMaker API      SMTP Server
(optional)         (optional)
```

---

## 2. Project Structure

```
Redline-/
├── app.py                  # App factory (create_app), seed, error handlers, /healthz
├── config.py               # DevelopmentConfig / ProductionConfig / TestConfig
├── extensions.py           # Shared Flask-Limiter, Flask-Migrate, PrometheusMetrics
├── metrics.py              # Prometheus gauges + lazy business metric collector
├── models.py               # SQLAlchemy ORM models + db instance
├── api.py                  # REST API blueprint (/api/v1/*)
├── notifications.py        # Email helpers (defect notification, event report)
├── filemaker.py            # FileMaker Data API client (optional integration)
├── requirements.txt        # Pinned production dependencies
├── requirements-test.txt   # Test-only additions (pytest, coverage)
├── Dockerfile              # Multi-stage production image
├── docker-compose.yml      # Docker Compose: redline + prometheus + grafana
├── .env.example            # Environment variable template
│
├── prometheus/
│   └── prometheus.yml      # Prometheus scrape config (15s interval, 30d retention)
│
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/prometheus.yml   # Auto-wired Prometheus datasource
│   │   └── dashboards/dashboard.yml     # Dashboard folder provider config
│   └── dashboards/
│       └── redline.json    # Operations dashboard (4 rows, 16 panels)
│
├── routes/                 # Web UI blueprints
│   ├── __init__.py
│   ├── auth.py             # /auth/login, /auth/logout
│   ├── report.py           # /report/<device_id>
│   └── admin.py            # /admin/* (all admin routes + admin_required)
│
├── static/
│   ├── css/style.css       # Redline brand CSS (black/red, Barlow Condensed)
│   ├── js/main.js          # Auto-dismiss alerts, confirm dialogs
│   ├── img/logo.svg        # Redline wordmark SVG
│   ├── openapi.yaml        # OpenAPI 3.0 specification (Swagger source)
│   └── qrcodes/            # Generated QR code PNGs (gitignored)
│
├── templates/
│   ├── base.html           # Layout: navbar, flash messages, Google Fonts
│   ├── login.html
│   ├── report_defect.html  # Mobile-optimised defect form
│   ├── defect_success.html # Success page with mailto: button
│   ├── error.html          # Generic error page (403, 404, 429)
│   ├── api_docs.html       # Swagger UI wrapper
│   └── admin/              # Admin dashboard templates (9 files)
│
├── tests/
│   ├── conftest.py         # Session fixtures, TestConfig, clean_db
│   ├── test_auth.py        # Authentication flow
│   ├── test_models.py      # ORM model unit tests
│   ├── test_api.py         # REST API endpoint tests
│   ├── test_admin.py       # Admin route tests
│   ├── test_report.py      # Defect form tests
│   ├── test_notifications.py
│   ├── test_nfr.py         # Non-functional requirements tests
│   └── test_business.py    # End-to-end business workflow tests
│
└── docs/
    ├── API.md
    ├── TECHNICAL.md        # ← this file
    ├── INSTALLATION.md
    └── BUSINESS.md
```

---

## 3. Architecture

### App Factory Pattern

`create_app(config_class)` in `app.py` is the single entry point:

```
create_app(config_class)
    │
    ├── app.config.from_object(config_class)
    ├── config_class.validate()          ← fail-fast on bad config
    ├── db.init_app(app)
    ├── migrate.init_app(app, db)
    ├── Mail(app)
    ├── limiter.init_app(app)
    ├── LoginManager(app)
    ├── @after_request → set_security_headers
    ├── register_blueprint(auth_bp)
    ├── register_blueprint(report_bp)
    ├── register_blueprint(admin_bp)
    ├── register_blueprint(api_bp)
    ├── standalone routes (/, /api/docs)
    ├── error handlers (403, 404, 429)
    └── db.create_all() + _seed_db()
```

### Extension Initialisation (extensions.py)

Extensions that need to be imported by blueprints before the app is created are defined in `extensions.py` as uninitialised instances:

```python
limiter  = Limiter(key_func=get_remote_address)   # rate limiting
migrate  = Migrate()                               # Alembic migrations
```

`init_app(app)` is called in `create_app()`.

### Request Lifecycle

```
Request
  │
  ├── Flask-Login: load_user()
  ├── Flask-Limiter: check rate limit
  ├── Blueprint route handler
  │     ├── @login_required / @admin_required / @_require_auth()
  │     ├── SQLAlchemy ORM queries
  │     └── Return response
  └── @after_request: set_security_headers()
```

---

## 4. Database Schema

### Entity-Relationship Diagram

```
users
  id           PK  INTEGER
  username          VARCHAR(80)   UNIQUE  NOT NULL  INDEX
  password_hash     VARCHAR(255)          NOT NULL
  is_admin          BOOLEAN       DEFAULT FALSE
  is_community      BOOLEAN       DEFAULT FALSE
  created_at        DATETIME      DEFAULT UTC NOW

devices
  id           PK  INTEGER
  device_id         VARCHAR(50)   UNIQUE  NOT NULL  INDEX
  name              VARCHAR(120)          NOT NULL
  description       TEXT          DEFAULT ''
  status            VARCHAR(20)   DEFAULT 'Verfügbar'  INDEX
  created_at        DATETIME      DEFAULT UTC NOW
  │
  └──< defects (cascade delete)

defects
  id           PK  INTEGER
  device_id    FK  INTEGER  → devices.id  NOT NULL  INDEX
  category          VARCHAR(80)           NOT NULL
  description       TEXT                  NOT NULL
  event_name        VARCHAR(120)          NOT NULL
  project_number    VARCHAR(50)           NOT NULL  INDEX
  status            VARCHAR(20)   DEFAULT 'Offen'   INDEX
  reporter          VARCHAR(80)   DEFAULT 'team_login'
  created_at        DATETIME      DEFAULT UTC NOW   INDEX
  resolved_at       DATETIME      NULLABLE
  resolution_notes  TEXT          DEFAULT ''

email_recipients
  id           PK  INTEGER
  name              VARCHAR(120)          NOT NULL
  email             VARCHAR(255)  UNIQUE  NOT NULL  INDEX
  active            BOOLEAN       DEFAULT TRUE
  created_at        DATETIME      DEFAULT UTC NOW

defect_categories
  id           PK  INTEGER
  name              VARCHAR(80)   UNIQUE  NOT NULL  INDEX
  sort_order        INTEGER       DEFAULT 0
  created_at        DATETIME      DEFAULT UTC NOW
```

### Status Values

| Model | Field | Values |
|-------|-------|--------|
| `Device` | `status` | `Verfügbar` · `Wartung` |
| `Defect` | `status` | `Offen` · `Behoben` |

### Cascade Delete

`Device.defects` uses `cascade="all, delete-orphan"`.
Deleting a device automatically deletes all its defect records at the ORM layer.

### Indexes

Performance indexes are defined on all high-frequency filter columns:

| Table | Indexed Column(s) |
|-------|-------------------|
| `users` | `username` |
| `devices` | `device_id`, `status` |
| `defects` | `device_id`, `status`, `project_number`, `created_at` |
| `email_recipients` | `email` |
| `defect_categories` | `name` |

---

## 5. Configuration & Environments

Three config classes in `config.py`:

| Class | `FLASK_ENV` | Debug | DB | Validation |
|-------|------------|-------|----|-----------|
| `DevelopmentConfig` | `development` | On | SQLite file | Warn only |
| `ProductionConfig` | `production` | Off | Any | Hard exit on errors |
| `TestConfig` | — (passed directly) | Off | `:memory:` | Skipped |

### Key Config Values

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session signing key | **Placeholder – must change** |
| `DATABASE_URL` | SQLAlchemy URI | `sqlite:///redline.db` |
| `APP_BASE_URL` | Public URL for QR codes | `http://localhost:5000` |
| `WORKSHOP_EMAIL` | Seed email recipient | `werkstatt@redline.local` |
| `MAIL_SERVER` | SMTP host | `smtp.gmail.com` |
| `RATELIMIT_ENABLED` | Toggle rate limiting | `True` (False in tests) |
| `RATELIMIT_STORAGE_URL` | Limiter backend | `memory://` |

### Production Validation (`ProductionConfig.validate()`)

The factory calls `validate()` before the first request. `ProductionConfig` hard-exits (`sys.exit(1)`) if:

- `SECRET_KEY` is still the default placeholder
- `APP_BASE_URL` contains `localhost`
- `APP_BASE_URL` does not start with `https://`

---

## 6. Security Architecture

### Authentication

| Layer | Mechanism |
|-------|-----------|
| Web UI | Session cookie via Flask-Login (`@login_required`) |
| REST API | HTTP Basic Auth checked on every request (`@_require_auth()`) |

### Authorisation

| Role | Decorator | Access |
|------|-----------|--------|
| Any authenticated | `@login_required` | Report form, basic views |
| Admin | `@admin_required` | All `/admin/*` routes |
| Admin (API) | `@_require_auth(admin_only=True)` | Write/delete API endpoints |

### Password Storage

Passwords are hashed with **PBKDF2-HMAC-SHA256** + random salt via `werkzeug.security.generate_password_hash()`.

Minimum length: **8 characters** (enforced in `routes/admin.py`).

### Security Headers (applied to every response)

| Header | Value |
|--------|-------|
| `X-Frame-Options` | `SAMEORIGIN` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` *(HTTPS + production only)* |

### CSRF Protection

Flask-WTF CSRF tokens protect all HTML form submissions.
The REST API uses stateless Basic Auth and does not require CSRF tokens.

### Rate Limiting

See [Section 11](#11-rate-limiting).

---

## 7. Blueprint & Route Map

### Web UI

| Blueprint | Prefix | Routes |
|-----------|--------|--------|
| `auth_bp` | `/auth` | `GET/POST /login`, `GET /logout` |
| `report_bp` | `/report` | `GET/POST /<device_id>`, `GET /<device_id>/success` |
| `admin_bp` | `/admin` | Dashboard, devices, QR, history, repair, users, defects, event-report, recipients, categories |

### REST API

| Blueprint | Prefix | Routes |
|-----------|--------|--------|
| `api_bp` | `/api/v1` | All API endpoints (see `docs/API.md`) |

### Standalone

| Route | Handler |
|-------|---------|
| `GET /` | Redirects based on user role |
| `GET /api/docs` | Swagger UI |
| `GET /healthz` | Liveness + readiness probe (DB check, updates `redline_db_up`) |
| `GET /metrics` | Prometheus scrape endpoint *(non-TESTING mode only)* |

---

## 8. Email Flow

Two distinct email mechanisms exist:

### Defect Notification (mailto: link)

Used by technicians on the mobile defect form.

```
Technician submits form
  → Defect saved to DB
  → /report/<device_id>/success rendered
  → Server builds mailto: URL from active EmailRecipient rows
  → Page renders a button: <a href="mailto:...">
  → Technician taps button → native mail client opens with pre-filled content
  → Technician sends email manually
```

**No SMTP configuration needed** for this flow.

### Event Summary Report (SMTP)

Used by admins to send a post-event summary.

```
Admin fills event-report form (event name, project number, recipient)
  → POST /admin/event-report
  → Defects queried from DB
  → send_event_summary_report(mail, ...) called
  → Flask-Mail sends via configured SMTP server
```

**Requires** `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD` in `.env`.

---

## 9. QR Code Generation

```
Admin: GET /admin/qr-page/<device_id>
         → Renders QR code inline as PNG (base64)
         → Shows report URL: {APP_BASE_URL}/report/{device_id}

Admin: GET /admin/qr/<device_id>
         → Generates PNG via qrcode library (Pillow backend)
         → Streams as download (Content-Disposition: attachment)

API:   GET /api/v1/devices/<device_id>/qr
         → Same generation, streamed as image/png response
```

The `APP_BASE_URL` config value is critical: it determines the URL encoded in each QR code. Must be set to the public hostname in production.

---

## 10. FileMaker Integration

`filemaker.py` implements a thin wrapper around the **FileMaker Data API v2**.

### Session Flow

```
FileMakerClient._login()
  POST /fmi/data/v2/databases/{DB}/sessions
  → receives Bearer token

[perform operations]

FileMakerClient._logout()
  DELETE /fmi/data/v2/databases/{DB}/sessions/{token}
```

### Operations

| Method | FileMaker Layout | Trigger |
|--------|-----------------|---------|
| `update_device_status(device_id, status)` | `Geräte` | Defect created / resolved |
| `create_defect_record(payload)` | `Defekte` | Defect created via API |

### Graceful Degradation (POC Mode)

If `FILEMAKER_PASSWORD` is not set, both methods log what they **would** do and return `True` without making any network call. This allows the application to function fully without a FileMaker instance.

All FileMaker errors are caught, logged at `ERROR` level, and do **not** propagate to the user.

---

## 11. Rate Limiting

Implemented with **Flask-Limiter 3.12** backed by the `limiter` instance in `extensions.py`.

| Endpoint | Limit |
|----------|-------|
| `POST /auth/login` | 10 / minute per IP |
| All API endpoints (global default) | 200 / hour, 50 / minute per IP |

Storage backend defaults to `memory://` (single-process). For multi-worker deployments configure a Redis backend:

```env
RATELIMIT_STORAGE_URL=redis://redis:6379/0
```

Rate limiting is **disabled** in the test environment (`RATELIMIT_ENABLED = False` in `TestConfig`).

---

## 12. Logging

The application uses Python's standard `logging` module, configured in `app.py`:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
```

| Module | Log events |
|--------|-----------|
| `app.py` | Seed data creation, default credential warnings |
| `filemaker.py` | FileMaker login/logout, sync operations, errors |
| `notifications.py` | Email send success/failure |

In Docker, logs are written to stdout/stderr and captured by the Docker logging driver (`json-file`, max 10 MB × 5 files).

---

## 13. Testing Strategy

### Test Pyramid

```
        ┌──────────────────────┐
        │   test_business      │  End-to-end workflow tests (BW-01…10)
        │   (50+ tests)        │
        ├──────────────────────┤
        │   test_nfr           │  Security, performance, DB integrity
        │   test_observability │  /healthz, collector, gauges, isolation
        │   (80+ tests)        │
        ├──────────────────────┤
        │   test_api           │  REST API contract (80+ tests)
        │   test_admin         │  Admin route tests
        │   test_report        │  Defect form tests
        │   test_auth          │  Auth flow tests
        │   test_notifications │  Email send tests
        ├──────────────────────┤
        │   test_models        │  ORM unit tests (35 tests)
        └──────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| In-memory SQLite (`":memory:"`) | Fast, isolated, no disk I/O |
| Session-scoped app, function-scoped `clean_db` | Create schema once; wipe data between tests |
| Plain dict fixtures | Avoid SQLAlchemy `DetachedInstanceError` across app contexts |
| `RATELIMIT_ENABLED = False` | Prevent throttling during rapid test execution |
| `WTF_CSRF_ENABLED = False` | Allow form POST without CSRF token in tests |
| `MAIL_SUPPRESS_SEND = True` | No real emails sent; Flask-Mail stubs the send |

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage report
pytest tests/ --cov=. --cov-report=html

# Single file
pytest tests/test_nfr.py -v

# Specific test class
pytest tests/test_business.py::TestDefectLifecycle -v
```

---

## 14. Deployment Architecture

### Development

```
python app.py          # Flask built-in dev server, port 5000
                       # Debug mode ON, hot-reload
```

### Production (Docker)

```
docker compose up -d

Nginx (reverse proxy, TLS termination)
  └── gunicorn (WSGI, 2 workers × 4 threads)         :8000
        └── Flask app (create_app())
              ├── /healthz  (liveness probe)
              ├── /metrics  (Prometheus scrape target)
              └── SQLite on named Docker volume  (/app/data/redline.db)

Prometheus :9090
  └── scrapes Flask /metrics every 15 s
        └── stores TSDB in prometheus_data volume (30-day retention)

Grafana :3000
  └── reads from Prometheus (auto-provisioned datasource)
        └── serves "Redline Operations Dashboard" (auto-provisioned)
```

Multi-stage Dockerfile:
1. **builder** – installs Python deps into `/opt/venv`
2. **runtime** – copies only the venv + app code; runs as non-root user `redline`

Named volumes: `redline_data`, `redline_qrcodes`, `prometheus_data`, `grafana_data`

### Production (Bare Metal with Nginx)

```bash
# Gunicorn
gunicorn --bind 127.0.0.1:8000 --workers 2 --threads 4 app:app

# Nginx (excerpt)
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Set `RATELIMIT_STORAGE_URL=redis://localhost:6379/0` when running multiple gunicorn workers to share rate-limit counters.

---

## 15. Non-Functional Requirements

| ID | Category | Requirement | Implementation |
|----|----------|-------------|----------------|
| NFR-01 | Security | All HTTP responses include defensive headers | `@after_request` hook |
| NFR-02 | Security | Login throttled to 10 req/min | Flask-Limiter |
| NFR-03 | Security | Passwords hashed with PBKDF2 + salt | Werkzeug `generate_password_hash` |
| NFR-04 | Security | Minimum password length 8 characters | `routes/admin.py` validation |
| NFR-05 | Security | HSTS header in HTTPS production | Conditional `after_request` |
| NFR-06 | Security | API 401 includes `WWW-Authenticate` header | `_json_error()` helper |
| NFR-07 | Reliability | Cascade delete: device deletion removes defects | `cascade="all, delete-orphan"` |
| NFR-08 | Reliability | DB connection pool with pre-ping | `SQLALCHEMY_ENGINE_OPTIONS` |
| NFR-09 | Reliability | FileMaker errors non-blocking | try/except in `filemaker.py` |
| NFR-10 | Performance | DB indexes on all filter/join columns | `__table_args__` in `models.py` |
| NFR-11 | Performance | Pagination cap at 200 items/page | `api.py` `min(..., 200)` |
| NFR-12 | Observability | Structured log format with timestamps | `logging.basicConfig` |
| NFR-13 | Config | Production startup validation (fail-fast) | `ProductionConfig.validate()` |
| NFR-14 | Deployment | Non-root Docker user | `useradd redline` in Dockerfile |
| NFR-15 | Deployment | Docker health check | `HEALTHCHECK` in Dockerfile → `/healthz` |
| NFR-16 | Observability | Prometheus metrics endpoint exposed | `prometheus-flask-exporter` → `/metrics` |
| NFR-17 | Observability | Business metrics queryable in real time | `metrics.py` – lazy DB collector |
| NFR-18 | Observability | Operations dashboard zero-config | Grafana auto-provisioning |
| NFR-19 | Observability | Liveness/readiness probe with DB check | `GET /healthz` → 200 / 503 |

---

## 16. Observability

### Architecture

The observability stack runs as three Docker Compose services and requires zero manual configuration:

```
Flask (:8000)
  ├── GET /healthz        Liveness + readiness probe (JSON, no auth)
  └── GET /metrics        Prometheus text format (auto-instrumented routes + business metrics)

Prometheus (:9090)
  └── scrapes /metrics every 15 s
  └── retains 30 days of TSDB data

Grafana (:3000)
  └── datasource: Prometheus (auto-provisioned via YAML)
  └── dashboard:  redline.json (auto-provisioned, default home page)
```

### /healthz Endpoint

| Attribute | Value |
|-----------|-------|
| Method | `GET` |
| Auth | None (public) |
| Success | `200 {"status": "ok", "db": "ok"}` |
| Degraded | `503 {"status": "degraded", "db": "error"}` |
| Side effect | Sets `redline_db_up` gauge to 1 or 0 |

Used by Docker `HEALTHCHECK`, load balancers, and Prometheus alert rules.

### Prometheus Metrics

#### HTTP Metrics (auto-instrumented)

| Metric | Type | Labels |
|--------|------|--------|
| `flask_http_request_total` | Counter | `method`, `path`, `status` |
| `flask_http_request_duration_seconds` | Histogram | `method`, `path`, `status` |
| `flask_http_request_exceptions_total` | Counter | `method`, `path` |
| `process_resident_memory_bytes` | Gauge | – |
| `process_cpu_seconds_total` | Counter | – |

#### Business Metrics (lazy DB collector)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `redline_devices_total` | Gauge | – | Total registered devices |
| `redline_device_status_total` | Gauge | `status` | Devices by status (Verfügbar / Wartung) |
| `redline_defects_total` | Gauge | `state` | Defects by state (open / resolved) |
| `redline_defects_by_category_total` | Gauge | `category` | Defects by category (all-time) |
| `redline_active_events_total` | Gauge | – | Projects with at least one open defect |
| `redline_users_total` | Gauge | `role` | Users by role (admin / team) |
| `redline_email_recipients_active_total` | Gauge | – | Active email recipients |
| `redline_db_up` | Gauge | – | 1 = DB reachable (set by `/healthz`) |
| `redline_app_info` | Info | `version`, `environment` | App metadata |

#### Collector Design

`_BusinessCollector` in `metrics.py` implements the `prometheus_client` collector protocol:

```python
class _BusinessCollector:
    def collect(self):          # called on every Prometheus scrape
        with self._app.app_context():
            yield GaugeMetricFamily("redline_devices_total", ...)
            ...                 # queries DB; yields GaugeMetricFamily objects
```

**Key properties:**
- **Zero request overhead** – DB queries only happen when Prometheus scrapes `/metrics`
- **Lazy initialization** – `init_app(flask_app)` called once at startup, skipped in `TESTING` mode
- **Error-safe** – any exception inside `collect()` is silently caught so scrapes never fail

### Grafana Dashboard

The dashboard (`grafana/dashboards/redline.json`) is auto-loaded by the provisioning provider and set as the default home page.

#### Row 1 – System Health

| Panel | Query | Type |
|-------|-------|------|
| App Status | `up{job="redline"}` | Stat (green UP / red DOWN) |
| DB Status | `redline_db_up` | Stat (green OK / red ERROR) |
| Process Uptime | `time() - process_start_time_seconds{job="redline"}` | Stat |
| HTTP 5xx Error Rate | `sum(rate(flask_http_request_total{status=~"5.."}[5m])) / sum(rate(...))` | Stat |
| Request Rate | `sum(rate(flask_http_request_total[1m]))` | Stat |

#### Row 2 – HTTP Traffic

| Panel | Type |
|-------|------|
| Requests/sec by Status Class (2xx/3xx/4xx/5xx) | Time series |
| Request Latency p50 / p95 / p99 | Time series |
| HTTP Status Distribution | Donut chart |
| Top Endpoints by Request Count | Table |

#### Row 3 – Business Metrics

| Panel | Metric |
|-------|--------|
| Total Devices | `redline_devices_total` |
| Open Defects | `redline_defects_total{state="open"}` |
| Active Events | `redline_active_events_total` |
| Active Email Recipients | `redline_email_recipients_active_total` |
| Total Users | `sum(redline_users_total)` |
| Devices in Maintenance | `redline_device_status_total{status="Wartung"}` |
| Defects by Status | Donut (open vs. resolved) |
| Defects by Category | Horizontal bar chart |

#### Row 4 – System Resources

| Panel | Metric |
|-------|--------|
| Process Memory (RSS + Virtual) | `process_resident_memory_bytes` |
| CPU Usage | `rate(process_cpu_seconds_total[1m]) * 100` |

### Test Coverage (`tests/test_observability.py`)

| Class | Tests | What is verified |
|-------|-------|-----------------|
| `TestHealthzEndpoint` | 7 | Status code, JSON shape, no auth required, no redirect |
| `TestMetricsEndpointAbsent` | 2 | `/metrics` not registered in `TESTING` mode |
| `TestBusinessCollectorFamilyPresence` | 2 | All 7 metric families present and correctly typed |
| `TestBusinessCollectorValues` | 7 | Values match live DB state |
| `TestBusinessCollectorLabels` | 4 | Label names and values match schema |
| `TestBusinessCollectorResilience` | 4 | No crash on missing app, no double-register |
| `TestPrometheusGauges` | 4 | Gauges writable; `app_info` is correct type |
| `TestMetricsTestIsolation` | 4 | `TESTING=True`, no `/metrics` route, `/healthz` works |
