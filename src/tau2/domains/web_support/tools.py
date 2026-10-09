"""Agent tools for the web_support domain.

Two toolkits:

* ``WebSupportTools``: a single ``web_search`` tool backed by the provider
  named in the DB (keenable / tavily / exa / mock). Every call is timed
  around the vendor HTTP request, the timing and cost are appended to the
  tool result (so they end up in the simulation transcript) and also written
  to a JSONL log so results can be aggregated without parsing transcripts.
* ``WebSupportToolsNoSearch``: no tools at all (model-only baseline).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from loguru import logger

from tau2.domains.web_support.data_model import SearchCall, WebSupportDB
from tau2.domains.web_support.providers import DEFAULT_MAX_RESULTS, search
from tau2.environment.toolkit import ToolKitBase, ToolType, is_tool
from tau2.utils.utils import DATA_DIR

SEARCH_LOG_DIR = DATA_DIR / "tau2" / "domains" / "web_support" / "logs"


def _log_path() -> Path:
    name = os.environ.get("TAU2_WEB_SEARCH_LOG", "search_calls.jsonl")
    return SEARCH_LOG_DIR / name


def _format_results(res: dict) -> str:
    lines = []
    if res.get("error"):
        lines.append(f"Search failed: {res['error']}")
    elif not res["results"]:
        lines.append("No results found.")
    else:
        for i, r in enumerate(res["results"], 1):
            pub = f" ({r['published'][:10]})" if r.get("published") else ""
            lines.append(f"{i}. {r['title']}{pub}\n   {r['url']}\n   {r['snippet']}")
    cost = res.get("cost_usd") or 0.0
    lines.append(
        f"\n[Timing: api={res['api_ms']}ms, provider={res['provider']}/{res['label']}, "
        f"cost=${cost:.4f}]"
    )
    return "\n".join(lines)


class WebSupportToolsNoSearch(ToolKitBase):
    """Baseline toolkit: the agent has no tools and must answer from memory."""

    db: WebSupportDB

    def __init__(self, db: WebSupportDB) -> None:
        super().__init__(db)


class WebSupportTools(ToolKitBase):
    """Toolkit with one live web search tool."""

    db: WebSupportDB

    def __init__(self, db: WebSupportDB) -> None:
        super().__init__(db)
        SEARCH_LOG_DIR.mkdir(parents=True, exist_ok=True)

    @is_tool(ToolType.READ)
    def web_search(self, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
        """
        Search the live web and return the top results with a short snippet each.

        Use this to look up current facts (prices, fees, allowances, policies,
        deadlines) on official company or government pages before answering.
        Results are ranked by relevance; each has a title, URL and snippet.

        Args:
            query: A concise search query, e.g. "Ryanair small bag size 2026".
            max_results: Number of results to return (1-10, default 5).

        Returns:
            A numbered list of results, each with title, URL and snippet.
        """
        res = search(self.db.provider, query, self.db.tier, max_results)
        call = SearchCall(
            provider=res["provider"],
            tier=res["tier"],
            query=query,
            max_results=int(max_results),
            api_ms=int(res["api_ms"]),
            cost_usd=float(res.get("cost_usd") or 0.0),
            vendor_ms=res.get("vendor_ms"),
            n_results=len(res["results"]),
            error=res.get("error"),
        )
        self.db.search_calls.append(call)
        try:
            with open(_log_path(), "a") as fp:
                fp.write(
                    json.dumps(
                        {
                            **call.model_dump(),
                            "ts": time.time(),
                            "pid": os.getpid(),
                            "task_id": os.environ.get("TAU2_CURRENT_TASK_ID"),
                        }
                    )
                    + "\n"
                )
        except Exception as e:  # logging must never break a simulation
            logger.warning(f"web_search log write failed: {e}")
        if call.error:
            logger.warning(f"web_search error ({call.provider}): {call.error}")
        return _format_results(res)
