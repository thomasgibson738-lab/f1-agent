"""Pull FastF1 lap data and write trimmed Parquet for the Streamlit app.

Output layout:
    data/laps/{year}/{round}/{session_code}.parquet

Session codes: FP1, FP2, FP3, Q, SQ, SS, S, R
(SS = Sprint Shootout 2023-2024; SQ = Sprint Qualifying 2025+)

Usage (run from project root):
    python src/ingest_laps.py 2024 1            # one race
    python src/ingest_laps.py 2024              # whole season
    python src/ingest_laps.py 2024 1 --force    # overwrite existing parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fastf1
import pandas as pd

CACHE_DIR = Path("data/cache/fastf1")
LAPS_DIR = Path("data/laps")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LAPS_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

# Map FastF1's canonical Session1..Session5 names -> short file codes.
SESSION_NAME_TO_CODE = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SS",
    "Sprint": "S",
    "Race": "R",
}

# Columns we keep from FastF1's laps DataFrame. Anything not present in a
# given session is silently skipped.
KEEP_COLS = [
    "LapNumber",
    "Driver",
    "DriverNumber",
    "Team",
    "LapTime",
    "Compound",
    "TyreLife",
    "FreshTyre",
    "Stint",
    "PitInTime",
    "PitOutTime",
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    "IsAccurate",
    "Deleted",
]


def ingest_session(year: int, rnd: int, session_num: int, code: str, *, force: bool) -> str:
    """Ingest one session. Returns a one-word status: written / skipped / empty / error."""
    out_path = LAPS_DIR / str(year) / str(rnd) / f"{code}.parquet"
    if out_path.exists() and not force:
        return "skipped"

    try:
        session = fastf1.get_session(year, rnd, session_num)
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        laps = session.laps
    except Exception as e:  # noqa: BLE001  FastF1 raises a zoo of errors (including DataNotLoadedError when load() silently fails)
        print(f"    {code}: load failed ({type(e).__name__}: {e})")
        return "error"

    if laps is None or laps.empty:
        print(f"    {code}: empty")
        return "empty"

    cols = [c for c in KEEP_COLS if c in laps.columns]
    trimmed = laps[cols].copy()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    trimmed.to_parquet(out_path, index=False)
    size_kb = out_path.stat().st_size / 1024
    print(f"    {code}: wrote {len(trimmed)} laps ({size_kb:.1f} KB)")
    return "written"


def ingest_event(year: int, rnd: int, *, force: bool) -> None:
    try:
        event = fastf1.get_event(year, rnd)
    except Exception as e:  # noqa: BLE001
        print(f"  Could not load event metadata: {e}")
        return

    name = event.get("EventName", f"Round {rnd}")
    print(f"  {year} R{rnd} — {name}")

    for i in range(1, 6):
        sess_name = event.get(f"Session{i}")
        if not isinstance(sess_name, str) or not sess_name.strip():
            continue
        code = SESSION_NAME_TO_CODE.get(sess_name)
        if not code:
            print(f"    Session{i}: unknown name '{sess_name}', skipping")
            continue
        ingest_session(year, rnd, i, code, force=force)


def ingest_season(year: int, *, force: bool) -> None:
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    print(f"{year}: {len(schedule)} rounds")
    for _, row in schedule.iterrows():
        rnd = int(row["RoundNumber"])
        ingest_event(year, rnd, force=force)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("year", type=int)
    ap.add_argument("round", type=int, nargs="?")
    ap.add_argument("--force", action="store_true", help="Overwrite existing parquet files")
    args = ap.parse_args()

    if args.round is None:
        ingest_season(args.year, force=args.force)
    else:
        ingest_event(args.year, args.round, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
