import time
from unittest import mock

import pytest

import netbuoy


class TestUptimePercent:
    def test_no_data_returns_none(self, db):
        pct, total = netbuoy.uptime_percent(db, 60)
        assert pct is None
        assert total == 0

    def test_100_percent(self, db):
        now = time.time()
        for i in range(10):
            db.execute("INSERT INTO ping_log VALUES (?, 1, 10.0)", (now - i,))
        db.commit()
        pct, total = netbuoy.uptime_percent(db, 60)
        assert pct == 100.0
        assert total == 10

    def test_0_percent(self, db):
        now = time.time()
        for i in range(5):
            db.execute("INSERT INTO ping_log VALUES (?, 0, NULL)", (now - i,))
        db.commit()
        pct, total = netbuoy.uptime_percent(db, 60)
        assert pct == 0.0
        assert total == 5

    def test_50_percent(self, db):
        now = time.time()
        for i in range(10):
            db.execute("INSERT INTO ping_log VALUES (?, ?, NULL)", (now - i, i % 2))
        db.commit()
        pct, total = netbuoy.uptime_percent(db, 60)
        assert pct == 50.0
        assert total == 10

    def test_excludes_old_data(self, db):
        now = time.time()
        # Recent: all ok
        for i in range(5):
            db.execute("INSERT INTO ping_log VALUES (?, 1, 10.0)", (now - i,))
        # Old: all failed (outside 60s window)
        for i in range(5):
            db.execute("INSERT INTO ping_log VALUES (?, 0, NULL)", (now - 100 - i,))
        db.commit()
        pct, total = netbuoy.uptime_percent(db, 60)
        assert pct == 100.0
        assert total == 5

    def test_window_boundaries(self, db):
        """Data exactly at cutoff boundary should be included."""
        now = time.time()
        with mock.patch("time.time", return_value=now):
            db.execute("INSERT INTO ping_log VALUES (?, 1, 5.0)", (now - 60,))
            db.execute("INSERT INTO ping_log VALUES (?, 0, NULL)", (now - 61,))
            db.commit()
            pct, total = netbuoy.uptime_percent(db, 60)
            assert total == 1
            assert pct == 100.0

    def test_different_windows(self, db):
        """1-minute window and 1-hour window show different results."""
        now = time.time()
        # Last 30 seconds: all ok
        for i in range(15):
            db.execute("INSERT INTO ping_log VALUES (?, 1, 10.0)", (now - i * 2,))
        # 5 minutes ago: all failed
        for i in range(15):
            db.execute("INSERT INTO ping_log VALUES (?, 0, NULL)", (now - 300 - i * 2,))
        db.commit()

        pct_1m, _ = netbuoy.uptime_percent(db, 60)
        pct_1h, _ = netbuoy.uptime_percent(db, 3600)
        assert pct_1m == 100.0
        assert pct_1h == 50.0


class TestUptimeSince:
    def test_no_data_returns_none(self, db):
        pct, total = netbuoy.uptime_since(db, time.time() - 100)
        assert pct is None
        assert total == 0

    def test_session_uptime(self, db):
        session_start = time.time() - 50
        for i in range(10):
            ok = 1 if i < 8 else 0
            db.execute("INSERT INTO ping_log VALUES (?, ?, NULL)", (session_start + i * 5, ok))
        db.commit()
        pct, total = netbuoy.uptime_since(db, session_start)
        assert pct == 80.0
        assert total == 10

    def test_diverges_from_all_time(self, db):
        """Session uptime can differ from all-time uptime."""
        now = time.time()
        session_start = now - 30

        # Old data: all failed
        for i in range(10):
            db.execute("INSERT INTO ping_log VALUES (?, 0, NULL)", (now - 1000 - i,))
        # Session data: all ok
        for i in range(10):
            db.execute("INSERT INTO ping_log VALUES (?, 1, 10.0)", (session_start + i * 2,))
        db.commit()

        session_pct, _ = netbuoy.uptime_since(db, session_start)
        all_pct, _ = netbuoy.uptime_all_time(db)
        assert session_pct == 100.0
        assert all_pct == 50.0


class TestUptimeAllTime:
    def test_no_data_returns_none(self, db):
        pct, total = netbuoy.uptime_all_time(db)
        assert pct is None
        assert total == 0

    def test_all_time_includes_everything(self, db):
        now = time.time()
        # Spread across a large time range
        db.execute("INSERT INTO ping_log VALUES (?, 1, 10.0)", (now - 100000,))
        db.execute("INSERT INTO ping_log VALUES (?, 1, 10.0)", (now - 50000,))
        db.execute("INSERT INTO ping_log VALUES (?, 0, NULL)", (now - 1,))
        db.commit()
        pct, total = netbuoy.uptime_all_time(db)
        assert total == 3
        assert abs(pct - 66.666) < 0.1
