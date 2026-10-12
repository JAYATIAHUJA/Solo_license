"""What a coding agent has spent, and the budget it may not exceed.

Spend comes from whatever each agent itself exposes, read by one adapter per
agent behind two entry points:

* :func:`ingest` - a usage report the agent pushes (Claude Code's statusline
  JSON, OpenCode's ``message.updated`` events forwarded by our plugin);
* :func:`usage_from_transcript` - the session file a hook names in
  ``transcript_path`` (Claude Code, Codex, Gemini CLI), read incrementally.

A cost the agent reports is used as is (``reported``); token counts are priced
from :data:`PRICES` at list price (``estimate``). Agents that expose neither
are ``unknown``: their spend is never guessed. Caps come from the policy
(``[budget]``); the gate enforces them through the same paths for every agent.

Standard library only.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# USD per million tokens: (input, output, cache read, cache write). List
# prices; matched as a substring of the model id, longest key first. Override
# or extend per machine in Settings (stored as ``model_prices``).
PRICES: dict[str, tuple[float, float, float, float]] = {
    # Anthropic
    "claude-opus-4-1": (15.0, 75.0, 1.5, 18.75),
    "claude-opus-4-2025": (15.0, 75.0, 1.5, 18.75),
    "opus": (5.0, 25.0, 0.5, 6.25),
    "sonnet": (3.0, 15.0, 0.3, 3.75),
    "claude-3-5-haiku": (0.8, 4.0, 0.08, 1.0),
    "haiku": (1.0, 5.0, 0.1, 1.25),
    # OpenAI
    "gpt-5-pro": (15.0, 120.0, 15.0, 0.0),
    "gpt-5-mini": (0.25, 2.0, 0.025, 0.0),
    "gpt-5-nano": (0.05, 0.4, 0.005, 0.0),
    "gpt-5": (1.25, 10.0, 0.125, 0.0),
    "gpt-4.1-mini": (0.4, 1.6, 0.1, 0.0),
    "gpt-4.1": (2.0, 8.0, 0.5, 0.0),
    "codex-mini": (1.5, 6.0, 0.375, 0.0),
    "o4-mini": (1.1, 4.4, 0.275, 0.0),
    "o3": (2.0, 8.0, 0.5, 0.0),
    # Google
    "gemini-3-pro": (2.0, 12.0, 0.2, 0.0),
    "gemini-3-flash": (0.5, 3.0, 0.05, 0.0),
    "gemini-2.5-pro": (1.25, 10.0, 0.125, 0.0),
    "gemini-2.5-flash-lite": (0.1, 0.4, 0.01, 0.0),
    "gemini-2.5-flash": (0.3, 2.5, 0.03, 0.0),
    # Zhipu / Z.ai
    "glm-4.5-air": (0.2, 1.1, 0.03, 0.0),
    "glm-4.5": (0.6, 2.2, 0.11, 0.0),
    "glm-4.6": (0.6, 2.2, 0.11, 0.0),
    # Moonshot, Alibaba, xAI, DeepSeek
    "kimi-k2": (0.6, 2.5, 0.15, 0.0),
    "qwen3-coder-plus": (1.0, 5.0, 0.1, 0.0),
    "grok-code-fast": (0.2, 1.5, 0.02, 0.0),
    "grok-4": (3.0, 15.0, 0.75, 0.0),
    "deepseek": (0.28, 0.42, 0.028, 0.0),
}

REPORTED, ESTIMATE, UNKNOWN = "reported", "estimate", "unknown"

# Where each agent's spend comes from: (kind, how). Kept next to the adapters
# so the dashboard never claims a source that is not read.
SOURCES: dict[str, tuple[str, str]] = {
    "claude-code": (REPORTED, "Claude Code's own session cost (statusline), else its transcript's token usage "
                              "at list prices"),
    "codex": (ESTIMATE, "token counts in the Codex session rollout, at list prices"),
    "gemini": (ESTIMATE, "token counts in the Gemini CLI session file, at list prices"),
    "opencode": (REPORTED, "OpenCode's own cost per message"),
}


def source_of(agent: str) -> tuple[str, str]:
    return SOURCES.get(agent, (UNKNOWN, "not reported by this agent's hooks"))


# --- tokens and prices ----------------------------------------------------------

@dataclass
class Tokens:
    input: int = 0          # fresh input (not read from the prompt cache)
    output: int = 0         # including reasoning / thinking
    cache_read: int = 0
    cache_write: int = 0

    def add(self, other: "Tokens") -> None:
        self.input += other.input
        self.output += other.output
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write


@dataclass
class Spend:
    """One session's usage so far, per model. ``reported_usd`` is the agent's own figure."""

    tokens: dict[str, Tokens] = field(default_factory=dict)
    reported_usd: float | None = None
    model: str = ""

    def add(self, model: str, tokens: Tokens) -> None:
        self.tokens.setdefault(model, Tokens()).add(tokens)
        self.model = model or self.model

    def total(self) -> Tokens:
        out = Tokens()
        for t in self.tokens.values():
            out.add(t)
        return out


def _num(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def load_prices(conn: sqlite3.Connection) -> dict[str, tuple[float, float, float, float]]:
    """This machine's price overrides (Settings), validated."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'model_prices'").fetchone()
    return clean_prices(json.loads(row["value"])) if row and row["value"] else {}


def clean_prices(raw: dict) -> dict[str, tuple[float, float, float, float]]:
    out = {}
    for key, value in (raw or {}).items():
        key = str(key).strip().lower()
        if not key or not isinstance(value, dict):
            continue
        try:
            parts = tuple(float(value.get(k) or 0) for k in ("input", "output", "cache_read", "cache_write"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"price for '{key}' must be numbers") from error
        if any(p < 0 or p > 10_000 for p in parts):
            raise ValueError(f"price for '{key}' is out of range")
        out[key] = parts
    return out


def price_for(model: str, overrides: dict | None = None) -> tuple[float, float, float, float] | None:
    """USD per million tokens for a model id, or None if unknown. Overrides win."""
    name = (model or "").lower().rsplit("/", 1)[-1]
    if not name:
        return None
    for table in (overrides or {}, PRICES):
        matches = [k for k in table if k in name]
        if matches:
            return table[max(matches, key=len)]
    return None


def estimate(spend: Spend, overrides: dict | None = None) -> tuple[float, list[str]]:
    """(USD at list price, models without a known price)."""
    usd, unpriced = 0.0, []
    for model, t in spend.tokens.items():
        price = price_for(model, overrides)
        if price is None:
            if t.total:
                unpriced.append(model or "unknown")
            continue
        usd += (t.input * price[0] + t.output * price[1] + t.cache_read * price[2]
                + t.cache_write * price[3]) / 1_000_000
    return usd, unpriced


# --- adapters: session files -------------------------------------------------------

class _ClaudeTranscript:
    """Claude Code transcript JSONL: an assistant line per content block, all
    carrying the message's ``usage``; counted once per message id.
    ``input_tokens`` excludes cache reads and writes."""

    def __init__(self) -> None:
        self.messages: dict[str, tuple[str, Tokens]] = {}

    def feed(self, rec: dict) -> None:
        msg = rec.get("message")
        if rec.get("type") != "assistant" or not isinstance(msg, dict):
            return
        usage, model = msg.get("usage"), str(msg.get("model") or "")
        if not isinstance(usage, dict) or not model or model.startswith("<"):
            return
        key = str(msg.get("id") or rec.get("requestId") or rec.get("uuid") or len(self.messages))
        self.messages[key] = (model, Tokens(_num(usage.get("input_tokens")), _num(usage.get("output_tokens")),
                                            _num(usage.get("cache_read_input_tokens")),
                                            _num(usage.get("cache_creation_input_tokens"))))

    def spend(self) -> Spend:
        out = Spend()
        for model, t in self.messages.values():
            out.add(model, t)
        return out


class _CodexRollout:
    """Codex rollout JSONL: ``token_count`` events carry the session's
    cumulative ``total_token_usage`` (``input_tokens`` includes the cached
    part); the growth between events is charged to the model of the latest
    ``turn_context``."""

    def __init__(self) -> None:
        self.model = ""
        self.prev = Tokens()
        self.out = Spend()

    def feed(self, rec: dict) -> None:
        kind, p = rec.get("type"), rec.get("payload")
        if not isinstance(p, dict):
            return
        if kind == "turn_context" and p.get("model"):
            self.model = str(p["model"])
            return
        if kind != "event_msg" or p.get("type") != "token_count":
            return
        total = (p.get("info") or {}).get("total_token_usage")
        if not isinstance(total, dict):
            return
        cached = _num(total.get("cached_input_tokens"))
        now = Tokens(max(0, _num(total.get("input_tokens")) - cached), _num(total.get("output_tokens")), cached,
                     _num(total.get("cache_write_input_tokens")))
        grew = Tokens(now.input - self.prev.input, now.output - self.prev.output,
                      now.cache_read - self.prev.cache_read, now.cache_write - self.prev.cache_write)
        if min(grew.input, grew.output, grew.cache_read, grew.cache_write) < 0:
            grew = now  # the counter restarted
        self.out.add(self.model or "unknown", grew)
        self.prev = now

    def spend(self) -> Spend:
        return self.out


class _GeminiSession:
    """Gemini CLI session file: ``gemini`` messages carry ``tokens`` (input =
    promptTokenCount, which includes the cached part; thoughts are billed as
    output). The JSONL form appends a message again when it changes, so the
    last copy of each id counts. Legacy ``.json`` files hold ``messages``."""

    def __init__(self) -> None:
        self.messages: dict[str, tuple[str, Tokens]] = {}

    def feed(self, rec: dict) -> None:
        for msg in rec["messages"] if isinstance(rec.get("messages"), list) else [rec]:
            if not isinstance(msg, dict) or msg.get("type") != "gemini" or not isinstance(msg.get("tokens"), dict):
                continue
            t = msg["tokens"]
            cached = _num(t.get("cached"))
            tokens = Tokens(max(0, _num(t.get("input")) - cached) + _num(t.get("tool")),
                            _num(t.get("output")) + _num(t.get("thoughts")), cached)
            self.messages[str(msg.get("id") or len(self.messages))] = (str(msg.get("model") or ""), tokens)

    def spend(self) -> Spend:
        out = Spend()
        for model, t in self.messages.values():
            out.add(model, t)
        return out


TRANSCRIPTS = {"claude-code": _ClaudeTranscript, "codex": _CodexRollout, "gemini": _GeminiSession}
_READ: dict[str, tuple[int, object]] = {}   # "<agent>:<path>" -> (bytes consumed, adapter)


def usage_from_transcript(agent: str, path: str | None) -> Spend | None:
    """Usage in the session file an agent's hook names, or None if this agent's
    file carries none. Only bytes appended since the last call are parsed."""
    factory = TRANSCRIPTS.get(agent)
    if factory is None or not path:
        return None
    file = Path(str(path))
    if file.suffix not in (".jsonl", ".json") or not file.is_file():
        return None
    if file.suffix == ".json":
        adapter = factory()
        try:
            adapter.feed(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None
        return adapter.spend()
    key = f"{agent}:{file}"
    offset, adapter = _READ.get(key, (0, None))
    try:
        size = file.stat().st_size
        if adapter is None or size < offset:
            offset, adapter = 0, factory()
        with file.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
    except OSError:
        return None
    end = chunk.rfind(b"\n")  # a half-written last line is read next time
    for line in chunk[:end + 1].splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            adapter.feed(rec)
    if len(_READ) > 256:
        _READ.clear()
    _READ[key] = (offset + end + 1, adapter)
    return adapter.spend()


# --- adapters: pushed reports ------------------------------------------------------

@dataclass(frozen=True)
class Report:
    session_id: str
    cwd: str
    part: str            # which slice of the session this figure covers
    spend: Spend
    transcript_path: str = ""


def _claude_statusline(p: dict) -> Report | None:
    """Claude Code statusline JSON: ``cost.total_cost_usd`` is Claude Code's
    own running total for the session (list price unless ``modelPricing``)."""
    cost = (p.get("cost") or {}).get("total_cost_usd")
    session = str(p.get("session_id") or "")
    if not session or not isinstance(cost, (int, float)):
        return None
    model = p.get("model") or {}
    cwd = (p.get("workspace") or {}).get("current_dir") or p.get("cwd") or "."
    return Report(session, str(cwd), "statusline",
                  Spend(reported_usd=float(cost), model=str(model.get("id") or "") if isinstance(model, dict) else ""),
                  str(p.get("transcript_path") or ""))


def _opencode_message(p: dict) -> Report | None:
    """An OpenCode AssistantMessage (``message.updated``): ``cost`` and
    ``tokens`` for that one message, final once ``time.completed`` is set."""
    info = p.get("info") if isinstance(p.get("info"), dict) else p
    if info.get("role") != "assistant" or not (info.get("time") or {}).get("completed"):
        return None
    session, message = str(info.get("sessionID") or ""), str(info.get("id") or "")
    if not session or not message:
        return None
    t = info.get("tokens") or {}
    cache = t.get("cache") or {}
    spend = Spend()
    spend.add(str(info.get("modelID") or ""), Tokens(_num(t.get("input")), _num(t.get("output")) + _num(t.get("reasoning")),
                                                      _num(cache.get("read")), _num(cache.get("write"))))
    cost = info.get("cost")
    # 0 with tokens: OpenCode had no price for the model; price it ourselves.
    if isinstance(cost, (int, float)) and (cost > 0 or not spend.total().total):
        spend.reported_usd = float(cost)
    path = info.get("path") or {}
    return Report(session, str(p.get("cwd") or path.get("root") or path.get("cwd") or "."), f"msg:{message}", spend)


PUSHED = {"claude-code": _claude_statusline, "opencode": _opencode_message}


def report_from(agent: str, payload: dict) -> Report | None:
    adapter = PUSHED.get(agent)
    return adapter(payload or {}) if adapter else None


# --- storage ------------------------------------------------------------------

def today() -> str:
    return date.today().isoformat()


@dataclass(frozen=True)
class SessionSpend:
    session_id: str
    usd: float = 0.0
    source: str = UNKNOWN
    tokens: int = 0
    unpriced: tuple[str, ...] = ()
    agent: str = ""
    repo: str = ""
    model: str = ""
    updated_at: str = ""


def session_spend(conn: sqlite3.Connection, session_id: str) -> SessionSpend:
    """A session's spend: the agent's own reported figures if there are any,
    else the estimate from its token counts."""
    rows = conn.execute("SELECT * FROM agent_spend WHERE session_id = ? ORDER BY updated_at", (session_id,)).fetchall()
    if not rows:
        return SessionSpend(session_id)
    reported = [r for r in rows if r["source"] == REPORTED]
    chosen = reported or rows
    counted = [r for r in chosen if r["tokens"]] or [r for r in rows if r["tokens"]]
    unpriced = sorted({m for r in chosen for m in (r["unpriced"] or "").split(",") if m})
    last = rows[-1]
    return SessionSpend(session_id, round(sum(r["cost_usd"] or 0.0 for r in chosen), 6),
                        REPORTED if reported else ESTIMATE, sum(r["tokens"] for r in counted), tuple(unpriced),
                        last["agent"], last["repo"], next((r["model"] for r in reversed(rows) if r["model"]), ""),
                        last["updated_at"])


def day_spend(conn: sqlite3.Connection, repo: str, day: str | None = None) -> float:
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS usd FROM agent_spend_days WHERE repo = ? AND day = ?",
                       (repo, day or today())).fetchone()
    return round(float(row["usd"]), 6)


def record(conn: sqlite3.Connection, *, session_id: str, agent: str, repo: str, part: str, spend: Spend,
           source: str | None = None, prices: dict | None = None, day: str | None = None) -> SessionSpend:
    """Store one slice of a session's spend (a running total: re-recording it
    replaces it). What the session's total moved by is added to today."""
    if spend.reported_usd is not None:
        cost, unpriced, source = spend.reported_usd, [], source or REPORTED
    else:
        cost, unpriced = estimate(spend, prices if prices is not None else load_prices(conn))
        source = source or ESTIMATE
    before = session_spend(conn, session_id).usd
    conn.execute(
        """INSERT INTO agent_spend (session_id, part, agent, repo, model, source, cost_usd, tokens, unpriced)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (session_id, part) DO UPDATE SET agent = excluded.agent, repo = excluded.repo,
               model = excluded.model, source = excluded.source, cost_usd = excluded.cost_usd,
               tokens = excluded.tokens, unpriced = excluded.unpriced, updated_at = datetime('now')""",
        (session_id, part, agent, repo, spend.model, source, round(cost, 6), spend.total().total,
         ",".join(unpriced)),
    )
    after = session_spend(conn, session_id)
    moved = round(after.usd - before, 6)
    if moved:
        key = (repo, day or today(), session_id)
        conn.execute("INSERT OR IGNORE INTO agent_spend_days (repo, day, session_id) VALUES (?, ?, ?)", key)
        conn.execute("UPDATE agent_spend_days SET cost_usd = MAX(0, cost_usd + ?) "
                     "WHERE repo = ? AND day = ? AND session_id = ?", (moved, *key))
    return after


def observe(conn: sqlite3.Connection, event: dict, repo: str) -> SessionSpend | None:
    """Read the usage in the transcript a hook event names, if this agent's has any."""
    agent = str(event.get("_agent") or "claude-code")
    spend = usage_from_transcript(agent, event.get("transcript_path"))
    session = str(event.get("session_id") or "")
    if spend is None or not session or not spend.tokens:
        return None
    return record(conn, session_id=session, agent=agent, repo=repo, part="transcript", spend=spend)


# --- caps -------------------------------------------------------------------------

@dataclass(frozen=True)
class Limits:
    session_usd: float | None = None
    day_usd: float | None = None
    warn_at: float = 0.8

    @property
    def any(self) -> bool:
        return self.session_usd is not None or self.day_usd is not None


@dataclass(frozen=True)
class Status:
    session_usd: float
    day_usd: float
    limits: Limits
    state: str = "ok"           # ok | warn | cap
    scope: str = ""             # session | day
    scope_key: str = ""
    spent: float = 0.0
    cap: float | None = None
    resumed: bool = False

    @property
    def blocked(self) -> bool:
        return self.state == "cap" and not self.resumed

    @property
    def where(self) -> str:
        return "this session's" if self.scope == "session" else "today's"


def _marked(conn: sqlite3.Connection, scope: str, mark: str) -> bool:
    return conn.execute("SELECT 1 FROM agent_budget_marks WHERE scope = ? AND mark = ?", (scope, mark)).fetchone() \
        is not None


def mark_once(conn: sqlite3.Connection, scope: str, mark: str, actor_id: str = "system:coding-gate") -> bool:
    """True the first time ``mark`` is set on ``scope``."""
    cur = conn.execute("INSERT OR IGNORE INTO agent_budget_marks (scope, mark, actor_id) VALUES (?, ?, ?)",
                       (scope, mark, actor_id))
    return cur.rowcount == 1


def check(conn: sqlite3.Connection, session_id: str, repo: str, limits: Limits, day: str | None = None) -> Status:
    day = day or today()
    s, d = session_spend(conn, session_id).usd, day_spend(conn, repo, day)
    best = Status(s, d, limits)
    rank = {"ok": 0, "warn": 1, "cap": 2}
    for scope, key, spent, cap in (("session", f"session:{session_id}", s, limits.session_usd),
                                   ("day", f"day:{repo}:{day}", d, limits.day_usd)):
        if cap is None:
            continue
        resumed = _marked(conn, key, "resumed")
        state = "cap" if spent >= cap else "warn" if spent >= cap * limits.warn_at else "ok"
        if resumed and state == "cap":
            continue  # a person lifted this cap for the rest of the session / day
        if rank[state] > rank[best.state]:
            best = Status(s, d, limits, state, scope, key, spent, cap, resumed)
    return best


def usd(value: float | None) -> str:
    return "-" if value is None else f"${value:,.2f}"


@dataclass(frozen=True)
class Notice:
    kind: str     # warn | cap
    text: str


def notice(conn: sqlite3.Connection, status: Status) -> Notice | None:
    """What to tell the agent the first time it crosses the warn line or the cap."""
    if status.state == "ok" or not mark_once(conn, status.scope_key, f"{status.state}@{status.cap}"):
        return None
    share = int(round(100 * status.spent / status.cap)) if status.cap else 0
    if status.state == "warn":
        return Notice("warn", f"Solo License: spend is {usd(status.spent)} of {status.where} {usd(status.cap)} "
                              f"budget ({share}%). Be concise: finish the current step, start nothing new, "
                              "and wrap up soon.")
    return Notice("cap", cap_text(status))


def deny_reason(status: Status) -> str:
    return (f"Budget reached: {usd(status.spent)} of {status.where} {usd(status.cap)} cap. Only reading is allowed "
            "until a person raises the cap or resumes in the Solo License dashboard.")


def cap_text(status: Status) -> str:
    return (f"Solo License: {status.where} budget of {usd(status.cap)} is used up ({usd(status.spent)}). "
            "Actions other than reading files will be refused. Summarise what you did and what is left, then stop.")


def stop_text(status: Status) -> str:
    return (f"Solo License: budget reached ({usd(status.spent)} of {status.where} {usd(status.cap)} cap). Do not "
            "start new work. Reply with a short summary: what you changed, what is verified, and what is left "
            "for a person to do.")


def resume(conn: sqlite3.Connection, repo: str, session_id: str | None, actor_id: str,
           day: str | None = None) -> list[str]:
    """A person lifts the cap for a session and/or for the repo today."""
    scopes = [f"day:{repo}:{day or today()}"] + ([f"session:{session_id}"] if session_id else [])
    return [s for s in scopes if mark_once(conn, s, "resumed", actor_id)]


# --- what the dashboard shows ----------------------------------------------------------

def payload(conn: sqlite3.Connection, repos: list[dict], limits_for, labels: dict[str, str]) -> dict:
    """Spend and caps per repo, recent sessions, and each agent's spend source."""
    day = today()
    out_repos = []
    for r in repos:
        limits: Limits = limits_for(r)
        out_repos.append({"repo": r["repo"], "day": day, "day_usd": day_spend(conn, r["repo"], day),
                          "limits": {"session_usd": limits.session_usd, "day_usd": limits.day_usd,
                                     "warn_at": limits.warn_at},
                          "resumed_today": _marked(conn, f"day:{r['repo']}:{day}", "resumed")})
    limits_by_repo = {r["repo"]: limits_for(r) for r in repos}
    sessions = []
    for row in conn.execute("SELECT session_id, MAX(updated_at) AS at FROM agent_spend GROUP BY session_id "
                            "ORDER BY at DESC LIMIT 10"):
        s = session_spend(conn, row["session_id"])
        st = check(conn, s.session_id, s.repo, limits_by_repo.get(s.repo, Limits()), day)
        sessions.append({"session_id": s.session_id, "agent": s.agent, "repo": s.repo, "usd": s.usd,
                         "source": s.source, "tokens": s.tokens, "model": s.model, "unpriced": list(s.unpriced),
                         "updated_at": s.updated_at, "state": st.state, "blocked": st.blocked, "scope": st.scope})
    seen = {r["agent"]: r["n"] for r in conn.execute(
        "SELECT agent, COUNT(*) AS n FROM agent_decisions GROUP BY agent")}
    spending = {r["agent"] for r in conn.execute("SELECT DISTINCT agent FROM agent_spend")}
    agents = []
    for agent in sorted(set(seen) | spending):
        kind, how = source_of(agent)
        label = labels.get(agent, agent)
        agents.append({"agent": agent, "label": label, "source": kind if agent in spending else UNKNOWN,
                       "how": how if kind != UNKNOWN else f"not reported by {label}",
                       "tool_calls": seen.get(agent, 0)})
    return {"day": day, "repos": out_repos, "sessions": sessions, "agents": agents,
            "prices_overridden": sorted(load_prices(conn))}
