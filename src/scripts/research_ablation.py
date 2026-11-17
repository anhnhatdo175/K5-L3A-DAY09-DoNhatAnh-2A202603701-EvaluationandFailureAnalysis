"""R2 ablation: disable the reference swarm's ticket-delay override."""

from unittest.mock import patch

from lab8.schemas import make_run_id
from lab8.shapes import swarm_reference


def run_claim(claim_id, *, seed, store_path, crash_at=None):
    # Separate trace IDs preserve both arms' evidence. Model calls stay intact.
    with (
        patch.object(swarm_reference, "parse_delay_days", return_value=None),
        patch.object(
            swarm_reference,
            "make_run_id",
            side_effect=lambda shape, claim, seed: make_run_id("swarm_order_only", claim, seed),
        ),
    ):
        return swarm_reference.run_claim(
            claim_id, seed=seed, store_path=store_path, crash_at=crash_at,
        )
