"""Validate raw event rows and load the clean ones into SQLite.

Rows that fail validation are written to a rejects CSV with a reason, never
silently dropped.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

REQUIRED = [
    "timestamp", "source_id", "destination_service", "event_type",
    "bytes_sent", "failed_auth_count", "expected_activity",
]
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


class ValidationError(ValueError):
    pass


def _int(value: str, name: str, minimum: int = 0) -> int | None:
    """Parse an optional non-negative integer. Empty string -> None (NULL)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        n = int(str(value).strip())
    except ValueError:
        raise ValidationError(f"{name} is not an integer: {value!r}")
    if n < minimum:
        raise ValidationError(f"{name} must be >= {minimum}: {n}")
    return n


def validate_row(row: dict) -> tuple:
    """Return a clean tuple in schema order, or raise ValidationError."""
    missing = [c for c in REQUIRED if c not in row]
    if missing:
        raise ValidationError(f"missing columns: {missing}")
    for col in ("timestamp", "source_id", "destination_service", "event_type"):
        if not (row[col] or "").strip():
            raise ValidationError(f"{col} is empty")
    try:
        ts = datetime.fromisoformat(row["timestamp"].strip())
    except ValueError:
        raise ValidationError(f"bad timestamp: {row['timestamp']!r}")
    label = _int(row["expected_activity"], "expected_activity")
    if label not in (0, 1):
        raise ValidationError(f"expected_activity must be 0 or 1: {row['expected_activity']!r}")
    return (
        ts.isoformat(timespec="seconds"),
        row["source_id"].strip(),
        row["destination_service"].strip(),
        row["event_type"].strip(),
        _int(row["bytes_sent"], "bytes_sent"),
        _int(row["failed_auth_count"], "failed_auth_count"),
        label,
    )


def load_csv(csv_path: Path, conn: sqlite3.Connection) -> tuple[int, list[dict]]:
    """Load valid rows; return (loaded_count, rejects)."""
    conn.executescript(SCHEMA_PATH.read_text())
    good, rejects = [], []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):
            try:
                good.append(validate_row(row))
            except ValidationError as e:
                rejects.append({"line": line_no, "reason": str(e), **row})
    conn.execute("DELETE FROM events")  # makes re-runs idempotent
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)", good)
    conn.commit()
    return len(good), rejects


def write_rejects(rejects: list[dict], path: Path) -> None:
    if not rejects:
        path.unlink(missing_ok=True)
        return
    fields = list(rejects[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rejects)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default="data/sample_events.csv")
    ap.add_argument("--db", default="data/signalwatch.db")
    ap.add_argument("--rejects", default="data/rejected_rows.csv")
    a = ap.parse_args()
    conn = sqlite3.connect(a.db)
    try:
        n, rejects = load_csv(Path(a.csv), conn)
    finally:
        conn.close()
    write_rejects(rejects, Path(a.rejects))
    print(f"loaded {n} rows, rejected {len(rejects)} -> {a.db}")


if __name__ == "__main__":
    main()
