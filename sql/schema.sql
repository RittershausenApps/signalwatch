-- Normalized event store
CREATE TABLE IF NOT EXISTS events (
    timestamp           TEXT    NOT NULL,   -- ISO-8601, e.g. 2026-01-05T08:15:00
    source_id           TEXT    NOT NULL,
    destination_service TEXT    NOT NULL,
    event_type          TEXT    NOT NULL,
    bytes_sent          INTEGER,
    failed_auth_count   INTEGER,
    expected_activity   INTEGER NOT NULL CHECK (expected_activity IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_events_source_ts ON events (source_id, timestamp);

-- Hourly aggregates per source: the unit the anomaly model scores.
-- injected_events > 0 means ground truth says something unexpected happened.
DROP VIEW IF EXISTS hourly_activity;
CREATE VIEW hourly_activity AS
SELECT
    strftime('%Y-%m-%dT%H:00:00', timestamp)              AS hour_start,
    source_id,
    COUNT(*)                                               AS event_count,
    COALESCE(SUM(bytes_sent), 0)                           AS total_bytes,
    COALESCE(SUM(failed_auth_count), 0)                    AS failed_auth,
    COUNT(DISTINCT destination_service)                    AS distinct_services,
    SUM(CASE WHEN expected_activity = 0 THEN 1 ELSE 0 END) AS injected_events,
    CAST(strftime('%H', timestamp) AS INTEGER)             AS hour_of_day,
    CAST(strftime('%w', timestamp) AS INTEGER)             AS day_of_week
FROM events
GROUP BY hour_start, source_id;

-- Hourly aggregates per service, handy for the dashboard.
DROP VIEW IF EXISTS hourly_by_service;
CREATE VIEW hourly_by_service AS
SELECT
    strftime('%Y-%m-%dT%H:00:00', timestamp) AS hour_start,
    destination_service,
    event_type,
    COUNT(*)                                 AS event_count,
    COALESCE(SUM(bytes_sent), 0)             AS total_bytes
FROM events
GROUP BY hour_start, destination_service, event_type;
