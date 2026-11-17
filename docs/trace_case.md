# Trace case — ticket overrides the order database

## Captured run

```text
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55
```

| Field | Observation |
|---|---|
| Trial | `R-swarm-C-002-s55` (aggregate report `E-swarm-20261117-acd6`). |
| Symptom | Ticket says 5 late days; DB says 2. Expected label is denied, refund 0. `swarm` resolves and writes 20,000đ. |
| First wrong step | Event 3, `model_override`, changes `delay_days` to 5. |
| Why first | Events 1–2 are a valid handoff and read-only investigator result; the override is the first event that contradicts the DB. It leads to event 4 quote=20,000 and an incorrect refund. |
| Failure mode | FM-03 `ticket_trust`; recorded in E-002 provenance as `R-swarm-C-002-s55`. |
| Counterfactual | `fixed` has no override event; event 3 quotes 0 with `no_entitlement`, result is denied, ledger remains 0, and Lab 8 grader passes. |
| Regression assertion | `test_override_event_breaks_db_fact` makes `DbFactKept` fail on the observed event; the same grader passes when there is no override. |
| Limitation | This replay proves the deterministic public C-002 case; it does not estimate how often a real model would make this error. |

The FM-08 assertion is `test_reply_amount_must_match_committed_ledger`: an explicit reply of 35,000đ fails against a 20,000đ ledger, while a reply of 20,000đ passes. The reference `swarm` does not record reply text, so `reply_amount_correct` only grades replies when the shape provides that event.
