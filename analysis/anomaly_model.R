# SignalWatch anomaly model
# Robust baseline per source and time-of-week bucket; flags hours whose activity
# sits more than THRESHOLD median-absolute-deviations above the usual level.
# Usage (from repo root): Rscript analysis/anomaly_model.R

suppressPackageStartupMessages({
  library(DBI)
  library(RSQLite)
})

DB_PATH   <- "data/signalwatch.db"
OUT_DIR   <- "output"
THRESHOLD <- 6     # chosen from a sensitivity sweep (see README); 3.5 is the textbook default but over-flags heavy-tailed byte counts
MIN_MAD   <- 1     # floor so a flat baseline doesn't make every blip infinite
METRICS   <- c("event_count", "total_bytes", "failed_auth")

dir.create(OUT_DIR, showWarnings = FALSE)
con <- dbConnect(SQLite(), DB_PATH)
hourly <- dbGetQuery(con, "SELECT * FROM hourly_activity ORDER BY hour_start, source_id")
dbDisconnect(con)

# Baseline buckets: business hours on weekdays vs. everything else, per source.
hourly$business <- ifelse(hourly$hour_of_day >= 8 & hourly$hour_of_day < 18 &
                            hourly$day_of_week %in% 1:5, "business", "off")
hourly$bucket <- paste(hourly$source_id, hourly$business, sep = "|")

robust_z <- function(x) {
  med <- median(x)
  s   <- max(1.4826 * mad(x, constant = 1), MIN_MAD)
  (x - med) / s
}

for (m in METRICS) {
  hourly[[paste0("z_", m)]] <- ave(hourly[[m]], hourly$bucket, FUN = robust_z)
}
z_cols <- paste0("z_", METRICS)
hourly$anomaly_score <- do.call(pmax, hourly[z_cols])
hourly$driver <- METRICS[max.col(as.matrix(hourly[z_cols]), ties.method = "first")]
hourly$flagged <- as.integer(hourly$anomaly_score > THRESHOLD)
hourly$truth   <- as.integer(hourly$injected_events > 0)

# Evaluation against synthetic ground truth
tp <- sum(hourly$flagged == 1 & hourly$truth == 1)
fp <- sum(hourly$flagged == 1 & hourly$truth == 0)
fn <- sum(hourly$flagged == 0 & hourly$truth == 1)
tn <- sum(hourly$flagged == 0 & hourly$truth == 0)
precision <- ifelse(tp + fp > 0, tp / (tp + fp), NA)
recall    <- ifelse(tp + fn > 0, tp / (tp + fn), NA)
f1        <- 2 * precision * recall / (precision + recall)

metrics <- data.frame(
  threshold = THRESHOLD, hours_scored = nrow(hourly),
  true_positives = tp, false_positives = fp, false_negatives = fn, true_negatives = tn,
  precision = round(precision, 3), recall = round(recall, 3), f1 = round(f1, 3)
)
print(metrics, row.names = FALSE)

hourly$outcome <- with(hourly, ifelse(flagged == 1 & truth == 1, "true_positive",
                               ifelse(flagged == 1 & truth == 0, "false_positive",
                               ifelse(flagged == 0 & truth == 1, "false_negative", "true_negative"))))

write.csv(hourly, file.path(OUT_DIR, "scored_hourly.csv"), row.names = FALSE)
write.csv(metrics, file.path(OUT_DIR, "metrics.csv"), row.names = FALSE)
write.csv(hourly[hourly$outcome %in% c("false_positive", "false_negative"),
                 c("hour_start", "source_id", "event_count", "total_bytes",
                   "failed_auth", "anomaly_score", "driver", "injected_events", "outcome")],
          file.path(OUT_DIR, "errors_to_review.csv"), row.names = FALSE)
cat("wrote", file.path(OUT_DIR, c("scored_hourly.csv", "metrics.csv", "errors_to_review.csv")), "\n")
