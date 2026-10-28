# V3 completion audit — accepted local implementation

Authority: the five required stages and invariants in
`V3_IMPROVEMENT_PLAN_20260922.md`. All five stages have been implemented and
verified within their stated scope. This does not establish profitable trading.
All artifact paths below
are relative to `artifacts/v3_improvement_20260922/` unless otherwise specified.

| Requirement | Current evidence | Disposition |
|---|---|---|
| Runtime selection explanation, not a reconstructed five-gate substitute | `sol_selection_pattern_final.md`: selection PASS; scanner attaches the explanation from captured before-state and the actual single Timing decision; nine named selection regression cases plus parameterized prerequisite cases | Accepted |
| Preserve selector behavior and legacy unknown state | Root 10,000-snapshot differential run; selector/scanner regression suite; browser assertions for sticky confirmation, score tolerance, missing funding, consumed/cooldown, and absent legacy metadata | Accepted |
| Exact frozen V3 financial replay with weighted fills, costs and funding | Latest `verified_replay_numeric_fix/`, prior `root_verified_check/`; all 153 keys/outcome hashes/eligibility/net planned returns reproduce; Sol independently checked fills, fees, funding, horizons and post-stop separation | Accepted for the frozen historical cohort and disclosed execution assumptions |
| Audit cohort, exact bars, source/model provenance and exclusions | Latest `input_audit_numeric_fix/`: 153 lane rows, 149 source IDs, four overlaps; 53 financial rows, 100 excluded; omissions/double counting corrected; missing model hashes and retrospective labels disclosed | Accepted; missing evidence remains excluded, not filled or promoted |
| Reject invalid funding completeness evidence | `sol_pagination_final_review.md` closes cursor/terminal findings; `sol_numeric_final_review.md` PASS closes both numeric-type findings and confirms unchanged 153 outcomes/53 eligible rows; 38 focused tests pass | Accepted |
| Pattern provenance, held-out support, uncertainty and no unsupported badge | `sol_selection_pattern_final.md`, `sol_pattern_roundtrip_review.md`; zero ECE handled correctly, malformed models rejected, training/policy/heldout support separated, legacy labels non-promotable; load/save/reload regression passes | Accepted |
| Pattern adverse excursion where available | Mechanism rows bind template checksum, temporal eligibility and full Entry-1 MAE/MFE; `sol_handoff_evidence_review.md` independently verifies unique-source after-fit medians, 79-path denominator, template identity and caveats | Accepted as descriptive path evidence, not predictive validation |
| Fixed mechanism definitions and pre-signal features | Frozen protocol and `mechanisms/frozen_inputs.json`; exact 149 PIT joins, nine features, 576 future bars; Sol independently recomputed all 153 paths, group labels, excursions and timestamps | Accepted for descriptive research |
| Independent-count and uncertainty caveats | Combined source deduplication, separate lanes/Champion subsets, chronological per-symbol 48h sensitivity, missingness and Wilson intervals; no causal or profitability promotion | Accepted; serial dependence remains disclosed |
| Regression and UI checks | Latest full unit run after numeric fix: 990 passed/53 warnings (90.66s); focused audit/replay 38 passed; final frontend build and four V3 Chromium cases passed; mobile 390×844 viewport image inspected | Accepted for tested revisions; rerun affected tests if review requires more changes |
| Independent final review and user handoff | Vietnamese `V3_IMPROVEMENT_RESULTS_20260922.md`; `sol_handoff_evidence_review.md` PASS for numerical accuracy and claims; sequential financial/pagination/numeric reviews close all findings | Accepted |

## Preserved invariants checked directly

- Frozen execution spec SHA-256 remains
  `5ee5088f9626b7f2315f7d60cd5bdda154d456cf91a087a7bae2e9fc81414ff5`.
- Frozen research configuration SHA-256 remains
  `f092fa6a56503fc4fd662f8f9940bdcf231e53a404e0d8dbada05739f3596263`.
- Frozen reference cohort SHA-256 remains
  `5bfa857534a23ab3d9312afb676119c91d3cac5f534d9c9e2a5efdfc35fbf924`.
- Original audited JSON remains
  `26010d1a6cdbb5fe8e3eea2044a407b8d149b6bbd6122e864df08bacd4457a5d`.
  Pagination-fix outputs must be separate, not overwrite this evidence.
- Unknown pattern classification does not suppress the Champion dispatch path;
  scanner dispatch remains gated by the frozen `champion` decision, not pattern.
- Reference score and pattern similarity are not presented as calibrated V3
  win probabilities; no pattern has been promoted to confirmed quality.
- Actual stopped outcomes remain separate from post-stop price observations.
- This implementation has not deployed to GCP, sent real Telegram messages,
  placed trades, committed, or pushed code.

## Completion boundary

All recorded review defects have been fixed and independently rechecked. The
latest full unit run is 990 passed with 53 existing library warnings, and the
final frontend build/four V3 browser cases passed. The final audit source hash is
`ca73787a211c6ffb8b5aad22ffe920152d5bddbb14f80a954d24015f20497eff`;
its test hash is
`169efa16600b071d694c157e1b4fcbf2b998cb54677c1d03835833da2c1cd8ff`.
These match the stable revision in the final Sol numeric review.

No implementation or verification requirement in the five-stage plan remains
open. Software acceptance does not prove prospective profitability. Collecting
genuinely future observations is a separate operational step; it cannot be
replaced by reused historical samples or inferred from two manually exited
trades. No deployment or real-money trading is authorized by this acceptance.
