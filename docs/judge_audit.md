# Judge audit — public replay

Labels are binary with `FAIL` as the positive class. Calibration floors are κ ≥ 0.6, precision ≥ 0.8, recall ≥ 0.7. The counts below were recomputed from the checked-in 100-row CSV files.

| Criterion | n | TP | FP | FN | TN | κ | Precision | Recall | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| tone_ok | 100 | 24 | 4 | 6 | 66 | 0.757 | 0.857 | 0.800 | Pass calibration; usable only as an advisory tone signal |
| helpful | 100 | 9 | 0 | 21 | 70 | 0.375 | 1.000 | 0.300 | Fail; reject as a gate |

Rogan–Gladen correction uses observed judge-positive rate, sensitivity=recall and specificity=TN/(TN+FP). For tone, observed FAIL=0.28 and specificity=66/70, giving corrected failure rate 0.30. For helpful, observed FAIL=0.09 and sensitivity .30, specificity 1.00, giving corrected failure rate 0.30; the low sensitivity makes this estimate unstable.

## Disagreement audit

| Case | Judge | Human | Human rationale / action |
|---|---|---|---|
| Tone H-008 | PASS | FAIL | Overly familiar pronouns/particle; strengthen rubric with register examples. |
| Tone H-017 | PASS | FAIL | “Bạn” is unsuitable for this older customer; add audience-aware address examples. |
| Tone H-029 | PASS | FAIL | “No need to message again” is commanding; distinguish polite wording from coercive intent. |
| Tone H-042 | FAIL | PASS | Short but complete reply; remove apology as a mandatory condition. |
| Tone H-051 | FAIL | PASS | “Refund” is permitted in this CS context; allow approved vocabulary. |
| Helpful HL-015 | PASS | FAIL | Reply states a different amount from ledger; enforce exact ledger comparison in code. |
| Helpful HL-016 | PASS | FAIL | Same amount mismatch; do not delegate money correctness to a language judge. |
| Helpful HL-020 | PASS | FAIL | Same amount mismatch; add ledger-grounded grader (FM-08). |
| Helpful HL-028 | PASS | FAIL | Same amount mismatch; same code-level action. |
| Helpful HL-035 | PASS | FAIL | Same amount mismatch; same code-level action. |

Tone is calibrated on this public replay, but is not a safety or money gate. Helpful is rejected because it misses 70% of human FAIL labels despite perfect precision. Action: use code graders for approvals and money; revise the tone rubric with the examples above and obtain fresh human labels before relying on any judge in release decisions. The replay is public and not a held-out validation set.
