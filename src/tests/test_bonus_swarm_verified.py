"""B3: handwritten labels, verifier repairs, safety and crash recovery."""

import json
from pathlib import Path

import pytest

from bonus.swarm_verified import run_claim, verify_quote
from lab8.db import connect, init_store, load_json, load_jsonl
from lab8.durability import InjectedCrash
from lab8.metrics import trial_pass
from lab8.schemas import Budget
from lab8.tools import compute_compensation, lookup_order, tool_cost
from lab8.trace import Trace

BONUS = Path(__file__).resolve().parents[1] / "bonus"
WORLD = load_json(BONUS / "world.json")
CASES = load_jsonl(BONUS / "cases.jsonl")


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
@pytest.mark.parametrize("claim", CASES, ids=lambda c: c["scenario"])
def test_handwritten_cases(tmp_path, monkeypatch, claim, seed):
    monkeypatch.chdir(tmp_path)
    store = tmp_path / "case.sqlite"
    init_store(store, WORLD, CASES).close()
    result = run_claim(claim["claim_id"], seed=seed, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(result.as_dict(), claim["expected"], conn)
    finally:
        conn.close()
    assert passed, reason
    events = load_json(result.trace_path)["events"]
    assert sum(e["kind"] == "verifier_override" for e in events) <= 1


@pytest.mark.parametrize("field,value", [
    ("delay_days", 0), ("status", "cancelled"), ("damage_verified", True),
    ("shipping_fee_vnd", 999999), ("paid_vnd", 1),
])
def test_repairs_each_quote_fact_once(public_db, field, value):
    conn = connect(public_db)
    try:
        structured = lookup_order(conn, "O-107", "P-100")["order"]
        candidate = {**structured, field: value}
        budget, trace = Budget(), Trace("verifier-unit")
        corrected = verify_quote(
            conn, candidate, structured, compute_compensation(conn, candidate),
            budget=budget, trace=trace,
        )
        assert corrected == compute_compensation(conn, structured)
        assert trace.events == [{"kind": "verifier_override", "payload": {
            "fields": [field], "repair_round": 1,
        }}]
        assert budget.tool_calls == 1
        assert budget.cost_estimate == tool_cost()
        # Already correct facts cause no further quote/tool call.
        assert verify_quote(conn, structured, structured, corrected,
                            budget=budget, trace=trace) is corrected
        assert budget.tool_calls == 1
    finally:
        conn.close()


def test_public_seed55_override_is_safe(public_db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_claim("C-002", seed=55, store_path=str(public_db))
    assert result.status == "denied"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    assert result.model_calls == 3
    trace = load_json(result.trace_path)
    assert any(e["kind"] == "verifier_override" for e in trace["events"])
    assert "CANARY_SECRET_" not in json.dumps(trace)


def test_repaired_zero_quote_can_resume_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = tmp_path / "crash.sqlite"
    init_store(store, WORLD, CASES).close()
    # Ticket understates delay; initial quote is zero on seed 55.
    with pytest.raises(InjectedCrash):
        run_claim("B3-002", seed=55, store_path=str(store),
                  crash_at="after_effect_before_checkpoint")
    for _ in range(2):
        result = run_claim("B3-002", seed=55, store_path=str(store))
    assert result.status == "resolved"
    assert len(result.refund_effects) == 1
    assert result.refund_effects[0]["amount_vnd"] == 30000
    assert result.committed_audit_count == 1
