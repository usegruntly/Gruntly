"""Put what a run's model calls used into its record: tokens by kind, and the dollars, or the reason there are none.

For a child on a hosted provider the numbers come from the proxy's meter (every response it carried, read from the provider's own
`usage`), so they hold for any child harness without that harness reporting anything. A local child costs no API dollars. A hosted
child whose price is unknown reports tokens and `cost_unknown`: a total built from it is a lower bound and says so.
"""
from __future__ import annotations

from pathlib import Path

from . import pricing
from .usage import Usage


def finalize_child_usage(st, provider: str, model: str | None, snapshot: dict, root: Path | None = None) -> dict:
    """Merge the proxy meter's snapshot into `child_usage.json` (adding to any earlier round of the same run) and return what was written."""
    cu = st.read_json("child_usage.json", {})
    total = Usage.from_dict((cu.get("proxy") or {}).get("usage"))
    total.add(Usage.from_dict(snapshot))
    cost = pricing.cost(total, provider, model, "hosted", root)
    cu["proxy"] = {"usage": total.to_dict(), "cost_usd": cost.usd, "cost_source": cost.source, "cost_detail": cost.detail}
    if total.seen and not cu.get("tokens"):
        cu["tokens"] = total.total
    if total.requests and not cu.get("requests"):
        cu["requests"] = total.requests
    if cost.usd is not None:
        cu["cost_usd"] = round(cost.usd, 5)
        cu.pop("cost_unknown", None)
    elif total.requests:
        cu["cost_unknown"] = True
    cu["cost_source"] = cost.source
    st.write_json("child_usage.json", cu)
    return cu
