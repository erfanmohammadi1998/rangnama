"""ثبت رویداد و آمار استفاده — SQLite بدون وابستگی خارجی."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "analytics.sqlite"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                color_code TEXT,
                color_name TEXT,
                meta TEXT
            )"""
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                name TEXT,
                phone TEXT,
                city TEXT,
                note TEXT
            )"""
        )
        _conn.commit()
    return _conn


def log_event(kind: str, color_code: str | None = None, color_name: str | None = None, **meta) -> None:
    try:
        with _lock:
            _db().execute(
                "INSERT INTO events (ts, kind, color_code, color_name, meta) VALUES (?,?,?,?,?)",
                (time.time(), kind, color_code, color_name, json.dumps(meta, ensure_ascii=False)),
            )
            _db().commit()
    except Exception as exc:  # noqa: BLE001 - آمار نباید مسیر اصلی را بشکند
        print(f"[analytics] {exc!r}")


def add_lead(name: str, phone: str, city: str = "", note: str = "") -> None:
    with _lock:
        _db().execute(
            "INSERT INTO leads (ts, name, phone, city, note) VALUES (?,?,?,?,?)",
            (time.time(), name, phone, city, note),
        )
        _db().commit()


def stats() -> dict:
    c = _db()
    now = time.time()
    day = 86400

    total = c.execute("SELECT COUNT(*) FROM events WHERE kind='visualize'").fetchone()[0]
    last_7d = c.execute(
        "SELECT COUNT(*) FROM events WHERE kind='visualize' AND ts > ?", (now - 7 * day,)
    ).fetchone()[0]
    uploads = c.execute("SELECT COUNT(*) FROM events WHERE kind='upload'").fetchone()[0]
    leads = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    top_colors = [
        {"code": row[0], "name": row[1], "count": row[2]}
        for row in c.execute(
            """SELECT color_code, color_name, COUNT(*) c FROM events
               WHERE kind='visualize' AND color_code IS NOT NULL
               GROUP BY color_code ORDER BY c DESC LIMIT 8"""
        ).fetchall()
    ]

    # نمودار روزانه‌ی ۱۴ روز اخیر
    timeline = []
    for i in range(13, -1, -1):
        start = now - (i + 1) * day
        end = now - i * day
        n = c.execute(
            "SELECT COUNT(*) FROM events WHERE kind='visualize' AND ts >= ? AND ts < ?",
            (start, end),
        ).fetchone()[0]
        timeline.append(n)

    recent_leads = [
        {"name": r[0], "phone": r[1], "city": r[2], "note": r[3], "ts": r[4]}
        for r in c.execute(
            "SELECT name, phone, city, note, ts FROM leads ORDER BY ts DESC LIMIT 20"
        ).fetchall()
    ]

    return {
        "total_visualizations": total,
        "visualizations_7d": last_7d,
        "photos_uploaded": uploads,
        "leads": leads,
        "top_colors": top_colors,
        "timeline_14d": timeline,
        "recent_leads": recent_leads,
    }
