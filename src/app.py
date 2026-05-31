"""Streamlit UI for browsing F1 race results via Jolpica.

Run from the project root:
    streamlit run src/app.py
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

import jolpica as j
import laps as lp

st.set_page_config(page_title="F1 Race Results", layout="wide")
st.title("F1 Race Results")


@st.cache_data(show_spinner=False)
def cached_seasons() -> list[dict]:
    return j.list_seasons()


@st.cache_data(show_spinner=False)
def cached_schedule(year: int) -> list[dict]:
    return j.get_schedule(year)


@st.cache_data(show_spinner=False)
def cached_race(year: int, rnd: int) -> dict:
    return j.get_race_results(year, rnd)


@st.cache_data(show_spinner=False)
def cached_qualifying(year: int, rnd: int) -> dict:
    return j.get_qualifying(year, rnd)


@st.cache_data(show_spinner=False)
def cached_sprint(year: int, rnd: int) -> dict:
    return j.get_sprint(year, rnd)


@st.cache_data(show_spinner=False)
def cached_driver_standings(year: int, rnd: int) -> list[dict]:
    return j.get_driver_standings(year, rnd)


@st.cache_data(show_spinner=False)
def cached_constructor_standings(year: int, rnd: int) -> list[dict]:
    return j.get_constructor_standings(year, rnd)


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


# Sidebar selectors
with st.sidebar:
    st.header("Browse")
    seasons = cached_seasons()
    years = sorted((int(s["season"]) for s in seasons), reverse=True)
    year = st.selectbox("Season", years, index=0)

    schedule = cached_schedule(year)
    if not schedule:
        st.warning(f"No rounds found for {year}.")
        st.stop()

    round_options = list(range(len(schedule)))
    idx = st.selectbox(
        "Round",
        round_options,
        format_func=lambda i: f"R{schedule[i]['round']} — {schedule[i]['raceName']} ({schedule[i]['date']})",
    )

race = schedule[idx]
rnd = int(race["round"])
circ = race.get("Circuit", {})
loc = circ.get("Location", {})

try:
    race_date = date.fromisoformat(race["date"])
    is_future = race_date > date.today()
except (KeyError, ValueError):
    race_date = None
    is_future = False

future_msg = (
    f"This race hasn't happened yet — scheduled for {race_date.isoformat()}."
    if race_date
    else "This race hasn't happened yet."
)

st.subheader(f"{year} {race['raceName']}  —  Round {rnd}")
st.caption(
    f"{circ.get('circuitName', '')} — {loc.get('locality', '')}, {loc.get('country', '')}  ·  {race.get('date', '')}"
)

HAS_LAPS = year >= 2018
if HAS_LAPS:
    (
        tab_race,
        tab_quali,
        tab_sprint,
        tab_standings,
        tab_practice_laps,
        tab_quali_laps,
        tab_race_laps,
    ) = st.tabs(
        [
            "Race",
            "Qualifying",
            "Sprint",
            "Standings",
            "Practice laps",
            "Quali laps",
            "Race laps",
        ]
    )
else:
    tab_race, tab_quali, tab_sprint, tab_standings = st.tabs(
        ["Race", "Qualifying", "Sprint", "Standings"]
    )
    tab_practice_laps = tab_quali_laps = tab_race_laps = None


def _render_session_laps(year_: int, rnd_: int, codes: list[str]) -> None:
    """Pick a session code (if multiple), then render chart + fastest-lap table."""
    available = [c for c in codes if c in lp.available_codes(year_, rnd_)]
    if not available:
        st.info(
            "No lap data ingested for this session yet. From the project root run:\n\n"
            f"`python src/ingest_laps.py {year_} {rnd_}`"
        )
        return

    if len(available) == 1:
        code = available[0]
        st.caption(lp.CODE_LABELS[code])
    else:
        code = st.radio(
            "Session",
            available,
            format_func=lambda c: lp.CODE_LABELS[c],
            horizontal=True,
            key=f"laps_{year_}_{rnd_}_{'_'.join(codes)}",
        )

    df = lp.load_laps(year_, rnd_, code)
    if df is None or df.empty:
        st.info("Parquet file is empty.")
        return

    pivot = lp.chart_pivot(df)
    if not pivot.empty:
        st.markdown("**Lap times** (seconds)")
        st.line_chart(pivot, height=420)

    fastest = lp.fastest_per_driver(df)
    if not fastest.empty:
        st.markdown("**Fastest lap per driver**")
        st.dataframe(fastest, hide_index=True, width="stretch")

with tab_race:
    if is_future:
        st.info(future_msg)
    else:
        data = cached_race(year, rnd)
        results = data.get("Results", [])
        if not results:
            st.info("No race classification available for this round.")
        else:
            st.dataframe(
                pd.DataFrame(_classification_rows(results)),
                hide_index=True,
                width="stretch",
            )

with tab_quali:
    if is_future:
        st.info(future_msg)
    else:
        data = cached_qualifying(year, rnd)
        results = data.get("QualifyingResults", [])
        if not results:
            st.info("No qualifying data available for this round (Jolpica coverage thins out before ~2003).")
        else:
            rows = [
                {
                    "Pos": r.get("position", ""),
                    "No": r.get("number", ""),
                    "Driver": _driver_name(r.get("Driver", {})),
                    "Constructor": r.get("Constructor", {}).get("name", ""),
                    "Q1": r.get("Q1", ""),
                    "Q2": r.get("Q2", ""),
                    "Q3": r.get("Q3", ""),
                }
                for r in results
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

with tab_sprint:
    if is_future:
        st.info(future_msg)
    else:
        data = cached_sprint(year, rnd)
        results = data.get("SprintResults", [])
        if not results:
            st.info("No sprint at this weekend.")
        else:
            st.dataframe(
                pd.DataFrame(_classification_rows(results)),
                hide_index=True,
                width="stretch",
            )

with tab_standings:
    if is_future:
        st.info(future_msg)
    else:
        col_d, col_c = st.columns(2)

        with col_d:
            st.markdown("**Drivers after this round**")
            ds = cached_driver_standings(year, rnd)
            if not ds:
                st.info("No driver standings available.")
            else:
                rows = [
                    {
                        "Pos": s.get("position", ""),
                        "Driver": _driver_name(s.get("Driver", {})),
                        "Constructor": (s.get("Constructors") or [{}])[0].get("name", ""),
                        "Pts": s.get("points", ""),
                        "Wins": s.get("wins", ""),
                    }
                    for s in ds
                ]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        with col_c:
            st.markdown("**Constructors after this round**")
            cs = cached_constructor_standings(year, rnd)
            if not cs:
                st.info("No constructor standings available (pre-1958 seasons have drivers only).")
            else:
                rows = [
                    {
                        "Pos": s.get("position", ""),
                        "Constructor": s.get("Constructor", {}).get("name", ""),
                        "Pts": s.get("points", ""),
                        "Wins": s.get("wins", ""),
                    }
                    for s in cs
                ]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

if HAS_LAPS:
    with tab_practice_laps:
        if is_future:
            st.info(future_msg)
        else:
            _render_session_laps(year, rnd, ["FP1", "FP2", "FP3"])

    with tab_quali_laps:
        if is_future:
            st.info(future_msg)
        else:
            _render_session_laps(year, rnd, ["Q", "SQ", "SS"])

    with tab_race_laps:
        if is_future:
            st.info(future_msg)
        else:
            _render_session_laps(year, rnd, ["R", "S"])
