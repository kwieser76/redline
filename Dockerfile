# ---------------------------------------------------------------------------
# Redline – Production Docker image
#
# Multi-stage build:
#   builder  – installs Python dependencies into a venv
#   runtime  – lean image with only the venv and application code
#
# Build:  docker build -t redline:latest .
# Run:    docker run -p 8000:8000 --env-file .env redline:latest
# ---------------------------------------------------------------------------

# ---- Stage 1: dependency builder ----
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed by some wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated virtualenv so only it gets copied to the runtime stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only dependency files first to leverage Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt


# ---- Stage 2: runtime image ----
FROM python:3.11-slim AS runtime

# Security: run as a non-root user with explicit UID/GID 1001.
# The fixed UID makes Docker named-volume ownership predictable:
# the host chown command can always use 1001:1001.
RUN groupadd -r -g 1001 redline \
 && useradd -r -u 1001 -g 1001 -d /app -s /sbin/nologin redline

WORKDIR /app

# Copy the pre-built virtualenv from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY --chown=redline:redline . .

# Create data directories and set ownership BEFORE the VOLUME declaration.
# Docker initialises a named volume from the container directory the first time
# it is mounted.  Without this the directories are root-owned and the app user
# (redline) cannot write the SQLite database → restart-loop on first deploy.
RUN mkdir -p /app/data /app/static/qrcodes \
 && chown -R redline:redline /app/data /app/static/qrcodes

# Persistent storage for SQLite DB and generated QR images
VOLUME ["/app/data", "/app/static/qrcodes"]

# Redirect SQLite to the volume mount point via an env var override.
# (Ignored when DATABASE_URL points to PostgreSQL.)
ENV DATABASE_URL="sqlite:////app/data/redline.db"

# Gunicorn settings
ENV GUNICORN_WORKERS=2
ENV GUNICORN_THREADS=4
ENV GUNICORN_TIMEOUT=120
ENV PORT=8000

# Run as non-root
USER redline

EXPOSE 8000

# Health-check endpoint – just hits the login redirect
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/')" || exit 1

CMD gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS}" \
    --threads "${GUNICORN_THREADS}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    "app:app"
