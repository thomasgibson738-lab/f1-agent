"""FastAPI backend for the F1 agent results browser.

Wraps the existing `jolpica` and `laps` modules (in ../src) as JSON
endpoints so a static HTML/JS frontend can consume them. Run from the
project root so the relative cache/data paths resolve:

    uvicorn backend.main:app --reload

Deployed on Render; the static frontend (Netlify) calls these endpoints.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# The agent logic lives in src/ and imports its siblings flatly
# (e.g. `import jolpica`), so put src/ on the path.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import jolpica as j  # noqa: E402
import laps as lp  # noqa: E402

app = FastAPI(title="F1 Agent API", version="0.1")

# Personal project: allow any origin so the Netlify frontend (whatever
# its final domain) can call the Render backend without re-deploys.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _driver_name(d: dict) -> str:
    return f"{d.get('givenName', '')} {d.get('familyName', '')}".strip()


def _classification_rows(results: list[dict]) -> list[dict]:
    """Race or sprint results share the same shape."""
    return [
        {
            "Pos": r.get("positionText", r.get("position", "")),
            "No": r.get("number", ""),
            "Driver": _driver_name(r.get("Driver", {})),
            "Constructor": r.get("Constructor", {}).get("name", ""),
            "Laps": r.get("laps", ""),
            "Grid": r.get("grid", ""),
            "Time/Gap": r.get("Time", {}).get("time") or r.get("status", ""),
            "Status": r.get("status", ""),
            "Pts": r.get("points", ""),
        }
        for r in results
    ]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/seasons")
def seasons() -> list[int]:
    return sorted((int(s["season"]) for s in j.list_seasons()), reverse=True)


@app.get("/api/schedule/{year}")
def schedule(year: int) -> list[dict]:
    """Round listing, enriched with a few fields the frontend needs."""
    rounds = j.get_schedule(year)
    out = []
    for race in rounds:
        circ = race.get("Circuit", {})
        loc = circ.get("Location", {})
        try:
            is_future = date.fromisoformat(race["date"]) > date.today()
        except (KeyError, ValueError):
            is_future = False
        out.append(
            {
                "round": int(race["round"]),
                "raceName": race.get("raceName", ""),
                "date": race.get("date", ""),
                "circuitName": circ.get("circuitName", ""),
                "locality": loc.get("locality", ""),
                "country": loc.get("country", ""),
                "isFuture": is_future,
                "hasLaps": year >= 2018,
            }
        )
    return out


@app.get("/api/results/{year}/{rnd}")
def results(year: int, rnd: int) -> list[dict]:
    data = j.get_race_results(year, rnd)
    return _classification_rows(data.get("Results", []))


@app.get("/api/qualifying/{year}/{rnd}")
def qualifying(year: int, rnd: int) -> list[dict]:
    data = j.get_qualifying(year, rnd)
    return [
        {
            "Pos": r.get("position", ""),
            "No": r.get("number", ""),
            "Driver": _driver_name(r.get("Driver", {})),
            "Constructor": r.get("Constructor", {}).get("name", ""),
            "Q1": r.get("Q1", ""),
            "Q2": r.get("Q2", ""),
            "Q3": r.get("Q3", ""),
        }
        for r in data.get("QualifyingResults", [])
    ]


@app.get("/api/sprint/{year}/{rnd}")
def sprint(year: int, rnd: int) -> list[dict]:
    data = j.get_sprint(year, rnd)
    return _classification_rows(data.get("SprintResults", []))


@app.get("/api/standings/{year}/{rnd}")
def standings(year: int, rnd: int) -> dict:
    ds = j.get_driver_standings(year, rnd)
    cs = j.get_constructor_standings(year, rnd)
    return {
        "drivers": [
            {
                "Pos": s.get("position", ""),
                "Driver": _driver_name(s.get("Driver", {})),
                "Constructor": (s.get("Constructors") or [{}])[0].get("name", ""),
                "Pts": s.get("points", ""),
                "Wins": s.get("wins", ""),
            }
            for s in ds
        ],
        "constructors": [
            {
                "Pos": s.get("position", ""),
                "Constructor": s.get("Constructor", {}).get("name", ""),
                "Pts": s.get("points", ""),
                "Wins": s.get("wins", ""),
            }
            for s in cs
        ],
    }


# Lap-session groupings, mirroring the old Streamlit tabs.
_LAP_GROUPS = {
    "practice": ["FP1", "FP2", "FP3"],
    "quali": ["Q", "SQ", "SS"],
    "race": ["R", "S"],
}


@app.get("/api/laps/{year}/{rnd}/{group}")
def laps(year: int, rnd: int, group: str, code: str | None = None) -> dict:
    """Lap data for a session group.

    Returns the available session codes plus, for the requested code
    (defaults to the first available, or the `?code=` query param if it
    is present and valid), a per-lap series for charting and a
    fastest-lap-per-driver table.
    """
    codes = _LAP_GROUPS.get(group)
    if codes is None:
        raise HTTPException(404, f"Unknown lap group '{group}'")

    available = [c for c in codes if c in lp.available_codes(year, rnd)]
    if not available:
        return {"available": [], "code": None, "series": [], "fastest": []}

    code = code if code in available else available[0]
    df = lp.load_laps(year, rnd, code)
    if df is None or df.empty:
        return {"available": available, "code": code, "series": [], "fastest": []}

    # Long-form lap series: {driver, lap, seconds} — the frontend pivots
    # this into one line per driver.
    series = []
    if {"LapTimeSeconds", "LapNumber", "Driver"}.issubset(df.columns):
        valid = df.dropna(subset=["LapTimeSeconds", "LapNumber"])
        for _, r in valid.iterrows():
            series.append(
                {
                    "driver": r["Driver"],
                    "lap": int(r["LapNumber"]),
                    "seconds": round(float(r["LapTimeSeconds"]), 3),
                }
            )

    fastest = lp.fastest_per_driver(df)
    fastest_rows = fastest.to_dict("records") if not fastest.empty else []

    return {
        "available": available,
        "code": code,
        "label": lp.CODE_LABELS.get(code, code),
        "series": series,
        "fastest": fastest_rows,
    }
