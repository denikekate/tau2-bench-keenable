"""Aggregate web_support benchmark results across arms.

Reads data/simulations/web_support/<run>_<arm>_<tier>/results.json for each
arm and prints a comparison table (success with Wilson 95% CI, split by
evergreen / changed-since-2025 tasks, searches per conversation, search
latency p50/p95, search cost per conversation, LLM cost per conversation)
and writes <run>_<tier>_summary.{json,md} next to the results.

Usage:  uv run python scripts/web_support/aggregate.py <run_name> [--tier fast] [--arms keenable tavily exa none]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = ROOT / "data" / "simulations" / "web_support"
SPLITS = json.loads((ROOT / "data/tau2/domains/web_support/split_tasks.json").read_text())
TASK_SPLIT = {t: "changed" for t in SPLITS["changed"]} | {t: "evergreen" for t in SPLITS["evergreen"]}

TIMING_RE = re.compile(r"\[Timing: api=(\d+)ms, provider=([^/]+)/([^,]+), cost=\$([0-9.]+)\]")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def percentile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    idx = (len(xs) - 1) * q
    lo, hi = math.floor(idx), math.ceil(idx)
    return xs[lo] + (xs[hi] - xs[lo]) * (idx - lo)


def load_arm(run: str, arm: str, tier: str) -> list[dict]:
    p = SIM_DIR / f"{run}_{arm}_{tier}" / "results.json"
    if not p.exists():
        return []
    return json.loads(p.read_text())["simulations"]


def summarise(sims: list[dict]) -> dict:
    sims = [s for s in sims if s.get("termination_reason") != "infrastructure_error"]
    n = len(sims)
    rewards = [float(s["reward_info"]["reward"]) for s in sims]
    k = int(round(sum(rewards)))
    by_split: dict[str, list[float]] = {"evergreen": [], "changed": []}
    comm_pass = []
    searches, latencies, search_cost, llm_cost, durations, errors = [], [], [], [], [], 0
    per_task: dict[str, list[float]] = {}
    for s, r in zip(sims, rewards):
        by_split.setdefault(TASK_SPLIT.get(s["task_id"], "evergreen"), []).append(r)
        per_task.setdefault(s["task_id"], []).append(r)
        cc = s["reward_info"].get("communicate_checks") or []
        if cc:
            comm_pass.append(1.0 if all(c["met"] for c in cc) else 0.0)
        n_search, cost_sum = 0, 0.0
        for m in s["messages"]:
            if m["role"] == "assistant" and m.get("tool_calls"):
                n_search += sum(1 for t in m["tool_calls"] if t["name"] == "web_search")
            if m["role"] == "tool":
                mt = TIMING_RE.search(str(m.get("content") or ""))
                if mt:
                    latencies.append(int(mt.group(1)))
                    cost_sum += float(mt.group(4))
                if "Search failed" in str(m.get("content") or ""):
                    errors += 1
        searches.append(n_search)
        search_cost.append(cost_sum)
        llm_cost.append((s.get("agent_cost") or 0.0) + (s.get("user_cost") or 0.0))
        durations.append(s.get("duration") or 0.0)
    lo, hi = wilson(k, n)
    out = {
        "n": n,
        "success": k / n if n else None,
        "success_ci95": [lo, hi],
        "success_evergreen": (statistics.mean(by_split["evergreen"]) if by_split["evergreen"] else None),
        "n_evergreen": len(by_split["evergreen"]),
        "success_changed": (statistics.mean(by_split["changed"]) if by_split["changed"] else None),
        "n_changed": len(by_split["changed"]),
        "communicate_pass": statistics.mean(comm_pass) if comm_pass else None,
        "searches_per_conv": statistics.mean(searches) if searches else 0.0,
        "search_calls": len(latencies),
        "search_errors": errors,
        "latency_p50_ms": percentile(latencies, 0.5),
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_mean_ms": statistics.mean(latencies) if latencies else None,
        "search_cost_per_conv": statistics.mean(search_cost) if search_cost else 0.0,
        "llm_cost_per_conv": statistics.mean(llm_cost) if llm_cost else None,
        "duration_s_mean": statistics.mean(durations) if durations else None,
        "per_task": {t: statistics.mean(v) for t, v in sorted(per_task.items())},
    }
    return out


def fmt(v, kind: str) -> str:
    if v is None:
        return "-"
    if kind == "pct":
        return pct(v)
    if kind == "ms":
        return f"{v:.0f}"
    if kind == "usd4":
        return f"${v:.4f}"
    if kind == "usd3":
        return f"${v:.3f}"
    if kind == "f1":
        return f"{v:.1f}"
    return str(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--tier", default="fast")
    ap.add_argument("--arms", nargs="*", default=["keenable", "tavily", "exa", "none"])
    args = ap.parse_args()

    summary = {}
    for arm in args.arms:
        sims = load_arm(args.run, arm, args.tier)
        if not sims:
            print(f"(no results for arm {arm})")
            continue
        summary[arm] = summarise(sims)

    cols = [
        ("Success (all 20)", lambda s: f"{pct(s['success'])} [{pct(s['success_ci95'][0])}-{pct(s['success_ci95'][1])}]"),
        ("Evergreen", lambda s: fmt(s["success_evergreen"], "pct")),
        ("Changed since 2025", lambda s: fmt(s["success_changed"], "pct")),
        ("Exact-figure check", lambda s: fmt(s["communicate_pass"], "pct")),
        ("Searches / conv", lambda s: fmt(s["searches_per_conv"], "f1")),
        ("Search p50 ms", lambda s: fmt(s["latency_p50_ms"], "ms")),
        ("Search p95 ms", lambda s: fmt(s["latency_p95_ms"], "ms")),
        ("Search errors", lambda s: str(s["search_errors"])),
        ("Search $ / conv", lambda s: fmt(s["search_cost_per_conv"], "usd4")),
        ("LLM $ / conv", lambda s: fmt(s["llm_cost_per_conv"], "usd3")),
        ("Conv seconds", lambda s: fmt(s["duration_s_mean"], "f1")),
        ("n", lambda s: str(s["n"])),
    ]
    arms = list(summary)
    lines = ["| Metric | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for name, f in cols:
        lines.append(f"| {name} | " + " | ".join(f(summary[a]) for a in arms) + " |")
    md = "\n".join(lines)

    # per-task matrix
    tasks = sorted({t for a in arms for t in summary[a]["per_task"]})
    tl = ["", "| Task | split | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
    for t in tasks:
        tl.append(
            f"| {t} | {TASK_SPLIT.get(t, '?')} | "
            + " | ".join(fmt(summary[a]["per_task"].get(t), "pct") for a in arms)
            + " |"
        )
    md += "\n".join(tl)
    print(md)
    out = SIM_DIR / f"{args.run}_{args.tier}_summary"
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    out.with_suffix(".md").write_text(md + "\n")
    print(f"\nwrote {out}.json and .md")


if __name__ == "__main__":
    main()
