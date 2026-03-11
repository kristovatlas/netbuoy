import sqlite3
import pytest
import sys
import os

# Ensure netbuoy module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def db():
    """In-memory SQLite database with netbuoy schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ping_log (
            ts REAL PRIMARY KEY,
            ok INTEGER NOT NULL,
            latency_ms REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS speed_log (
            ts REAL PRIMARY KEY,
            download_mbps REAL,
            upload_mbps REAL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ping_ts ON ping_log(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_speed_ts ON speed_log(ts)")
    conn.commit()
    yield conn
    conn.close()
