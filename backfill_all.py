"""Backfill lap parquet for every season from START_YEAR to END_YEAR.

Run from project root:
    python backfill_all.py

Already-written parquet files are skipped automatically (no --force).
When FastF1's 500 calls/hour rate limit is hit, the script sleeps until
the top of the next hour then resumes automatically — no intervention needed.
Progress is logged to backfill.log as well as stdout.
"""

from __future__ import annotations

import logging
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Hard cap: any single network call that hangs longer than this gets killed.
socket.setdefaulttimeout(120)

# ── configure logging ────────────────────────────────────────────────────────
log_path = Path("backfill.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── FastF1 setup ──────────────────────────────────────────────────────────────
import fastf1
from fastf1.exceptions import RateLimitExceededError

fastf1.Cache.enable_cache(str(Path("data/cache/fastf1")))

from src.ingest_laps import ingest_event  # noqa: E402

START_YEAR = 2018
END_YEAR = 2026  # inclusive

RATE_LIMIT_PAUSE = 65  # extra seconds beyond the top of the next hour


def seconds_until_next_hour() -> int:
    now = datetime.now(timezone.utc)
    secs_past = now.minute * 60 + now.second
    return max(0, 3600 - secs_past)


def rate_limited_ingest(year: int, rnd: int) -> None:
    """Call ingest_event; on RateLimitExceededError sleep until next hour and retry."""
    while True:
        try:
            ingest_event(year, rnd, force=False)
            return
        except RateLimitExceededError:
            wait = seconds_until_next_hour() + RATE_LIMIT_PAUSE
            resume_at = datetime.now().strftime("%H:%M:%S")
            log.warning(
                "  Rate limit hit — sleeping %ds (resuming ~%s)",
                wait,
                datetime.fromtimestamp(time.time() + wait).strftime("%H:%M:%S"),
            )
            time.sleep(wait)
            log.info("  Resuming after rate-limit pause")


def backfill_season(year: int) -> None:
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
    except RateLimitExceededError:
        wait = seconds_until_next_hour() + RATE_LIMIT_PAUSE
        log.warning("%d: rate limit on schedule fetch — sleeping %ds", year, wait)
        time.sleep(wait)
        schedule = fastf1.get_event_schedule(year, include_testing=False)
    except Exception as e:
        log.error("%d: failed to get schedule — %s", year, e)
        return

    log.info("%d: %d rounds", year, len(schedule))
    for _, row in schedule.iterrows():
        rnd = int(row["RoundNumber"])
        name = row.get("EventName", f"Round {rnd}")
        log.info("  %d R%d — %s", year, rnd, name)
        try:
            rate_limited_ingest(year, rnd)
        except Exception as e:
            log.error("  %d R%d: unexpected error — %s", year, rnd, e)


if __name__ == "__main__":
    log.info("=== backfill start: %d–%d ===", START_YEAR, END_YEAR)
    for year in range(START_YEAR, END_YEAR + 1):
        backfill_season(year)
    log.info("=== backfill complete ===")
