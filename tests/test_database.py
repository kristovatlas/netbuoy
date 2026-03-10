import stat
import time
import tempfile
from pathlib import Path
from unittest import mock

import pytest

import netbuoy


class TestInitDb:
    def test_creates_directory_and_tables(self, tmp_path):
        db_dir = tmp_path / "netbuoy_test"
        db_path = db_dir / "history.db"
        with mock.patch.object(netbuoy, "DB_DIR", db_dir), \
             mock.patch.object(netbuoy, "DB_PATH", db_path):
            conn = netbuoy.init_db()
            assert db_dir.exists()
            # Verify tables exist
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "ping_log" in table_names
            assert "speed_log" in table_names
            conn.close()

    def test_wal_journal_mode(self, tmp_path):
        db_dir = tmp_path / "netbuoy_test"
        db_path = db_dir / "history.db"
        with mock.patch.object(netbuoy, "DB_DIR", db_dir), \
             mock.patch.object(netbuoy, "DB_PATH", db_path):
            conn = netbuoy.init_db()
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
            conn.close()

    def test_directory_permissions_owner_only(self, tmp_path):
        db_dir = tmp_path / "netbuoy_test"
        db_path = db_dir / "history.db"
        with mock.patch.object(netbuoy, "DB_DIR", db_dir), \
             mock.patch.object(netbuoy, "DB_PATH", db_path):
            conn = netbuoy.init_db()
            mode = db_dir.stat().st_mode
            # Only owner should have rwx
            assert mode & stat.S_IRWXG == 0, "Group should have no permissions"
            assert mode & stat.S_IRWXO == 0, "Others should have no permissions"
            conn.close()

    def test_idempotent(self, tmp_path):
        db_dir = tmp_path / "netbuoy_test"
        db_path = db_dir / "history.db"
        with mock.patch.object(netbuoy, "DB_DIR", db_dir), \
             mock.patch.object(netbuoy, "DB_PATH", db_path):
            conn1 = netbuoy.init_db()
            conn1.close()
            conn2 = netbuoy.init_db()
            tables = conn2.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert len([t for t in tables if t[0] in ("ping_log", "speed_log")]) == 2
            conn2.close()


class TestRecordPing:
    def test_records_successful_ping(self, db):
        with mock.patch("time.time", return_value=1000.0):
            netbuoy.record_ping(db, True, 12.5)
        row = db.execute("SELECT ts, ok, latency_ms FROM ping_log").fetchone()
        assert row == (1000.0, 1, 12.5)

    def test_records_failed_ping(self, db):
        with mock.patch("time.time", return_value=1001.0):
            netbuoy.record_ping(db, False)
        row = db.execute("SELECT ts, ok, latency_ms FROM ping_log").fetchone()
        assert row == (1001.0, 0, None)

    def test_replaces_on_duplicate_timestamp(self, db):
        with mock.patch("time.time", return_value=1000.0):
            netbuoy.record_ping(db, True, 10.0)
            netbuoy.record_ping(db, False, None)
        rows = db.execute("SELECT COUNT(*) FROM ping_log").fetchone()
        assert rows[0] == 1
        row = db.execute("SELECT ok FROM ping_log").fetchone()
        assert row[0] == 0


class TestRecordSpeed:
    def test_records_speed(self, db):
        with mock.patch("time.time", return_value=2000.0):
            netbuoy.record_speed(db, 100.5, 25.3)
        row = db.execute("SELECT ts, download_mbps, upload_mbps FROM speed_log").fetchone()
        assert row == (2000.0, 100.5, 25.3)

    def test_records_download_only(self, db):
        with mock.patch("time.time", return_value=2000.0):
            netbuoy.record_speed(db, 50.0, None)
        row = db.execute("SELECT download_mbps, upload_mbps FROM speed_log").fetchone()
        assert row == (50.0, None)


class TestLatestSpeed:
    def test_returns_none_when_empty(self, db):
        assert netbuoy.latest_speed(db) is None

    def test_returns_most_recent(self, db):
        db.execute("INSERT INTO speed_log VALUES (1000, 50.0, 10.0)")
        db.execute("INSERT INTO speed_log VALUES (2000, 100.0, 25.0)")
        db.commit()
        row = netbuoy.latest_speed(db)
        assert row == (100.0, 25.0, 2000.0)
