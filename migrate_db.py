"""
One-time migration script for existing Redline databases.

Run this once if you are upgrading from a version before v0.1b:
    python migrate_db.py

Safe to run multiple times – already-existing columns are skipped.
"""

import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "redline.db")


def col_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def table_exists(conn, table):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchall()
    return len(rows) > 0


def run():
    if not os.path.exists(DB_PATH):
        print(f"[SKIP] Database '{DB_PATH}' not found – nothing to migrate.")
        return

    conn = sqlite3.connect(DB_PATH)
    changes = 0

    # ── users.is_api_user ─────────────────────────────────────────────────────
    if table_exists(conn, "users") and not col_exists(conn, "users", "is_api_user"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_api_user BOOLEAN NOT NULL DEFAULT 0"
        )
        conn.commit()
        print("[OK] Added column: users.is_api_user")
        changes += 1
    else:
        print("[SKIP] users.is_api_user already exists")

    # ── users.is_werkstatt ────────────────────────────────────────────────────
    if table_exists(conn, "users") and not col_exists(conn, "users", "is_werkstatt"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_werkstatt BOOLEAN NOT NULL DEFAULT 0"
        )
        conn.commit()
        print("[OK] Added column: users.is_werkstatt")
        changes += 1
    else:
        print("[SKIP] users.is_werkstatt already exists")

    # ── users.is_disponent ────────────────────────────────────────────────────
    if table_exists(conn, "users") and not col_exists(conn, "users", "is_disponent"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_disponent BOOLEAN NOT NULL DEFAULT 0"
        )
        conn.commit()
        print("[OK] Added column: users.is_disponent")
        changes += 1
    else:
        print("[SKIP] users.is_disponent already exists")

    # ── device_categories table ───────────────────────────────────────────────
    if not table_exists(conn, "device_categories"):
        conn.execute(
            """
            CREATE TABLE device_categories (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.commit()
        print("[OK] Created table: device_categories")
        changes += 1
    else:
        print("[SKIP] device_categories already exists")

    # ── devices.category_id ───────────────────────────────────────────────────
    if table_exists(conn, "devices") and not col_exists(conn, "devices", "category_id"):
        conn.execute(
            "ALTER TABLE devices ADD COLUMN category_id INTEGER REFERENCES device_categories(id)"
        )
        conn.commit()
        print("[OK] Added column: devices.category_id")
        changes += 1
    else:
        print("[SKIP] devices.category_id already exists")

    conn.close()

    print()
    if changes:
        print(f"Migration complete – {changes} change(s) applied.")
        print("You can now start the app normally:  python app.py")
    else:
        print("Nothing to do – database is already up to date.")


if __name__ == "__main__":
    run()
