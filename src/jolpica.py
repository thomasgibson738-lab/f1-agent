"""Jolpica-F1 (Ergast successor) HTTP client.

Wraps the public REST API at https://api.jolpi.ca/ergast/f1/ with a
persistent SQLite HTTP cache. Historical race data is immutable, so we
cache forever; only the current/future season needs refreshing and we
can handle that later by clearing specific entries.

Public functions return the inner payloads directly (lists of dicts or
single dicts), stripping the MRData wrapper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests_cache

BASE = "https://api.jolpi.ca/ergast/f1"
CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "jolpica"

_session = requests_cache.CachedSession(
    cache_name=str(CACHE_FILE),
    backend="sqlite",
    expire_after=requests_cache.NEVER_EXPIRE,
    allowable_codes=(200,),
)
_session.headers.update({"User-Agent": "f1-agent/0.1 (personal project)"})


def _get(path: str, **params: Any) -> dict:
    """GET {BASE}/{path}.json. Returns the MRData payload."""
    url = f"{BASE}/{path}.json"
    params.setdefault("limit", 100)
    r = _session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["MRData"]


def list_seasons() -> list[dict]:
    """All F1 seasons. Each item has a 'season' string like '1950'."""
    data = _get("seasons", limit=100)
    return data["SeasonTable"]["Seasons"]


def get_schedule(year: int) -> list[dict]:
    """Round listing for a season (race name, date, circuit, etc.)."""
    data = _get(f"{year}", limit=100)
    return data["RaceTable"]["Races"]


def get_race_results(year: int, round_: int) -> dict:
    """Single race classification. Returns {} if no data."""
    data = _get(f"{year}/{round_}/results", limit=100)
    races = data["RaceTable"]["Races"]
    return races[0] if races else {}


def get_qualifying(year: int, round_: int) -> dict:
    data = _get(f"{year}/{round_}/qualifying", limit=100)
    races = data["RaceTable"]["Races"]
    return races[0] if races else {}


def get_sprint(year: int, round_: int) -> dict:
    data = _get(f"{year}/{round_}/sprint", limit=100)
    races = data["RaceTable"]["Races"]
    return races[0] if races else {}


def get_driver_standings(year: int, round_: int) -> list[dict]:
    """Driver standings after the given round."""
    data = _get(f"{year}/{round_}/driverStandings", limit=100)
    lists = data["StandingsTable"]["StandingsLists"]
    return lists[0]["DriverStandings"] if lists else []


def get_constructor_standings(year: int, round_: int) -> list[dict]:
    data = _get(f"{year}/{round_}/constructorStandings", limit=100)
    lists = data["StandingsTable"]["StandingsLists"]
    return lists[0]["ConstructorStandings"] if lists else []
