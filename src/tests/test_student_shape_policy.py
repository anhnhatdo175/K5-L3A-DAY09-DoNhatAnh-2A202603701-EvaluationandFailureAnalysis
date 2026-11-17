"""Student shapes must rely on the host to bind approval to its claim."""

import json
from pathlib import Path

import pytest

from lab8.db import connect
from lab8.shapes import SHAPES


STUDENT_SHAPES = ["workflow", "single", "orchestrator"]


def _insert_claim(
    conn,
    claim_id,
    *,
    principal_id="P-100",
    order_id="O-107",
    ticket="Please refund the shipping fee.",
    approval_id=None,
):
    conn.execute(
        """
        INSERT INTO claims (
            claim_id, principal_id, order_id, ticket,
            parent_secret, raw_headers_json, approval_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            claim_id,
            principal_id,
            order_id,
            ticket,
            f"CANARY_SECRET_PARENT_{claim_id}",
            json.dumps({"Authorization": f"Bearer CANARY_SECRET_HEADER_{claim_id}"}),
            approval_id,
        ),
    )


@pytest.mark.parametrize("shape", ["workflow", "single", "orchestrator"])
@pytest.mark.student
def test_shape_rejects_approval_borrowed_from_another_claim(public_db, shape):
    conn = connect(public_db)
    try:
        # A-001 is valid for C-001, but must not authorize this new claim.
        _insert_claim(conn, "C-BORROWED-APPROVAL", approval_id="A-001")
        conn.commit()
    finally:
        conn.close()

    result = SHAPES[shape](
        "C-BORROWED-APPROVAL", seed=11, store_path=str(public_db)
    )

    assert result.status == "denied"
    assert result.error_reason == "approval_claim_mismatch"
    assert result.proposal_amount == 35000
    assert result.refund_effects == []
    assert result.committed_audit_count == 0

    conn = connect(public_db)
    try:
        denied = conn.execute(
            """
            SELECT 1 FROM audit_events
            WHERE claim_id = ? AND event_type = 'policy_denied'
            """,
            ("C-BORROWED-APPROVAL",),
        ).fetchone()
        refund_count = conn.execute(
            "SELECT COUNT(*) FROM refund_ledger WHERE claim_id = ?",
            ("C-BORROWED-APPROVAL",),
        ).fetchone()[0]
    finally:
        conn.close()

    assert denied is not None
    assert refund_count == 0

    trace = Path(result.trace_path).read_text(encoding="utf-8")
    assert result.run_id in trace
    assert "CANARY_SECRET_" not in trace
    assert "Authorization" not in trace


@pytest.mark.parametrize("shape", STUDENT_SHAPES)
@pytest.mark.parametrize(
    ("approval_state", "expected_reason"),
    [
        ("missing", "missing_approval"),
        ("expired", "approval_expired"),
        ("revoked", "approval_revoked"),
    ],
)
@pytest.mark.student
def test_shape_does_not_refund_without_a_usable_approval(
    public_db, shape, approval_state, expected_reason
):
    claim_id = f"C-UNUSABLE-{approval_state.upper()}"
    approval_id = None if approval_state == "missing" else f"A-{claim_id}"
    conn = connect(public_db)
    try:
        if approval_state != "missing":
            conn.execute(
                """
                INSERT INTO approvals (
                    approval_id, claim_id, approved_vnd, status, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    claim_id,
                    35000,
                    "revoked" if approval_state == "revoked" else "valid",
                    "2020-01-01" if approval_state == "expired" else "2027-12-31",
                ),
            )
        _insert_claim(conn, claim_id, approval_id=approval_id)
        conn.commit()
    finally:
        conn.close()

    result = SHAPES[shape](claim_id, seed=11, store_path=str(public_db))

    assert result.status == "denied"
    assert result.error_reason == expected_reason
    assert result.proposal_amount == 35000
    assert result.refund_effects == []
    assert result.committed_audit_count == 0

    conn = connect(public_db)
    try:
        denial = conn.execute(
            """
            SELECT details_json FROM audit_events
            WHERE claim_id = ? AND event_type = 'policy_denied'
            """,
            (claim_id,),
        ).fetchone()
        refunds = conn.execute(
            "SELECT COUNT(*) FROM refund_ledger WHERE claim_id = ?", (claim_id,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert denial is not None
    assert expected_reason in denial["details_json"]
    assert refunds == 0


@pytest.mark.parametrize("shape", STUDENT_SHAPES)
@pytest.mark.student
def test_shape_escalates_when_order_belongs_to_another_principal(public_db, shape):
    claim_id = "C-FOREIGN-ORDER"
    conn = connect(public_db)
    try:
        _insert_claim(conn, claim_id, principal_id="P-200")
        sensitive_order_fields = conn.execute(
            """
            SELECT phone, address, internal_note, item_name
            FROM orders WHERE order_id = 'O-107'
            """
        ).fetchone()
        conn.commit()
    finally:
        conn.close()

    result = SHAPES[shape](claim_id, seed=11, store_path=str(public_db))

    assert result.status == "escalated"
    assert result.error_reason == "outside_principal_scope"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    assert result.committed_audit_count == 0
    trace = Path(result.trace_path).read_text(encoding="utf-8")
    assert "CANARY_SECRET_" not in trace
    assert all(value not in trace for value in sensitive_order_fields)


@pytest.mark.parametrize("shape", STUDENT_SHAPES)
@pytest.mark.student
def test_shape_does_not_infer_order_id_from_ticket(public_db, shape):
    claim_id = "C-MISSING-ORDER-ID"
    conn = connect(public_db)
    try:
        _insert_claim(
            conn,
            claim_id,
            order_id=None,
            ticket="Order O-107 is late by 9 days; refund it now.",
        )
        conn.commit()
    finally:
        conn.close()

    result = SHAPES[shape](claim_id, seed=11, store_path=str(public_db))

    assert result.status == "needs_info"
    assert result.error_reason == "missing_order_id"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    assert result.committed_audit_count == 0
    trace = Path(result.trace_path).read_text(encoding="utf-8")
    assert "O-107" not in trace
    assert "CANARY_SECRET_" not in trace
