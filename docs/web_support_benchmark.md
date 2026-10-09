# web_support: live web search benchmark (Keenable vs Tavily vs Exa)

A tau2-bench domain that keeps the harness fixed (same agent LLM, same user
simulator, same tasks, same judge) and swaps only the search API the agent
calls. It measures what a customer-support or voice agent actually gets from a
search provider: did the customer get the right figure, how many searches did
it take, how long did each search take, and what did it cost.

## Why a new domain

tau2's only retrieval domain, `banking_knowledge`, runs over a private,
fictional knowledge base. Tavily, Exa and Keenable search the public web, so
they cannot be dropped into it. `web_support` instead uses tasks whose answers
live on real public pages (airline bag rules, bank fees, government fees,
return windows, subscription prices).

## Design

- Agent policy: "AnswerLine", a voice helpdesk that must look facts up with
  `web_search` and read back the specific figure. Voice-grade settings: 5
  results, 400-character snippets, fast tiers (Keenable realtime, Tavily
  ultra-fast, Exa instant). `TAU2_WEB_SEARCH_TIER=standard` switches to
  Keenable pro / Tavily basic / Exa auto.
- Arms: `web_support_keenable`, `web_support_tavily`, `web_support_exa`,
  `web_support_none` (no tool, model memory only), `web_support_mock`
  (offline, for smoke tests).
- 20 tasks, verified on 2026-10-09 against official pages
  (`data/tau2/domains/web_support/facts/*.json`): 10 **evergreen** facts and
  10 **changed since 2025** facts (FSCS limit, passport fee, stamp price,
  Congestion Charge, TV licence, Delta bag fee, Wise ATM terms, Costco UK,
  Netflix UK, Ryanair bag size). The second half is where memorised answers
  are stale, so it is where search quality shows.
- Scoring: an LLM judge checks one natural-language assertion per task (the
  current figure, not the old one); reward basis `NL_ASSERTION`. A substring
  check on the exact figure (`communicate_info`) is reported as a diagnostic.
- Each `web_search` result carries `[Timing: api=NNNms, provider=..., cost=$...]`
  so latency and cost are in the transcript; calls are also logged to
  `data/tau2/domains/web_support/logs/*.jsonl`.

## Run

```bash
cp .env.example .env   # add KEENABLE_API_KEY, TAVILY_API_KEY, EXA_API_KEY, ANTHROPIC_API_KEY
uv sync && uv pip install "websockets>=13.0"
scripts/web_support/run_benchmark.sh myrun 3 keenable tavily exa none
# -> prints the comparison table, writes data/simulations/web_support/myrun_fast_summary.{md,json}
```

Defaults: agent `anthropic/claude-sonnet-5-5`, user simulator
`anthropic/claude-haiku-5-5`, judge `anthropic/claude-sonnet-5-5`; override
with `AGENT_LLM`, `USER_LLM`, `JUDGE_LLM`. About 2 to 6 cents per conversation.

To re-verify facts and rebuild tasks: edit the facts files, then
`uv run python scripts/web_support/build_tasks.py`.

## Caveats

- Latency is measured from the machine running the benchmark; a keep-alive
  client is used so TLS is paid once. Subtract the network floor
  (`providers.probe_overhead()`) to compare with vendors' own numbers.
- 20 tasks x 3 trials gives roughly +/-15 points on success; only large gaps
  are significant. Latency and cost stabilise much faster.
- Facts drift. `description.notes` on each task records the verification
  date and the previous value; re-verify before quoting results.
