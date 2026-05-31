"""Helpers for loading and presenting lap-time Parquet files.

The Parquet files are produced by `src/ingest_laps.py` and live at
`data/laps/{year}/{round}/{code}.parquet`. Code values: FP1, FP2, FP3,
Q, SQ, SS, S, R.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

LAPS_DIR = Path("data/laps")

CODE_LABELS = {
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
    "Q": "Qualifying",
    "SQ": "Sprint Qualifying",
    "SS": "Sprint Shootout",
    "S": "Sprint",
    "R": "Race",
}


def parquet_path(year: int, rnd: int, code: str) -> Path:
    return LAPS_DIR / str(year) / str(rnd) / f"{code}.parquet"


def available_codes(year: int, rnd: int) -> list[str]:
    """Codes for which a Parquet file exists, in the canonical session order."""
    d = LAPS_DIR / str(year) / str(rnd)
    if not d.exists():
        return []
    present = {p.stem for p in d.glob("*.parquet")}
    return [c for c in CODE_LABELS if c in present]


def load_laps(year: int, rnd: int, code: str) -> pd.DataFrame | None:
    p = parquet_path(year, rnd, code)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "LapTime" in df.columns:
        df["LapTimeSeconds"] = df["LapTime"].dt.total_seconds()
    return df


def _fmt_td(td) -> str:
    if pd.isna(td):
        return ""
    total = td.total_seconds()
    m, s = divmod(total, 60)
    return f"{int(m)}:{s:06.3f}"


def fastest_per_driver(df: pd.DataFrame) -> pd.DataFrame:
    """One row per driver, their personal-best lap in this session."""
    if "LapTimeSeconds" not in df.columns:
        return pd.DataFrame()
    valid = df.dropna(subset=["LapTimeSeconds"])
    if valid.empty:
        return valid
    idx = valid.groupby("Driver")["LapTimeSeconds"].idxmin()
    out = valid.loc[idx].sort_values("LapTimeSeconds").copy()

    rows = []
    for _, r in out.iterrows():
        rows.append(
            {
                "Driver": r.get("Driver", ""),
                "Team": r.get("Team", ""),
                "Lap #": int(r["LapNumber"]) if pd.notna(r.get("LapNumber")) else "",
                "Best lap": _fmt_td(r.get("LapTime")),
                "Compound": r.get("Compound", "") or "",
                "Tyre age": (
                    int(r["TyreLife"]) if pd.notna(r.get("TyreLife")) else ""
                ),
            }
        )
    return pd.DataFrame(rows)


def chart_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Wide DataFrame for st.line_chart: index=LapNumber, columns=Driver, values=seconds."""
    if "LapTimeSeconds" not in df.columns or "LapNumber" not in df.columns:
        return pd.DataFrame()
    valid = df.dropna(subset=["LapTimeSeconds", "LapNumber"]).copy()
    if valid.empty:
        return valid
    valid["LapNumber"] = valid["LapNumber"].astype(int)
    return valid.pivot_table(
        index="LapNumber", columns="Driver", values="LapTimeSeconds", aggfunc="first"
    )
