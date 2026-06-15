"""F1 news digest from public RSS feeds, cached in SQLite.

Fetches a handful of F1 news feeds, de-duplicates and sorts by publish
time, and caches the result in `data/news/news.db`. The cache carries a
`fetched_at` timestamp; `get_news` refreshes lazily when the cache is
stale (older than `max_age_hours`), so the digest is fresh each morning
the page is opened without needing a separate scheduler.

A `refresh()` entry point is also provided so a cron job (local or
Render) can warm the cache on a schedule if you want true push-style
updates.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests

NEWS_DIR = Path("data/news")
NEWS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = NEWS_DIR / "news.db"

# Public F1 news feeds. Each is best-effort: a feed that fails or moves
# is skipped without breaking the digest.
FEEDS = [
    ("Formula1.com", "https://www.formula1.com/en/latest/all.xml"),
    ("Autosport", "https://www.autosport.com/rss/f1/news/"),
    ("Motorsport.com", "https://www.motorsport.com/rss/f1/news/"),
    ("RaceFans", "https://www.racefans.net/feed/"),
    ("The Race", "https://www.the-race.com/formula-1/feed/"),
    ("PlanetF1", "https://www.planetf1.com/feed"),
]

DEFAULT_MAX_AGE_HOURS = 3
DEFAULT_LIMIT = 40
_HEADERS = {"User-Agent": "f1-agent/0.1 (personal project)"}


def _init_db(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            link      TEXT PRIMARY KEY,
            title     TEXT NOT NULL,
            source    TEXT NOT NULL,
            summary   TEXT,
            published REAL          -- unix epoch seconds, may be NULL
        )
        """
    )
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    con.commit()


def _parse_published(entry) -> float | None:
    """Best-effort publish time as unix epoch seconds."""
    if getattr(entry, "published_parsed", None):
        return time.mktime(entry.published_parsed)
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                return parsedate_to_datetime(raw).timestamp()
            except (TypeError, ValueError):
                pass
    return None


def _clean(text: str | None, limit: int = 280) -> str:
    if not text:
        return ""
    # feedparser hands back HTML in summaries; strip tags crudely.
    import re

    plain = re.sub(r"<[^>]+>", "", text).strip()
    plain = re.sub(r"\s+", " ", plain)
    return plain[:limit] + ("…" if len(plain) > limit else "")


def _fetch_all() -> list[dict]:
    """Fetch every feed, returning a flat list of item dicts."""
    items: list[dict] = []
    for source, url in FEEDS:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception:
            continue  # one bad feed shouldn't sink the digest
        for entry in parsed.entries:
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            items.append(
                {
                    "link": link,
                    "title": title.strip(),
                    "source": source,
                    "summary": _clean(entry.get("summary")),
                    "published": _parse_published(entry),
                }
            )
    return items


def refresh() -> int:
    """Fetch all feeds and upsert into the cache. Returns item count fetched."""
    items = _fetch_all()
    con = sqlite3.connect(DB_PATH)
    try:
        _init_db(con)
        con.executemany(
            """
            INSERT INTO items (link, title, source, summary, published)
            VALUES (:link, :title, :source, :summary, :published)
            ON CONFLICT(link) DO UPDATE SET
                title=excluded.title,
                source=excluded.source,
                summary=excluded.summary,
                published=COALESCE(excluded.published, items.published)
            """,
            items,
        )
        con.execute(
            "INSERT INTO meta (key, value) VALUES ('fetched_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(time.time()),),
        )
        con.commit()
    finally:
        con.close()
    return len(items)


def _last_fetch(con: sqlite3.Connection) -> float:
    row = con.execute("SELECT value FROM meta WHERE key='fetched_at'").fetchone()
    return float(row[0]) if row else 0.0


def get_news(
    limit: int = DEFAULT_LIMIT, max_age_hours: float = DEFAULT_MAX_AGE_HOURS
) -> dict:
    """Return the cached digest, refreshing lazily if stale.

    Shape: {"items": [...], "fetchedAt": iso8601 | None}.
    """
    con = sqlite3.connect(DB_PATH)
    try:
        _init_db(con)
        age = time.time() - _last_fetch(con)
        stale = age > max_age_hours * 3600
    finally:
        con.close()

    if stale:
        refresh()

    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute(
            "SELECT title, link, source, summary, published FROM items "
            "ORDER BY (published IS NULL), published DESC LIMIT ?",
            (limit,),
        ).fetchall()
        fetched_at = _last_fetch(con)
    finally:
        con.close()

    items = [
        {
            "title": t,
            "link": link,
            "source": source,
            "summary": summary,
            "published": (
                datetime.fromtimestamp(pub, timezone.utc).isoformat()
                if pub
                else None
            ),
        }
        for (t, link, source, summary, pub) in rows
    ]
    fetched_iso = (
        datetime.fromtimestamp(fetched_at, timezone.utc).isoformat()
        if fetched_at
        else None
    )
    return {"items": items, "fetchedAt": fetched_iso}


if __name__ == "__main__":
    # Manual warm/refresh: python src/news.py
    n = refresh()
    print(f"Fetched {n} items into {DB_PATH}")
