"""F1 chat agent: Claude (Opus 4.8) with tool use over the project's data.

Wraps the existing `jolpica`, `laps`, and `news` modules as tools so the
model can answer questions about race results, qualifying, sprints,
standings, lap times, and the latest news. The agent loop is manual so we
keep control over iteration limits and tool dispatch.

The API key is read from the environment (.env via python-dotenv). It is
never logged or returned to the client.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

import jolpica as j
import laps as lp
import news as nw
import search_regs as regs

# Load .env from the project root regardless of the process CWD.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "claude-opus-4-8"
MAX_TOOL_ITERATIONS = 8

# Lazily constructed so the rest of the backend imports even when no API key
# is configured (e.g. the results/news endpoints don't need it).
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY from env
    return _client

SYSTEM = """You are an F1 assistant embedded in a personal Formula 1 web app.
You answer questions about race results, qualifying, sprints, championship
standings, lap times, the latest F1 news, and the FIA regulations.

Use the provided tools to look up real data rather than answering from memory —
your training data may be stale and the user expects current, accurate figures.
Rounds are numbered within a season; if you only know a Grand Prix by name,
call get_schedule to find its round number first. Lap-time data is only
available from 2018 onward.

For any question about the rules — technical specs, sporting procedures,
penalties, car dimensions, weights, etc. — call search_regulations and base
your answer on the retrieved text. The corpus is the 2026 FIA F1 Sporting and
Technical Regulations. Cite the source document and page number for regulation
answers (e.g. "Technical Regulations, p.42"), and don't state a specific rule
value unless it appears in the retrieved chunks.

Be concise and conversational; format results as short tables or lists when
helpful. If a tool returns no data, say so plainly rather than inventing an
answer."""

TOOLS: list[dict] = [
    {
        "name": "list_seasons",
        "description": "List all F1 seasons that have data, newest first.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_schedule",
        "description": "Get the race calendar for a season: round numbers, "
        "Grand Prix names, dates, and circuits. Use this to map a race name to "
        "its round number.",
        "input_schema": {
            "type": "object",
            "properties": {"year": {"type": "integer", "description": "Season, e.g. 2024"}},
            "required": ["year"],
        },
    },
    {
        "name": "get_race_results",
        "description": "Race classification for a given season and round: "
        "finishing positions, drivers, constructors, times/gaps, status, points.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "round": {"type": "integer"},
            },
            "required": ["year", "round"],
        },
    },
    {
        "name": "get_qualifying",
        "description": "Qualifying results (Q1/Q2/Q3 times) for a season and round.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "round": {"type": "integer"},
            },
            "required": ["year", "round"],
        },
    },
    {
        "name": "get_sprint",
        "description": "Sprint race results for a season and round (empty if no "
        "sprint that weekend).",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "round": {"type": "integer"},
            },
            "required": ["year", "round"],
        },
    },
    {
        "name": "get_standings",
        "description": "Driver and constructor championship standings after a "
        "given season and round.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "round": {"type": "integer"},
            },
            "required": ["year", "round"],
        },
    },
    {
        "name": "get_lap_summary",
        "description": "Fastest lap per driver for a session at a given season "
        "and round. session_group is 'practice', 'quali', or 'race'. Lap data "
        "exists only from 2018 onward.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "round": {"type": "integer"},
                "session_group": {
                    "type": "string",
                    "enum": ["practice", "quali", "race"],
                },
            },
            "required": ["year", "round", "session_group"],
        },
    },
    {
        "name": "get_latest_news",
        "description": "The latest F1 news headlines from major outlets, newest "
        "first. Use for 'what's the latest', recent events, or breaking news.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max headlines (default 15)"}
            },
        },
    },
    {
        "name": "search_regulations",
        "description": "Semantic search over the 2026 FIA F1 Sporting and "
        "Technical Regulations. Use for any rules question (car weight, "
        "dimensions, power unit, penalties, parc fermé, track limits, etc.). "
        "Returns the most relevant regulation passages with source document and "
        "page number for citation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language description of the rule to find.",
                },
                "k": {"type": "integer", "description": "Number of passages (default 5)"},
            },
            "required": ["query"],
        },
    },
]

_LAP_GROUPS = {"practice": ["FP1", "FP2", "FP3"], "quali": ["Q", "SQ", "SS"], "race": ["R", "S"]}


def _driver_name(d: dict) -> str:
    return f"{d.get('givenName', '')} {d.get('familyName', '')}".strip()


def _lap_summary(year: int, rnd: int, group: str) -> Any:
    codes = _LAP_GROUPS.get(group, [])
    available = [c for c in codes if c in lp.available_codes(year, rnd)]
    if not available:
        return {"available": [], "note": "No lap data for this session."}
    code = available[0]
    df = lp.load_laps(year, rnd, code)
    if df is None or df.empty:
        return {"available": available, "note": "Lap file empty."}
    fastest = lp.fastest_per_driver(df)
    return {
        "session": lp.CODE_LABELS.get(code, code),
        "fastest": fastest.to_dict("records") if not fastest.empty else [],
    }


def _run_tool(name: str, args: dict) -> Any:
    """Dispatch a tool call to the underlying data module."""
    if name == "list_seasons":
        return sorted((int(s["season"]) for s in j.list_seasons()), reverse=True)
    if name == "get_schedule":
        return [
            {
                "round": int(r["round"]),
                "raceName": r.get("raceName", ""),
                "date": r.get("date", ""),
                "circuit": r.get("Circuit", {}).get("circuitName", ""),
            }
            for r in j.get_schedule(args["year"])
        ]
    if name == "get_race_results":
        data = j.get_race_results(args["year"], args["round"])
        return [
            {
                "pos": r.get("positionText", ""),
                "driver": _driver_name(r.get("Driver", {})),
                "constructor": r.get("Constructor", {}).get("name", ""),
                "grid": r.get("grid", ""),
                "timeOrGap": r.get("Time", {}).get("time") or r.get("status", ""),
                "status": r.get("status", ""),
                "points": r.get("points", ""),
            }
            for r in data.get("Results", [])
        ]
    if name == "get_qualifying":
        data = j.get_qualifying(args["year"], args["round"])
        return [
            {
                "pos": r.get("position", ""),
                "driver": _driver_name(r.get("Driver", {})),
                "constructor": r.get("Constructor", {}).get("name", ""),
                "Q1": r.get("Q1", ""),
                "Q2": r.get("Q2", ""),
                "Q3": r.get("Q3", ""),
            }
            for r in data.get("QualifyingResults", [])
        ]
    if name == "get_sprint":
        data = j.get_sprint(args["year"], args["round"])
        return [
            {
                "pos": r.get("positionText", ""),
                "driver": _driver_name(r.get("Driver", {})),
                "constructor": r.get("Constructor", {}).get("name", ""),
                "points": r.get("points", ""),
            }
            for r in data.get("SprintResults", [])
        ]
    if name == "get_standings":
        ds = j.get_driver_standings(args["year"], args["round"])
        cs = j.get_constructor_standings(args["year"], args["round"])
        return {
            "drivers": [
                {
                    "pos": s.get("position", ""),
                    "driver": _driver_name(s.get("Driver", {})),
                    "constructor": (s.get("Constructors") or [{}])[0].get("name", ""),
                    "points": s.get("points", ""),
                    "wins": s.get("wins", ""),
                }
                for s in ds
            ],
            "constructors": [
                {
                    "pos": s.get("position", ""),
                    "constructor": s.get("Constructor", {}).get("name", ""),
                    "points": s.get("points", ""),
                    "wins": s.get("wins", ""),
                }
                for s in cs
            ],
        }
    if name == "get_lap_summary":
        return _lap_summary(args["year"], args["round"], args["session_group"])
    if name == "get_latest_news":
        return nw.get_news(limit=args.get("limit", 15))["items"]
    if name == "search_regulations":
        hits = regs.search_regulations(args["query"], k=args.get("k", 5))
        return [
            {
                "source": h.get("source", ""),
                "page": h.get("page", ""),
                "text": h.get("text", ""),
            }
            for h in hits
        ]
    return {"error": f"Unknown tool {name}"}


def answer(messages: list[dict]) -> str:
    """Run the agent loop over a conversation and return the final text.

    `messages` is a list of {role, content} text turns (user/assistant). Tool
    use happens internally; only the final assistant text is returned.
    """
    convo: list[dict] = list(messages)

    client = _get_client()
    for _ in range(MAX_TOOL_ITERATIONS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM,
            tools=TOOLS,
            messages=convo,
        )

        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()

        # Preserve the assistant turn (thinking + tool_use blocks) verbatim.
        convo.append({"role": "assistant", "content": resp.content})

        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                try:
                    result = _run_tool(block.name, dict(block.input))
                    content = json.dumps(result, default=str)
                    is_error = False
                except Exception as e:  # surface tool failure to the model
                    content = f"Tool error: {e}"
                    is_error = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )
        convo.append({"role": "user", "content": tool_results})

    return "Sorry — I couldn't resolve that within the tool-call limit. Try rephrasing?"
