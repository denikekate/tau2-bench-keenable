"""Web search providers behind one interface, each timed around its own HTTP call.

Adapted from the Keenable voice "search race" demo. Providers: keenable,
tavily, exa, plus two offline ones used for smoke tests and the baseline:

    keenable    fast=realtime     standard=pro
    tavily      fast=ultra-fast   standard=basic
    exa         fast=instant      standard=auto
    mock        canned results, no network (smoke tests)
    none        no search tool at all (model-only baseline)

``search(provider, query, tier, max_results)`` returns a normalised dict:
    {provider, tier, label, api_ms, cost_usd, vendor_ms?, error?,
     results: [{title, url, source, snippet, published}]}

``api_ms`` is measured here around the vendor HTTP call only, so the agent
LLM is not included. That is the number the benchmark reports as search
latency.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

TIMEOUT_S = 15.0
DEFAULT_MAX_RESULTS = 5
SNIPPET_CHARS = 400

PROVIDERS = ["keenable", "tavily", "exa"]
TIERS = ["fast", "standard"]

# List price per query, USD, used when the vendor does not report cost in the
# response (Exa and Tavily do). Check against each pricing page before quoting.
LIST_PRICE: dict[str, dict[str, float]] = {
    "keenable": {"fast": 0.001, "standard": 0.001},  # $1 / 1K
    "tavily": {"fast": 0.008, "standard": 0.008},  # 1 credit at ~$0.008 pay-as-you-go
    "exa": {"fast": 0.004, "standard": 0.005},  # instant $4 / 1K; auto $5 / 1K
    "mock": {"fast": 0.0, "standard": 0.0},
}
LABEL: dict[str, dict[str, str]] = {
    "keenable": {"fast": "realtime", "standard": "pro"},
    "tavily": {"fast": "ultra-fast", "standard": "basic"},
    "exa": {"fast": "instant", "standard": "auto"},
    "mock": {"fast": "mock", "standard": "mock"},
}


class ProviderError(RuntimeError):
    pass


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def _row(title: str, url: str, snippet: str, published: str | None) -> dict[str, Any]:
    return {
        "title": (title or "Untitled").strip(),
        "url": url,
        "source": _domain(url),
        "snippet": (snippet or "").strip()[:SNIPPET_CHARS],
        "published": published,
    }


_CLIENT: httpx.Client | None = None
_CLIENT_PID: int | None = None


def _client() -> httpx.Client:
    """One keep-alive client per process, so TLS setup is paid once per host,
    the way a long-running voice agent would hold its connections."""
    global _CLIENT, _CLIENT_PID
    pid = os.getpid()
    if _CLIENT is None or _CLIENT_PID != pid:
        _CLIENT = httpx.Client(timeout=TIMEOUT_S, http2=False)
        _CLIENT_PID = pid
    return _CLIENT


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    r = _client().post(url, json=body, headers=headers)
    if r.status_code >= 400:
        raise ProviderError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _key(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise ProviderError(f"{name} is not set")
    return v


# ---------- vendors ----------


def _keenable(q: str, tier: str, k: int) -> dict[str, Any]:
    key = (os.environ.get("KEENABLE_API_KEY") or "").strip()
    if key:
        url, headers = "https://api.keenable.ai/v1/search", {"X-API-Key": key}
    else:  # keyless public endpoint, rate limited per IP
        url, headers = "https://api.keenable.ai/v1/search/public", {
            "X-Keenable-Title": "tau2 web_support benchmark"
        }
    j = _post(
        url,
        headers,
        {
            "query": q,
            "mode": "realtime" if tier == "fast" else "pro",
            "max_results": k,
            "snippet_max_length": SNIPPET_CHARS,
        },
    )
    return {
        "results": [
            _row(
                r.get("title"),
                r.get("url", ""),
                r.get("snippet") or r.get("description") or "",
                r.get("published_at"),
            )
            for r in j.get("results", [])
            if r.get("url")
        ]
    }


def _tavily(q: str, tier: str, k: int) -> dict[str, Any]:
    j = _post(
        "https://api.tavily.com/search",
        {"Authorization": f"Bearer {_key('TAVILY_API_KEY')}"},
        {
            "query": q,
            "search_depth": "ultra-fast" if tier == "fast" else "basic",
            "max_results": k,
            "include_usage": True,
            "include_published_date": True,
        },
    )
    credits = (j.get("usage") or {}).get("credits")
    return {
        "results": [
            _row(r.get("title"), r.get("url", ""), r.get("content") or "", r.get("published_date"))
            for r in j.get("results", [])
            if r.get("url")
        ],
        "cost_usd": credits * 0.008 if isinstance(credits, (int, float)) else None,
        "vendor_ms": round(j["response_time"] * 1000) if j.get("response_time") else None,
    }


def _exa(q: str, tier: str, k: int) -> dict[str, Any]:
    j = _post(
        "https://api.exa.ai/search",
        {"x-api-key": _key("EXA_API_KEY")},
        {
            "query": q,
            "type": "instant" if tier == "fast" else "auto",
            "numResults": k,
            "contents": {"highlights": {"maxCharacters": SNIPPET_CHARS}},
        },
    )
    cost = (j.get("costDollars") or {}).get("total")
    return {
        "results": [
            _row(
                r.get("title"),
                r.get("url", ""),
                (r.get("highlights") or [r.get("text") or ""])[0],
                r.get("publishedDate"),
            )
            for r in j.get("results", [])
            if r.get("url")
        ],
        "cost_usd": cost if isinstance(cost, (int, float)) else None,
        "vendor_ms": round(j["searchTime"]) if j.get("searchTime") else None,
    }


def _mock(q: str, tier: str, k: int) -> dict[str, Any]:
    """Offline provider for smoke tests: echoes the query as a fake result."""
    time.sleep(0.05)
    return {
        "results": [
            _row(
                f"Mock result for: {q}",
                "https://example.com/mock",
                "This is a mock search result. No real information here.",
                None,
            )
        ]
    }


_IMPL: dict[str, Callable[[str, str, int], dict[str, Any]]] = {
    "keenable": _keenable,
    "tavily": _tavily,
    "exa": _exa,
    "mock": _mock,
}


# ---------- public API ----------


def search(
    provider: str,
    query: str,
    tier: str = "fast",
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict[str, Any]:
    """Run one provider and time it. Never raises; errors land in ``error``."""
    tier = "standard" if tier == "standard" else "fast"
    base = {"provider": provider, "tier": tier, "results": []}
    if provider not in _IMPL:
        return {**base, "label": provider, "api_ms": 0, "error": f"unknown provider '{provider}'"}
    base["label"] = LABEL[provider][tier]
    k = max(1, min(int(max_results or DEFAULT_MAX_RESULTS), 10))
    t0 = time.perf_counter()
    try:
        out = _IMPL[provider](query, tier, k)
    except httpx.TimeoutException:
        return {
            **base,
            "api_ms": round((time.perf_counter() - t0) * 1000),
            "cost_usd": 0.0,
            "error": f"timeout after {TIMEOUT_S:.0f}s",
        }
    except Exception as e:  # ProviderError, network, JSON
        return {
            **base,
            "api_ms": round((time.perf_counter() - t0) * 1000),
            "cost_usd": 0.0,
            "error": str(e)[:300],
        }
    api_ms = round((time.perf_counter() - t0) * 1000)
    cost = out.get("cost_usd")
    return {
        **base,
        "api_ms": api_ms,
        "vendor_ms": out.get("vendor_ms"),
        "cost_usd": cost if isinstance(cost, (int, float)) else LIST_PRICE[provider][tier],
        "results": out["results"][:k],
    }


def probe_overhead(n: int = 5) -> dict[str, int]:
    """Median round-trip (ms) of a trivial keep-alive GET to each vendor host.

    This is the network floor from the machine running the benchmark (TLS is
    reused after the first request). Search latency minus this floor is the
    vendor's own search time plus one proxy hop; report both.
    """
    import statistics

    hosts = {
        "keenable": "https://api.keenable.ai/",
        "tavily": "https://api.tavily.com/",
        "exa": "https://api.exa.ai/",
    }
    out: dict[str, int] = {}
    for name, url in hosts.items():
        samples = []
        for _ in range(n + 1):  # first request pays TLS; drop it
            t0 = time.perf_counter()
            try:
                _client().get(url)
            except Exception:
                pass
            samples.append(round((time.perf_counter() - t0) * 1000))
        out[name] = int(statistics.median(samples[1:]))
    return out
