# Tableau dashboard guide

**Audience:** a SOC lead or security manager who needs to know *where to look first*, not a model tuner.
**Tool:** Tableau Public (free). Everything here is synthetic data, so publishing is safe.

## Connect
1. Run the pipeline (see the README) so `output/scored_hourly.csv` exists.
2. Tableau Public → Connect → *Text file* → `output/scored_hourly.csv`.
3. Set `hour_start` to **Date & Time**.

## Sheets
| Sheet | Build |
|---|---|
| **Event volume over time** | Columns `hour_start` (continuous, hour); Rows `SUM(event_count)`; Color `source_id`. |
| **Anomaly score timeline** | Columns `hour_start`; Rows `MAX(anomaly_score)`; add a reference line at 3.5; Color by `outcome`. |
| **Outcome counts** | Rows `outcome`; Columns `COUNT(hour_start)`; label values. Shows TP / FP / FN / TN. |
| **Anomaly drivers** | Filter `flagged = 1`; Rows `driver`; Columns `COUNT`; shows whether volume, bytes or failed logins triggered the flag. |
| **Hour-of-day heatmap** | Columns `hour_of_day`; Rows `day_of_week`; Color `AVG(anomaly_score)`. |

Optional second data source: `data/signalwatch.db` is SQLite (needs the SQLite ODBC driver), so the CSV route is simpler.

## Assemble
Drag the sheets onto one dashboard titled **SignalWatch – Threat Triage**. Add a filter action so clicking an outcome bar filters the timeline. Add a text box: *"Synthetic data. Scores prioritise review; they are not proof of malicious activity."*

## Publish
File → Save to Tableau Public. Put the URL in the README and save a screenshot as `dashboard/screenshot.png`.
