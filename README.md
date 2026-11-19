# SignalWatch: security analytics on synthetic network events

A small, reproducible pipeline that turns synthetic network-event logs into anomaly scores and an analyst dashboard.

**Degree connection**
- **Applied Security:** safe attack simulation (brute force, low-and-slow exfiltration, scan bursts), defensive triage, input validation of untrusted logs, responsible-use framing.
- **Analytics:** data validation, SQL aggregation, a robust statistical model in R, evaluation against ground truth, and a Tableau dashboard.

## Architecture

```
generate_events.py ──▶ sample_events.csv ──▶ ingest.py ──▶ SQLite (events + views)
   (Python, seeded)        (raw, some bad rows)  (validate)        │
                                                                   ▼
                              Tableau ◀── output/scored_hourly.csv ◀── anomaly_model.R
                                                                   (robust z-scores, evaluation)
```

## The security problem
Three fictional incident types are injected into otherwise normal hourly traffic from 8 hosts:

| Incident | Signature |
|---|---|
| Brute force | burst of failed logins against `auth-svc` |
| Exfiltration (low and slow) | few events, very large `bytes_sent` |
| Scan burst | sudden spike in event volume across services |

Rows carry a ground-truth label (`expected_activity = 0` means injected). No IP addresses and no real traffic are used.

## The analytical solution
For each source and each bucket (business hours vs. off hours), the model computes a robust z-score `(x − median) / (1.4826 · MAD)` on three hourly metrics: event count, total bytes, failed logins. The hour's anomaly score is the maximum; above **3.5** it is flagged. Median and MAD are used instead of mean and standard deviation because attacks inflate the very statistics they are measured against.

## Run it from a clean clone
Requires Python 3.10+ and R 4.x with `DBI` and `RSQLite`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/generate_events.py        # data/sample_events.csv
python src/ingest.py                 # data/signalwatch.db + rejected_rows.csv
Rscript analysis/anomaly_model.R     # output/*.csv
pytest                               # unit tests
```

Then follow [dashboard/tableau_guide.md](dashboard/tableau_guide.md).

## Results
<!-- Fill in from output/metrics.csv after running -->
RESULTS_PLACEHOLDER

## Limits of the model
- It scores hourly aggregates, so it cannot say *which* event in the hour was bad.
- Thresholds are tuned on data I generated; real traffic has heavier tails and drift.
- A new host has no baseline. Attackers who ramp up slowly can drag the median.
- Misses and over-flags are listed in `output/errors_to_review.csv`.

## Responsible use
All data is synthetic. Scores are for **triage**, deciding what a human reviews first, and are not evidence of malicious activity.

## Layout
`src/` Python · `sql/` schema and views · `analysis/` R model · `dashboard/` Tableau guide · `tests/` pytest
