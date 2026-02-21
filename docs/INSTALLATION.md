# Redline – Installation & Deployment Guide

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Local Development (Python venv)](#2-local-development-python-venv)
3. [Environment Configuration](#3-environment-configuration)
4. [First Run & Seed Data](#4-first-run--seed-data)
5. [Production – Docker Compose](#5-production--docker-compose)
6. [Production – Bare Metal (Gunicorn + Nginx)](#6-production--bare-metal-gunicorn--nginx)
7. [Database Migrations](#7-database-migrations)
8. [Backup & Restore](#8-backup--restore)
9. [Updating the Application](#9-updating-the-application)
10. [Health Check & Observability](#10-health-check--observability)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

### Local Development

| Requirement | Minimum version |
|-------------|----------------|
| Python | 3.10 |
| pip | 23.x |
| git | any |

### Production (Docker)

| Requirement | Minimum version |
|-------------|----------------|
| Docker Engine | 24.x |
| Docker Compose | v2.x (`docker compose`) |

### Production (Bare Metal)

| Requirement | Notes |
|-------------|-------|
| Python 3.10+ | System or pyenv |
| Nginx | Reverse proxy + TLS termination |
| Certbot / Let's Encrypt | TLS certificate |
| systemd | Process management |

---

## 2. Local Development (Python venv)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/Redline-.git
cd Redline-

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and edit the environment file
cp .env.example .env
# Edit .env – see Section 3 for required values

# 5. Start the development server
python app.py
```

The app is available at **http://localhost:5000**.

---

## 3. Environment Configuration

Copy `.env.example` to `.env` and fill in all required values:

```env
# ── Flask ────────────────────────────────────────────────────────────────────
# REQUIRED: generate with:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-me-with-a-random-64-char-hex-string

# ── Database ─────────────────────────────────────────────────────────────────
# SQLite (default – suitable for development and small deployments):
# DATABASE_URL=sqlite:///redline.db

# PostgreSQL (recommended for production):
# DATABASE_URL=postgresql://redline:password@db:5432/redline

# ── Public URL ───────────────────────────────────────────────────────────────
# REQUIRED in production: base URL for QR code links
# Must be the publicly reachable address; must use https:// in production.
APP_BASE_URL=https://redline.your-company.com

# ── Email Recipients (seed) ───────────────────────────────────────────────────
# This address is added as the first email recipient on first startup.
WORKSHOP_EMAIL=werkstatt@your-company.com

# ── SMTP (only needed for Event Summary Reports) ───────────────────────────
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=noreply@your-company.com

# ── FileMaker (optional) ──────────────────────────────────────────────────
# Leave FILEMAKER_PASSWORD empty to run in POC mode (no FileMaker required).
FILEMAKER_HOST=https://filemaker.your-company.com
FILEMAKER_DATABASE=RedlineDB
FILEMAKER_USERNAME=admin
FILEMAKER_PASSWORD=

# ── Rate Limiting ──────────────────────────────────────────────────────────
# For multi-worker deployments, use Redis:
# RATELIMIT_STORAGE_URL=redis://redis:6379/0

# ── Observability ────────────────────────────────────────────────────────
# Grafana admin password (change before deploying!)
GRAFANA_ADMIN_PASSWORD=change-me-grafana-password

# Optional: override default service ports
APP_PORT=8000
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
```

### Required Values Checklist

| Variable | Required for | Notes |
|----------|-------------|-------|
| `SECRET_KEY` | All environments | **Must** be changed from default |
| `APP_BASE_URL` | Production | Must be public HTTPS URL |
| `WORKSHOP_EMAIL` | First run | Seed email recipient |
| `GRAFANA_ADMIN_PASSWORD` | Docker Compose | Change from default before deploying |
| `MAIL_*` | Event summary reports | Optional for basic usage |
| `FILEMAKER_*` | FileMaker sync | Optional; leave password empty for POC mode |

---

## 4. First Run & Seed Data

On the **first startup** the application automatically:

1. Creates all database tables (`db.create_all()`)
2. Creates default users:

   | Username | Password | Role |
   |----------|----------|------|
   | `admin` | `admin123` | Administrator |
   | `team_login` | `team2025` | Community user (technicians) |

3. Seeds 9 default defect categories
4. Adds `WORKSHOP_EMAIL` as the first email recipient

> **Security:** Change the default passwords immediately after the first login.
> Admin → Benutzerverwaltung → change_password

---

## 5. Production – Docker Compose

`docker compose up -d` starts **three services** automatically:

| Service | Port (default) | Purpose |
|---------|---------------|---------|
| `redline` | 8000 | Flask app (gunicorn) |
| `prometheus` | 9090 | Metrics collection & storage |
| `grafana` | 3000 | Operations dashboard |

### Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env – at minimum set:
#   SECRET_KEY, APP_BASE_URL, GRAFANA_ADMIN_PASSWORD

# 2. Build and start all services
docker compose up -d

# 3. View logs
docker compose logs -f

# 4. Check status
docker compose ps
```

After startup, open:

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | Redline application |
| `http://localhost:8000/healthz` | Health probe (JSON) |
| `http://localhost:8000/metrics` | Prometheus metrics |
| `http://localhost:9090` | Prometheus UI |
| `http://localhost:3000` | Grafana (admin / your password) |

The Grafana "Redline Operations Dashboard" is the **default home page** – no manual setup required.

### Named Volumes

| Volume | Mount Point | Purpose |
|--------|-------------|---------|
| `redline_data` | `/app/data` | SQLite database |
| `redline_qrcodes` | `/app/static/qrcodes` | Generated QR code PNGs |
| `prometheus_data` | `/prometheus` | Prometheus TSDB (30-day retention) |
| `grafana_data` | `/var/lib/grafana` | Grafana state (annotations, users) |

### Adding Nginx as Reverse Proxy

Create `nginx.conf`:

```nginx
server {
    listen 80;
    server_name redline.your-company.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name redline.your-company.com;

    ssl_certificate     /etc/letsencrypt/live/redline.your-company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/redline.your-company.com/privkey.pem;

    location / {
        proxy_pass         http://localhost:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

### Rate Limiting with Multiple Workers

If running more than one gunicorn worker, configure a Redis backend so all workers share rate-limit counters:

```env
RATELIMIT_STORAGE_URL=redis://redis:6379/0
```

Add Redis to `docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
```

---

## 6. Production – Bare Metal (Gunicorn + Nginx)

```bash
# 1. Create a system user
sudo useradd -r -s /bin/false redline

# 2. Clone repository
sudo git clone https://github.com/your-org/Redline-.git /opt/redline
sudo chown -R redline:redline /opt/redline

# 3. Create virtualenv and install
sudo -u redline python3 -m venv /opt/redline/venv
sudo -u redline /opt/redline/venv/bin/pip install -r /opt/redline/requirements.txt

# 4. Configure environment
sudo cp /opt/redline/.env.example /opt/redline/.env
sudo nano /opt/redline/.env   # fill in production values

# 5. Create data directories
sudo mkdir -p /opt/redline/data /opt/redline/static/qrcodes
sudo chown -R redline:redline /opt/redline/data /opt/redline/static/qrcodes
```

### systemd Service

Create `/etc/systemd/system/redline.service`:

```ini
[Unit]
Description=Redline Defect Reporting System
After=network.target

[Service]
Type=simple
User=redline
Group=redline
WorkingDirectory=/opt/redline
EnvironmentFile=/opt/redline/.env
ExecStart=/opt/redline/venv/bin/gunicorn \
    --bind 127.0.0.1:8000 \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile /var/log/redline/access.log \
    --error-logfile  /var/log/redline/error.log \
    app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /var/log/redline
sudo chown redline:redline /var/log/redline

sudo systemctl daemon-reload
sudo systemctl enable redline
sudo systemctl start redline
sudo systemctl status redline
```

---

## 7. Database Migrations

The app uses **Flask-Migrate** (Alembic) for schema migrations.

### Initialise Migration Repository (once)

```bash
flask --app app db init
```

### Create a New Migration

After changing `models.py`:

```bash
flask --app app db migrate -m "describe your change"
```

Review the generated migration in `migrations/versions/`.

### Apply Migrations

```bash
flask --app app db upgrade
```

### Rollback

```bash
flask --app app db downgrade
```

> **Note:** The development shortcut `db.create_all()` in `create_app()` creates tables that don't yet exist but does **not** apply schema changes to existing tables. For schema changes on an existing database always use `flask db migrate` + `flask db upgrade`.

---

## 8. Backup & Restore

### SQLite (default)

```bash
# Backup
cp /opt/redline/data/redline.db /backup/redline-$(date +%Y%m%d).db
# or Docker volume
docker run --rm -v redline_data:/data -v $(pwd):/backup alpine \
    tar czf /backup/redline-$(date +%Y%m%d).tar.gz /data

# Restore
docker run --rm -v redline_data:/data -v $(pwd):/backup alpine \
    tar xzf /backup/redline-20250601.tar.gz -C /
```

### PostgreSQL

```bash
# Backup
pg_dump -U redline redline > /backup/redline-$(date +%Y%m%d).sql

# Restore
psql -U redline redline < /backup/redline-20250601.sql
```

### QR Code PNGs

QR code images are regenerated on demand (they are not stored permanently). The `static/qrcodes/` directory can be emptied safely; images are re-created when next requested.

---

## 9. Updating the Application

### Docker Compose

```bash
git pull origin main
docker compose build
docker compose up -d
# Run any pending migrations
docker compose exec redline flask --app app db upgrade
```

### Bare Metal

```bash
cd /opt/redline
sudo -u redline git pull origin main
sudo -u redline venv/bin/pip install -r requirements.txt
sudo -u redline venv/bin/flask --app app db upgrade
sudo systemctl restart redline
```

---

## 10. Health Check & Observability

### /healthz Probe

The `/healthz` endpoint is the single source of truth for application and database health.
It is called by Docker's `HEALTHCHECK`, load balancers, and Prometheus alert rules.

```bash
# Quick check
curl http://localhost:8000/healthz
# → {"db": "ok", "status": "ok"}   HTTP 200

# Docker health status
docker compose ps
docker inspect redline_app | grep -A5 Health
```

| Response | Status | Meaning |
|----------|--------|---------|
| `{"status":"ok","db":"ok"}` | 200 | App and DB healthy |
| `{"status":"degraded","db":"error"}` | 503 | DB unreachable |

### Prometheus Metrics

The `/metrics` endpoint exposes all Prometheus metrics in text format:

```bash
# View raw metrics
curl http://localhost:8000/metrics | grep redline_

# Example output:
# redline_devices_total 4.0
# redline_defects_total{state="open"} 2.0
# redline_defects_total{state="resolved"} 7.0
# redline_db_up 1.0
# flask_http_request_total{method="GET",path="/report/<device_id>",status="200"} 42.0
```

### Grafana Dashboard

The operations dashboard is pre-loaded at **http://localhost:3000** (default login: `admin` / your `GRAFANA_ADMIN_PASSWORD`).

#### Dashboard Rows

| Row | Panels |
|-----|--------|
| System Health | App Status, DB Status, Uptime, 5xx Error Rate, Req/s |
| HTTP Traffic | Req/s by class, Latency p50/p95/p99, Status donut, Top endpoints |
| Business Metrics | Devices, Open Defects, Active Events, Recipients, Users, Defect charts |
| System Resources | Memory (RSS + virtual), CPU % |

#### Changing the Admin Password

```bash
# Via .env before first start
GRAFANA_ADMIN_PASSWORD=your-secure-password

# Via CLI after startup
docker compose exec grafana grafana-cli admin reset-admin-password new-password
```

#### Resetting Grafana (wipe dashboard customisations)

```bash
docker compose down
docker volume rm redline_grafana_data
docker compose up -d
# Dashboard is re-provisioned automatically from grafana/dashboards/redline.json
```

### Prometheus Retention & Storage

Default: **30 days** of time-series data in the `prometheus_data` Docker volume.

To change retention, edit `docker-compose.yml`:

```yaml
command:
  - "--storage.tsdb.retention.time=90d"   # change as needed
```

### Useful Prometheus Queries

```promql
# Is the app up?
up{job="redline"}

# Current open defects
redline_defects_total{state="open"}

# Average request latency over last 5 min (ms)
histogram_quantile(0.95, sum(rate(flask_http_request_duration_seconds_bucket[5m])) by (le)) * 1000

# HTTP error rate (%)
sum(rate(flask_http_request_total{status=~"5.."}[5m])) / sum(rate(flask_http_request_total[5m])) * 100
```

---

## 11. Troubleshooting

### QR codes point to localhost

`APP_BASE_URL` is not set or still points to `localhost`. Set it to the public server URL in `.env` and restart.

### 500 errors on startup

Check the log output for `[PRODUCTION CONFIGURATION ERRORS]`. Common causes:
- `SECRET_KEY` is still the default placeholder
- `APP_BASE_URL` is `http://` instead of `https://` in production

### Rate limit errors during testing

Ensure `RATELIMIT_ENABLED=False` is set in `TestConfig` (already done). Do not run the test suite against a production environment.

### Email not sending

- Check `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD` in `.env`
- For Gmail: use an **App Password** (not your account password)
- Note: SMTP is only needed for **Event Summary Reports**. Defect notifications use `mailto:` links (no SMTP required).

### FileMaker sync failing

If `FILEMAKER_PASSWORD` is empty the client runs in **POC mode** (logs what would be sent, no network calls). Check the log for `[POC]` prefixed lines to verify.

### Database locked (SQLite)

SQLite only supports one writer at a time. For concurrent write load, migrate to PostgreSQL:

```env
DATABASE_URL=postgresql://redline:password@localhost/redline
```

### Grafana shows "No data" in panels

1. Verify Prometheus is scraping successfully: open `http://localhost:9090/targets` and check that `redline` target is **UP**.
2. If the target is **DOWN**, check that the `redline` container is healthy: `docker compose ps`.
3. Wait one scrape interval (15 s) for the first data point to appear after startup.

### Grafana dashboard not loading / missing

The dashboard is provisioned from `grafana/dashboards/redline.json` on container start. If it is missing:

```bash
docker compose restart grafana
```

If the `grafana_data` volume is corrupted, wipe and recreate:

```bash
docker compose down && docker volume rm redline_grafana_data && docker compose up -d
```

### /metrics returns 404

`/metrics` is only registered when `TESTING=False` (i.e. not in the test suite). In production this should never happen. Check that `FLASK_ENV=production` is set in `docker-compose.yml` or your `.env`.

### Prometheus cannot reach /metrics

By default Prometheus uses the Docker service name `redline` to reach the Flask app (see `prometheus/prometheus.yml`). Ensure the containers are on the same Docker network (default with `docker compose`). Do not use `localhost` in the Prometheus scrape target.
