"""Generate a synthetic, labeled network-event log.

Everything here is fictional: host IDs are made up, no IP addresses are used,
and attacks are just numbers in a CSV. Re-running with the same seed always
produces the same file.

expected_activity = 1 -> normal baseline behaviour
expected_activity = 0 -> injected anomaly (ground truth label)

A small share of deliberately malformed rows is mixed in so the validator in
ingest.py has something real to reject.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

FIELDS = [
    "timestamp", "source_id", "destination_service", "event_type",
    "bytes_sent", "failed_auth_count", "expected_activity",
]
SOURCES = [f"host-{i:02d}" for i in range(1, 9)]
SERVICES = ["auth-svc", "web-app", "db-main", "file-share"]
# Normal events: (event_type, service, mean bytes, share of traffic)
NORMAL_MIX = [
    ("http_request", "web-app", 4_000, 0.45),
    ("db_query", "db-main", 2_500, 0.20),
    ("file_read", "file-share", 20_000, 0.15),
    ("login_success", "auth-svc", 300, 0.15),
    ("login_failure", "auth-svc", 300, 0.05),
]


def poisson(rng: random.Random, lam: float) -> int:
    """Knuth's algorithm; fine for the small rates used here."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def hourly_rate(hour: int, weekday: int, host_scale: float) -> float:
    """Business-hours bump so the baseline has realistic seasonality."""
    base = 14.0 if 8 <= hour < 18 and weekday < 5 else 4.0
    return base * host_scale


def normal_event(rng: random.Random, ts: datetime, source: str) -> dict:
    r, acc = rng.random(), 0.0
    for etype, svc, mean_bytes, share in NORMAL_MIX:
        acc += share
        if r <= acc:
            break
    failed = 1 if etype == "login_failure" else 0
    return {
        "timestamp": ts.isoformat(timespec="seconds"),
        "source_id": source,
        "destination_service": svc,
        "event_type": etype,
        "bytes_sent": max(0, int(rng.gauss(mean_bytes, mean_bytes * 0.3))),
        "failed_auth_count": failed,
        "expected_activity": 1,
    }


def attack_events(rng: random.Random, kind: str, start: datetime, source: str) -> list[dict]:
    """Return one injected incident (all rows labeled expected_activity=0)."""
    rows = []
    if kind == "brute_force":  # burst of failed logins within ~2 hours
        for _ in range(rng.randint(60, 90)):
            ts = start + timedelta(seconds=rng.randint(0, 7199))
            rows.append(("login_failure", "auth-svc", rng.randint(200, 500), rng.randint(3, 8), ts))
    elif kind == "exfiltration":  # few events, huge payloads (low and slow)
        for _ in range(rng.randint(6, 10)):
            ts = start + timedelta(seconds=rng.randint(0, 3599))
            rows.append(("data_transfer", "file-share", rng.randint(2_000_000, 6_000_000), 0, ts))
    elif kind == "scan_burst":  # volume spike across services
        for _ in range(rng.randint(120, 180)):
            ts = start + timedelta(seconds=rng.randint(0, 3599))
            svc = rng.choice(SERVICES)
            rows.append(("http_request", svc, rng.randint(100, 400), 0, ts))
    return [
        {"timestamp": ts.isoformat(timespec="seconds"), "source_id": source,
         "destination_service": svc, "event_type": et, "bytes_sent": b,
         "failed_auth_count": f, "expected_activity": 0}
        for et, svc, b, f, ts in rows
    ]


def corrupt(rng: random.Random, row: dict) -> dict:
    """Make a row invalid in one realistic way."""
    bad = dict(row)
    choice = rng.choice(["no_source", "bad_ts", "neg_bytes", "bad_label", "text_bytes"])
    if choice == "no_source":
        bad["source_id"] = ""
    elif choice == "bad_ts":
        bad["timestamp"] = "not-a-date"
    elif choice == "neg_bytes":
        bad["bytes_sent"] = -5
    elif choice == "bad_label":
        bad["expected_activity"] = 7
    else:
        bad["bytes_sent"] = "lots"
    return bad


def generate(days: int, seed: int, n_incidents: int, bad_rate: float) -> list[dict]:
    rng = random.Random(seed)
    start = datetime(2026, 1, 5)  # a Monday
    scales = {s: rng.uniform(0.7, 1.3) for s in SOURCES}
    rows: list[dict] = []
    for h in range(days * 24):
        hour_start = start + timedelta(hours=h)
        for s in SOURCES:
            lam = hourly_rate(hour_start.hour, hour_start.weekday(), scales[s])
            for _ in range(poisson(rng, lam)):
                ts = hour_start + timedelta(seconds=rng.randint(0, 3599))
                rows.append(normal_event(rng, ts, s))
    # Incidents start well after the first day so every host has a baseline.
    kinds = ["brute_force", "exfiltration", "scan_burst"]
    for i in range(n_incidents):
        at = start + timedelta(days=rng.randint(1, days - 1), hours=rng.randint(0, 21))
        rows += attack_events(rng, kinds[i % 3], at, rng.choice(SOURCES))
    rows.sort(key=lambda r: r["timestamp"])
    return [corrupt(rng, r) if rng.random() < bad_rate else r for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="data/sample_events.csv")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--incidents", type=int, default=12)
    ap.add_argument("--bad-rate", type=float, default=0.005)
    a = ap.parse_args()
    rows = generate(a.days, a.seed, a.incidents, a.bad_rate)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
