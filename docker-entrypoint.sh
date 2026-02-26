#!/bin/sh
# ---------------------------------------------------------------------------
# Redline – container entrypoint
#
# Runs as root so it can fix volume ownership, then drops to the non-root
# "redline" user (UID/GID 1001) before executing the application.
#
# Why this is needed:
#   Docker only copies directory ownership from the image to a *new* named
#   volume.  If the volume already exists (e.g. created before a UID change
#   or on a plain "docker volume create"), it keeps its original ownership
#   (usually root:root), which prevents the app user from writing the SQLite
#   database → restart-loop.
#
#   Running this fixup on every start costs ~1 ms and is idempotent.
# ---------------------------------------------------------------------------

set -e

# Fix ownership of writable directories (safe to run as root, no-op if
# already correct).
chown -R redline:redline /app/data /app/static/qrcodes

# Drop privileges and exec the CMD (gunicorn …) as the redline user.
exec gosu redline "$@"
