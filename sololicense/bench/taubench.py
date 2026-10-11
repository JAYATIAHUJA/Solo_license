"""Replay τ-bench retail trajectories through different autonomy policies.

τ-bench (Sierra Research, MIT licence, https://github.com/sierra-research/tau-bench)
is a standard benchmark for customer-service agents: an LLM agent talks to a
simulated customer and changes a retail database (cancel, modify, return,
exchange). The repository ships *recorded* trajectories of frontier models,
each scored by comparing the final database with the expected one.

We replay every database write those agents made and ask one question per
write: **who would have let it through?** Five policies are compared:

* ``full_auto``      - the agent acts alone (how the trajectories were recorded);
* ``approve_all``    - a person approves every write;
* ``fixed_ladder``   - autonomy after N reviewed-correct writes in a row
                       (Solo License v1), demoted when an audit finds a mistake;
* ``guards_only``    - the agent acts alone, but policy guards hold suspicious
                       writes for a person (AgentSpec-style runtime rules);
* ``solo_license``   - per-job-type licence earned from verified evidence with
                       :mod:`sololicense.domain.trust` (Bayesian, break-even from
                       the economics), plus the same guards and audits.

Labels come from the benchmark itself: a write is *correct* when its episode
reached the expected database, or when it matches a write in the reference
solution. A write the tool rejected ("Error: …") changed nothing and is skipped.

The replay is counterfactual per write: a held write does not change the rest of
the recorded conversation. Reviewers and auditors are assumed to judge a write
correctly (``reviewer_miss_rate`` relaxes that).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import comb
from pathlib import Path
from typing import Iterable

from sololicense.domain.trust import TrustPolicy, failure_upper_bound

TAU_BENCH_COMMIT = "59a200c6d575d595120f1cb70fea53cef0632f6b"
_RAW = f"https://raw.githubusercontent.com/sierra-research/tau-bench/{TAU_BENCH_COMMIT}"
FILES = {
    "orders.json": f"{_RAW}/tau_bench/envs/retail/data/orders.json",
    "gpt-4o-retail.json": f"{_RAW}/historical_trajectories/gpt-4o-retail.json",
    "sonnet-35-new-retail.json": f"{_RAW}/historical_trajectories/sonnet-35-new-retail.json",
}
MODELS = {
    "gpt-4o-retail.json": "GPT-4o",
    "sonnet-35-new-retail.json": "Claude 3.5 Sonnet (new)",
}

# Tools that change the database. Everything else is a read.
WRITE_TOOLS = (
    "cancel_pending_order",
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
    "modify_user_address",
)
# Policy: "Exchange or modify order tools can only be called once."
_ONE_SHOT = {"modify_pending_order_items", "exchange_delivered_order_items"}
# Policy: consequential actions need an explicit "yes" from the user.
_CONFIRM_RE = re.compile(
    r"\b(yes|yeah|yep|confirm(?:ed)?|correct|go ahead|proceed|please do|sure)\b", re.I
)


# --- data -------------------------------------------------------------------


def fetch(data_dir: Path) -> dict[str, Path]:
    """Download the pinned τ-bench files once; later calls reuse the cache."""
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, url in FILES.items():
        path = data_dir / name
        if not path.exists():
            tmp = path.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=120) as response, open(tmp, "wb") as out:
                out.write(response.read())
            tmp.replace(path)
        paths[name] = path
    return paths


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Write:
    """One database write an agent actually made."""

    tool: str
    correct: bool
    guards: tuple[str, ...]  # names of policy guards that fired (empty = clean)


@dataclass(frozen=True)
class Episode:
    task_id: int
    trial: int
    reward: float
    writes: tuple[Write, ...] = field(default_factory=tuple)


def _arguments(call: dict) -> dict:
    raw = call["function"]["arguments"]
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


def _normalise(tool: str, kwargs: dict) -> str:
    """Canonical form so equivalent argument orders compare equal."""
    kw = dict(kwargs)
    if "new_item_ids" in kw and "item_ids" in kw:
        pairs = sorted(zip(map(str, kw["item_ids"]), map(str, kw["new_item_ids"])))
        kw["item_ids"] = [p[0] for p in pairs]
        kw["new_item_ids"] = [p[1] for p in pairs]
    elif "item_ids" in kw:
        kw["item_ids"] = sorted(map(str, kw["item_ids"]))
    return tool + json.dumps(kw, sort_keys=True)


def parse_episode(raw: dict, orders: dict) -> Episode:
    """Extract every executed write with its label and the guards that fire."""
    task = raw["info"]["task"]
    gold = {_normalise(a["name"], a["kwargs"]) for a in task["actions"] if a["name"] in WRITE_TOOLS}
    traj = raw["traj"]
    responses = {m.get("tool_call_id"): str(m.get("content") or "") for m in traj if m["role"] == "tool"}

    authenticated: str | None = None
    seen = ""          # everything tools have shown the agent so far
    last_user = ""
    calls: Counter = Counter()
    writes: list[Write] = []
    for message in traj:
        role = message["role"]
        if role == "user":
            last_user = str(message.get("content") or "")
        elif role == "tool":
            content = str(message.get("content") or "")
            seen += "\n" + content
            if str(message.get("name", "")).startswith("find_user_id") and not content.startswith("Error"):
                authenticated = content.strip()
        if role != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            tool = call["function"]["name"]
            if tool not in WRITE_TOOLS:
                continue
            kwargs = _arguments(call)
            if responses.get(call.get("id"), "").startswith("Error"):
                continue  # the tool refused; nothing changed
            order_id = kwargs.get("order_id")
            owner = orders.get(order_id, {}).get("user_id") if order_id else kwargs.get("user_id")
            ids = [str(x) for key in ("item_ids", "new_item_ids") for x in kwargs.get(key, [])]
            fired = []
            if authenticated is None or owner != authenticated:
                fired.append("identity")
            if not _CONFIRM_RE.search(last_user):
                fired.append("confirmation")
            if not all(i in seen for i in ids) or (order_id and order_id not in seen):
                fired.append("grounding")
            if tool in _ONE_SHOT and calls[(tool, order_id)] > 0:
                fired.append("one_shot")
            calls[(tool, order_id)] += 1
            correct = raw["reward"] >= 1.0 or _normalise(tool, kwargs) in gold
            writes.append(Write(tool=tool, correct=correct, guards=tuple(fired)))
    return Episode(raw["task_id"], raw.get("trial", 0), float(raw["reward"]), tuple(writes))


def load_episodes(trajectory_path: Path, orders_path: Path) -> list[Episode]:
    orders = json.loads(orders_path.read_text(encoding="utf-8"))
    raws = json.loads(trajectory_path.read_text(encoding="utf-8"))
    return [parse_episode(raw, orders) for raw in raws]


def pass_hat_k(episodes: Iterable[Episode], k: int) -> float:
    """τ-bench's pass^k: chance that *all* k i.i.d. trials of a task succeed."""
    by_task: dict[int, list[float]] = defaultdict(list)
    for e in episodes:
        by_task[e.task_id].append(e.reward)
    scores = []
    for rewards in by_task.values():
        n, c = len(rewards), sum(r >= 1.0 for r in rewards)
        if n >= k:
            scores.append(comb(c, k) / comb(n, k))
    return sum(scores) / len(scores) if scores else 0.0


# --- policies ---------------------------------------------------------------


@dataclass(frozen=True)
class Costs:
    """Per-write costs, in dollars. Defaults mirror planning/cfo/model.py (L1 vs L2 minutes)."""

    review: float = 2.25       # 3 min of a $45/h person approving one write
    autonomous: float = 0.375  # 0.5 min of monitoring per unattended write
    incident: float = 120.0    # one wrong change reaching a customer


@dataclass
class Outcome:
    writes: int = 0
    wrong: int = 0
    harmful: int = 0          # wrong writes that reached a customer unreviewed
    caught_by_audit: int = 0  # of those, found afterwards by a sampled audit
    blocked: int = 0          # wrong writes stopped before they landed
    reviews: int = 0          # human approvals (including guard holds)
    audits: int = 0
    autonomous: int = 0       # writes executed with no human before them

    def cost(self, costs: Costs) -> float:
        return (
            (self.reviews + self.audits) * costs.review
            + self.autonomous * costs.autonomous
            + self.harmful * costs.incident
        )

    def as_dict(self, costs: Costs) -> dict:
        return {
            "writes": self.writes,
            "wrong": self.wrong,
            "harmful": self.harmful,
            "caught_by_audit": self.caught_by_audit,
            "blocked": self.blocked,
            "reviews": self.reviews,
            "audits": self.audits,
            "autonomous": self.autonomous,
            "automation_rate": round(self.autonomous / self.writes, 4) if self.writes else 0.0,
            "harm_rate": round(self.harmful / self.writes, 4) if self.writes else 0.0,
            "cost": round(self.cost(costs), 2),
        }


@dataclass
class _ClassState:
    successes: int = 0
    failures: int = 0
    streak: int = 0
    autonomous: bool = False


def simulate(
    policy: str,
    writes: list[Write],
    *,
    costs: Costs,
    confidence: float = 0.9,
    audit_rate: float = 0.1,
    fixed_n: int = 3,
    reviewer_miss_rate: float = 0.0,
    seed: int = 0,
) -> Outcome:
    """Run one policy over a stream of writes (in the given order)."""
    rng = random.Random(seed)
    trust = TrustPolicy(
        review_cost_saved=costs.review - costs.autonomous,
        incident_cost=costs.incident,
        confidence=confidence,
    )
    states: dict[str, _ClassState] = defaultdict(_ClassState)
    out = Outcome()

    def review(write: Write) -> bool:
        """A person looks at the write; returns True if a wrong write is stopped."""
        out.reviews += 1
        caught = not write.correct and rng.random() >= reviewer_miss_rate
        if caught:
            out.blocked += 1
        elif not write.correct:
            out.harmful += 1  # the reviewer missed it
        return caught

    for write in writes:
        out.writes += 1
        out.wrong += not write.correct
        state = states[write.tool]

        if policy == "full_auto":
            out.autonomous += 1
            out.harmful += not write.correct
            continue
        if policy == "approve_all":
            review(write)
            continue
        if policy == "guards_only":
            if write.guards:
                review(write)
            else:
                out.autonomous += 1
                out.harmful += not write.correct
            continue

        uses_guards = policy == "solo_license"
        if not state.autonomous or (uses_guards and write.guards):
            caught = review(write)
            if caught:
                state.failures += 1
                state.streak = 0
            else:
                state.successes += 1
                state.streak += 1
        else:
            out.autonomous += 1
            if rng.random() < audit_rate:
                out.audits += 1
                if write.correct:
                    state.successes += 1
                    state.streak += 1
                else:
                    out.harmful += 1
                    out.caught_by_audit += 1
                    state.failures += 1
                    state.streak = 0
                    state.autonomous = False  # detection: demote at once
            elif not write.correct:
                out.harmful += 1

        if policy == "fixed_ladder":
            if not state.autonomous and state.streak >= fixed_n:
                state.autonomous = True
        elif policy == "solo_license":
            state.autonomous = trust.earned(state.successes, state.failures)
        else:
            raise ValueError(f"unknown policy {policy!r}")
    return out


POLICIES = ("full_auto", "approve_all", "fixed_ladder", "guards_only", "solo_license")


def stream(episodes: list[Episode], seed: int) -> list[Write]:
    """Episodes in a random arrival order (writes keep their in-episode order)."""
    order = list(episodes)
    random.Random(seed).shuffle(order)
    return [w for e in order for w in e.writes]


def class_table(episodes: list[Episode], costs: Costs, confidence: float) -> list[dict]:
    """Measured reliability per job type - the evidence a licence is learned from."""
    trust = TrustPolicy(costs.review - costs.autonomous, costs.incident, confidence)
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for e in episodes:
        for w in e.writes:
            totals[w.tool][0] += 1
            totals[w.tool][1] += not w.correct
    rows = []
    for tool in WRITE_TOOLS:
        n, wrong = totals.get(tool, [0, 0])
        if not n:
            continue
        rows.append({
            "job_type": tool,
            "writes": n,
            "wrong": wrong,
            "error_rate": round(wrong / n, 4),
            "upper_bound": round(failure_upper_bound(n - wrong, wrong, confidence), 4),
            "break_even": round(trust.target_rate, 4),
            "earns_autonomy": trust.earned(n - wrong, wrong),
        })
    return rows
