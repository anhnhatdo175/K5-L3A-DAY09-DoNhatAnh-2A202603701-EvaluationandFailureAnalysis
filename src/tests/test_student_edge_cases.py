import json
from pathlib import Path

import pytest

from lab8.db import connect
from lab8.shapes import SHAPES, single


@pytest.mark.parametrize("shape", ["workflow", "single", "orchestrator"])
def test_unknown_claim_returns_failed_with_fresh_trace(public_db, shape):
    result = SHAPES[shape]("C-UNKNOWN", seed=11, store_path=str(public_db))
    assert result.status == "failed"
    assert result.error_reason == "unknown_claim"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    trace = json.loads(Path(result.trace_path).read_text())
    assert trace["run_id"] == result.run_id
    assert trace["events"]


@pytest.mark.parametrize("shape", ["workflow", "single", "orchestrator"])
def test_changed_quote_on_retry_preserves_original_payment(public_db, shape):
    first = SHAPES[shape]("C-001", seed=11, store_path=str(public_db))
    conn = connect(public_db)
    try:
        conn.execute("UPDATE orders SET shipping_fee_vnd = 10000 WHERE order_id = 'O-107'")
        conn.commit()
    finally:
        conn.close()
    second = SHAPES[shape]("C-001", seed=11, store_path=str(public_db))
    assert first.status == "resolved"
    assert second.status == "failed"
    assert second.error_reason == "amount_conflict"
    assert second.proposal_amount == 10000
    assert second.refund_effects == first.refund_effects
    assert second.committed_audit_count == 1


def test_single_step_cap_stops_without_payment(public_db, monkeypatch):
    def hit_cap(conn, budget, **kwargs):
        # Exercise the real runtime cap with a decision that never finishes.
        from lab8.runtime import run_react

        assert kwargs["max_steps"] == 8
        return run_react(
            conn, budget, observation=kwargs["observation"], max_steps=8, worker=True,
            decide=lambda _: {"tool": "lookup_policy"},
        )

    monkeypatch.setattr(single, "run_react", hit_cap)
    result = single.run_claim("C-001", seed=11, store_path=str(public_db))
    assert result.status == "failed"
    assert result.error_reason == "step_cap"
    assert result.refund_effects == []
    assert result.committed_audit_count == 0
    assert result.tool_calls == 9  # Initial claim read plus eight bounded reads.
