"""web_support domain: a consumer helpdesk agent that answers questions needing
live public-web facts, with the search backend swapped per run.

Registered domain names (all share one task set):

    web_support_keenable   web_search backed by Keenable
    web_support_tavily     web_search backed by Tavily
    web_support_exa        web_search backed by Exa
    web_support_mock       offline canned provider (smoke tests)
    web_support_none       no search tool (model-only baseline)

Tier (fast | standard) is read from the ``TAU2_WEB_SEARCH_TIER`` environment
variable, default ``fast`` (Keenable realtime, Tavily ultra-fast, Exa instant),
which is the voice-grade comparison.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from tau2.data_model.tasks import Task
from tau2.domains.web_support.data_model import WebSupportDB
from tau2.domains.web_support.tools import WebSupportTools, WebSupportToolsNoSearch
from tau2.environment.environment import Environment
from tau2.utils import load_file
from tau2.utils.utils import DATA_DIR

WEB_SUPPORT_DATA_DIR = DATA_DIR / "tau2" / "domains" / "web_support"
WEB_SUPPORT_DB_PATH = WEB_SUPPORT_DATA_DIR / "db.json"
WEB_SUPPORT_POLICY_PATH = WEB_SUPPORT_DATA_DIR / "policy.md"
WEB_SUPPORT_POLICY_NO_SEARCH_PATH = WEB_SUPPORT_DATA_DIR / "policy_no_search.md"
WEB_SUPPORT_TASK_SET_PATH = WEB_SUPPORT_DATA_DIR / "tasks.json"

SEARCH_PROVIDERS = ("keenable", "tavily", "exa", "mock")


def get_tier() -> str:
    tier = (os.environ.get("TAU2_WEB_SEARCH_TIER") or "fast").strip().lower()
    return "standard" if tier == "standard" else "fast"


def _make_get_environment(provider: str):
    def get_environment(
        db: Optional[WebSupportDB] = None,
        solo_mode: bool = False,
    ) -> Environment:
        if solo_mode:
            raise ValueError("solo_mode is not supported for web_support")
        if db is None:
            db = WebSupportDB.load(WEB_SUPPORT_DB_PATH)
        db.provider = provider
        db.tier = get_tier()
        if provider == "none":
            tools = WebSupportToolsNoSearch(db)
            policy_path: Path = WEB_SUPPORT_POLICY_NO_SEARCH_PATH
        elif provider in SEARCH_PROVIDERS:
            tools = WebSupportTools(db)
            policy_path = WEB_SUPPORT_POLICY_PATH
        else:
            raise ValueError(f"Unknown web_support provider: {provider}")
        with open(policy_path, "r") as fp:
            policy = fp.read()
        return Environment(
            domain_name=f"web_support_{provider}",
            policy=policy,
            tools=tools,
            user_tools=None,
        )

    get_environment.__name__ = f"get_environment_{provider}"
    return get_environment


get_environment_keenable = _make_get_environment("keenable")
get_environment_tavily = _make_get_environment("tavily")
get_environment_exa = _make_get_environment("exa")
get_environment_mock = _make_get_environment("mock")
get_environment_none = _make_get_environment("none")


def get_tasks(task_split_name: Optional[str] = None) -> list[Task]:
    tasks = load_file(WEB_SUPPORT_TASK_SET_PATH)
    tasks = [Task.model_validate(task) for task in tasks]
    if task_split_name is None:
        return tasks
    splits = get_tasks_split()
    if task_split_name not in splits:
        raise ValueError(
            f"Invalid task split name: {task_split_name}. Valid splits: {list(splits)}"
        )
    return [t for t in tasks if t.id in splits[task_split_name]]


def get_tasks_split() -> dict[str, list[str]]:
    """Splits: ``evergreen`` (facts stable for years) and ``changed`` (facts
    that changed since 2025, where memorised answers are stale)."""
    return load_file(WEB_SUPPORT_DATA_DIR / "split_tasks.json")
