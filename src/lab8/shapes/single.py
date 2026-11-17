"""Shape B — one ReAct agent. Student work.

Use `lab8.runtime.run_react` with max_steps=8. `decide` may pick a read tool.
It must not call `issue_refund`. After the loop, the host validates the quote
and is the only writer.

A decide() that trusts ticket text over the order row will fail hidden claims
where the customer overstates the delay or cites a superseded clause.

Per-order cap: an order may already have been refunded by an earlier claim.
The read tool `lookup_refund_history` shows how much. The host still enforces
the cap, so pass the full quote to `durability.issue_refund`, not a net amount.

Caps: stop at 8 steps. Count model calls in the Budget so cost stays comparable.

Trace contract v1 (../../docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

from functools import partial

from lab8.db import connect
from lab8.mock_llm import complete
from lab8.runtime import run_react
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import compute_compensation, get_claim_view, tool_cost
from lab8.trace import Trace


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        budget = Budget()
        trace = Trace(make_run_id("single", claim_id, seed))
        done = partial(
            finish, conn, shape="single", claim_id=claim_id, seed=seed,
            budget=budget, trace=trace,
        )
        budget.add_tool(tool_cost())
        claim = get_claim_view(conn, claim_id)
        trace.add("claim", {"found": claim["found"], "has_order": bool(claim.get("order_id"))})
        if not claim["found"]:
            return done(status="failed", proposal_amount=0, error_reason="unknown_claim")
        if not claim.get("order_id"):
            return done(status="needs_info", proposal_amount=0, error_reason="missing_order_id")

        def decide(observation):
            # MockLLM returns text; code maps the read phase to an allowed action.
            phase = observation.get("last_tool", "start")
            complete(budget, seed=seed, purpose="decide", prompt=phase)
            if phase == "start":
                trace.add("agent", {"tool": "lookup_order"})
                return {
                    "tool": "lookup_order",
                    "args": {"order_id": claim["order_id"], "principal_id": claim["principal_id"]},
                }
            trace.add("agent", {"final": True})
            return {"final": {"order_view": observation["last_result"]}}

        investigation = run_react(
            conn, budget, observation={"claim": claim}, decide=decide, max_steps=8,
            worker=True,
        )
        if investigation["stopped"] == "step_cap":
            trace.add("agent", {"stopped": "step_cap"})
            return done(status="failed", proposal_amount=0, error_reason="step_cap")
        order_view = investigation["final"]["order_view"]
        trace.add("order", {"visible": order_view["visible"], "reason": order_view["reason"]})
        if not order_view["visible"]:
            return done(status="escalated", proposal_amount=0, error_reason=order_view["reason"])
        budget.add_tool(tool_cost())
        quote = compute_compensation(conn, order_view["order"])
        return _settle_quote(
            conn, claim_id, quote, budget=budget, trace=trace,
            done=done, crash_at=crash_at,
        )
    finally:
        conn.close()


def _settle_quote(conn, claim_id, quote, *, budget, trace, done, crash_at):
    """Submit the full quote to the host, then report the actual ledger."""
    from lab8.durability import InjectedCrash, issue_refund

    proposal = int(quote["amount_vnd"])
    trace.add("quote", quote)
    if proposal <= 0:
        return done(status="denied", proposal_amount=0, error_reason=quote.get("reason"))

    budget.add_tool(tool_cost())
    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise
    trace.add("refund", {"ok": outcome["ok"], "reason": outcome["reason"]})
    status = "resolved" if outcome["ok"] else "failed" if outcome["conflict"] else "denied"
    return done(
        status=status,
        proposal_amount=proposal,
        error_reason=None if outcome["ok"] else outcome["reason"],
    )
