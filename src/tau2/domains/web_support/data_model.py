from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from tau2.environment.db import DB


class SearchCall(BaseModel):
    """One web_search call made by the agent during a simulation."""

    provider: str
    tier: str
    query: str
    max_results: int
    api_ms: int
    cost_usd: float
    vendor_ms: Optional[int] = None
    n_results: int
    error: Optional[str] = None


class WebSupportDB(DB):
    """State for the web_support domain.

    The domain has no transactional state; the DB only records the search
    calls made during a simulation so that they are serialised with the
    results and can be aggregated afterwards.
    """

    provider: str = Field(description="Search provider name for this environment")
    tier: str = Field(default="fast", description="Provider tier: fast or standard")
    search_calls: List[SearchCall] = Field(default_factory=list)
    # Reserved for future use (per-task hidden context); keeps the file non-empty.
    meta: Dict[str, str] = Field(default_factory=dict)
