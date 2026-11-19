import csv
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import generate_events as gen  # noqa: E402
import ingest  # noqa: E402

GOOD = {
    "timestamp": "2026-01-05T08:15:00", "source_id": "host-01",
    "destination_service": "web-app", "event_type": "http_request",
    "bytes_sent": "1200", "failed_auth_count": "0", "expected_activity": "1",
}


def with_(**kw):
    return {**GOOD, **kw}


def test_valid_row_is_cleaned():
    assert ingest.validate_row(GOOD) == (
        "2026-01-05T08:15:00", "host-01", "web-app", "http_request", 1200, 0, 1)


def test_missing_optional_numbers_become_null():
    row = ingest.validate_row(with_(bytes_sent="", failed_auth_count=""))
    assert row[4] is None and row[5] is None


@pytest.mark.parametrize("bad", [
    with_(source_id=""),
    with_(timestamp="yesterday"),
    with_(bytes_sent="-5"),
    with_(bytes_sent="lots"),
    with_(expected_activity="7"),
    with_(expected_activity=""),
])
def test_malformed_rows_rejected(bad):
    with pytest.raises(ingest.ValidationError):
        ingest.validate_row(bad)


def test_missing_column_rejected():
    row = dict(GOOD)
    del row["event_type"]
    with pytest.raises(ingest.ValidationError):
        ingest.validate_row(row)


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ingest.REQUIRED)
        w.writeheader()
        w.writerows(rows)


def test_load_csv_splits_good_and_bad(tmp_path):
    p = tmp_path / "e.csv"
    write_csv(p, [GOOD, with_(source_id=""), with_(timestamp="2026-01-05T09:00:00")])
    conn = sqlite3.connect(":memory:")
    loaded, rejects = ingest.load_csv(p, conn)
    assert loaded == 2
    assert len(rejects) == 1 and "source_id" in rejects[0]["reason"]
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2


def test_reload_is_idempotent(tmp_path):
    p = tmp_path / "e.csv"
    write_csv(p, [GOOD])
    conn = sqlite3.connect(":memory:")
    ingest.load_csv(p, conn)
    ingest.load_csv(p, conn)
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_hourly_view_aggregates(tmp_path):
    p = tmp_path / "e.csv"
    write_csv(p, [GOOD, with_(timestamp="2026-01-05T08:45:00", expected_activity="0")])
    conn = sqlite3.connect(":memory:")
    ingest.load_csv(p, conn)
    hour, src, n, _, _, _, injected, hod, _ = conn.execute("SELECT * FROM hourly_activity").fetchone()
    assert (hour, src, n, injected, hod) == ("2026-01-05T08:00:00", "host-01", 2, 1, 8)


def test_generator_is_deterministic_and_labeled():
    a = gen.generate(days=3, seed=1, n_incidents=3, bad_rate=0.0)
    b = gen.generate(days=3, seed=1, n_incidents=3, bad_rate=0.0)
    assert a == b
    assert any(r["expected_activity"] == 0 for r in a)
    for r in a:  # with bad_rate=0 everything must validate
        ingest.validate_row({k: str(v) for k, v in r.items()})
