# V3 improvement acceptance — 2026-09-22

User approved the recommendations in the preceding V3 review. This plan preserves
the whole objective; completing an individual stage does not complete the goal.

## Scope and invariants

- Preserve the current runtime Champion selector and execution contract as a
  versioned baseline. Do not silently replace it with the historical five-gate
  description. Any changed selector is a separately named challenger.
- Preserve existing unrelated work, especially Telegram-only-signal edits dated
  2026-09-22. No real Telegram sends, GCP deployment, or live trading in this work.
- The reference model score is not a calibrated V3 weighted-average outcome
  probability. Pattern similarity is not probability or causal evidence.
- Keep all eligible Champion signals regardless of unknown pattern classification.
- Distinguish stopped-trade failure from later price-only target observations.
- Use Luna Max for implementation and Sol Medium for independent review.

## Required stages and completion evidence

1. Selection transparency: authoritative, versioned runtime explanation attached
   to signals; UI distinguishes five-feature checklist from actual Timing and
   funding qualification. Unknown legacy state stays unknown. Regression tests
   demonstrate unchanged selections, including score tolerance and suppression.
2. Exact V3 validation: inventory source cohorts, model provenance, weighted-average
   fills, candle/funding coverage and execution assumptions. Replay the frozen
   V3 cohort with eligible inputs where available. Publish exclusions and costs,
   distinguish reused historical diagnostics from untouched prospective evidence.
   The one-year open-profit search is not an exact V3 validation substitute.
3. Pattern evidence: connect versioned template identity to independently eligible
   outcome support, uncertainty and adverse excursion where available. Missing or
   incompatible evidence must not produce a high-quality badge. Test provenance,
   temporal boundaries and missing-data behavior.
4. Mechanism research: compare reversal-and-dump, reversal-and-continuation and
   sideways outcomes using only pre-signal features for explanations/prediction.
   Freeze definitions before computing comparisons, report independent episode
   counts and uncertainty, and avoid causal claims from observational associations.
5. Verification and handoff: targeted and relevant regression tests, frontend
   build/render checks for changed UI, Sol review of final code/evidence, and a
   user-facing report clearly separating implemented changes from unproven edge.

## Evidence limits

Prospective samples cannot be manufactured from previously examined history.
Configured promotion gates remain in force; software completion alone does not
establish profitable performance or authorize deployment. If collecting future
evidence needs new operational authority, ask for that authority explicitly.

## Historical progress log (latest status below)

- Initial review completed; selection metadata implementation dispatched to Luna
  Max. Runtime/configuration selection logic is to remain frozen.
- Existing six-month replay explicitly rejects financial eligibility without
  provider funding attestation. New annual funding data may help, but compatibility
  and coverage must be verified rather than assumed.
- Baseline checks on 2026-09-22: 34 label/dual-outcome/pattern tests and 33
  scanner/dispatch/selector tests passed before the new worker edits. These are
  baseline checks, not final verification of the pending changes.
- Confirmed quality-gate bug: finite ECE=0.0 is currently replaced by the missing
  fallback through `or 1.0`. Pattern worker owns the fix and boundary tests.
- Frozen mechanism definitions are in `V3_MECHANISM_PROTOCOL_20260922.md`.
- Selection worker completed its first pass. Root reran 39 selector/scanner/
  dispatch/explanation tests and the two existing V3 browser smoke tests: all
  passed. Frontend build passed. These tests do not resolve the pending sticky
  confirmation explanation finding or prove coverage of every new UI state.
  Sol Medium selection review is in progress; stage 1 is not yet accepted.
- Input audit and pattern workers remain active; no new financial replay or
  mechanism comparison result has been published yet.
- Intermediate full unit suite: 937 passed, 53 warnings (160.26 seconds).
  This run precedes the selection-review fixes and final replay implementation;
  it is not the final acceptance run.
- Sol requested changes to selection explanation (sticky latch, skipped cooldown,
  pure gate vs final qualification, full UI prerequisites). Luna fix is active.
- Initial input audit completed: all 153 price paths are available. Root verified
  the protocol-document digest discrepancy is solely CRLF vs LF; a reviewed
  text-only equivalence check and exact V3 replay are now assigned. Four partial
  funding symbols remain explicitly excluded unless independently resolved.
- Pattern worker completed its bounded implementation: 35 focused tests and
  175 experiment tests passed. Root generated separate research-only artifacts
  under `artifacts/v3_improvement_20260922/pattern_research/` without replacing
  serving artifacts. The legacy dataset remains unsupported for compact outcomes.
  Only pattern_05 has qualifying heldout support: 15 events, 7 positives; this is
  legacy Entry-1 exploratory evidence, not a V3 improvement claim. Other patterns
  have insufficient policy support and no qualifying heldout rows in this report.
- Mechanism study implementation dispatched against the frozen descriptive
  protocol; exact financial replay and selection fixes continue independently.
- Root differential check against HEAD selector passed on 10,000 deterministic
  snapshots (seed 20260922): identical Timing decisions/episode IDs, Champion gate
  results, episode state and last-entry state after capturing before-state and
  generating explanations. Inputs span score boundaries, pump/reversal thresholds,
  missing funding, stablecoins and time gaps. Recheck if selector code changes.

## Latest acceptance checkpoint

- Sol final selection review: PASS, including 44 focused Python tests and two
  browser cases. Stage 1 accepted independently; the full goal is not complete.
- Sol pattern review initially requested legacy load/save/reload checksum
  compatibility changes. Luna fixed them; Sol follow-up PASS, 33 focused tests,
  current serving/research identity links checked. Stage 3 accepted.
- Mechanism implementation and real artifacts exist: 153 lane rows, 149 unique
  source events, 149 exact PIT joins and complete paths. Root ran its 14 tests;
  Sol Medium review PASS independently recomputed every path and denominator,
  checked hashes and temporal limitations. Stage 4 accepted as descriptive
  historical research, not causal or financial evidence.
- Exact financial replay and root independent run exist: all 153 lane keys,
  outcome hashes, eligibility flags and planned net returns match. Global
  exclusion double counting and input-audit Markdown omission are corrected;
  root reran 19 audit/replay tests successfully. Sol independently checked 153
  financial records, fills, costs, funding, post-stop separation and summaries
  without discrepancies, and ran 31 additional engine/dual-outcome tests.
- Stage 2 accepted: Sol's cursor/terminal-pagination findings and two subsequent
  integer-type findings are fixed and independently rechecked. Final
  `sol_numeric_final_review.md` is PASS with 38 focused tests. Latest output
  directories are `input_audit_numeric_fix/` and `verified_replay_numeric_fix/`.
  Root and Sol confirm 153 unchanged outcome hashes/eligibility/net returns and
  53 eligible rows. Original source cache, audit JSON and replay reports remain
  immutable; missing funding evidence stays excluded.
- Root full unit suite after checksum fix: 970 passed, 53 warnings, 135.04s.
  Rerun affected tests if subsequent financial/reporting changes occur.
- Latest root full unit suite after pagination fix: 976 passed, 53 warnings,
  133.66s. Focused audit/replay tests: 24 passed. Worker Ruff check clean.
- Final root full unit suite after numeric fix: 990 passed, 53 existing warnings,
  90.66s. Final focused audit/replay: 38 passed; worker Ruff clean. Final source
  and test hashes match the stable version accepted by Sol.
- Root final frontend rebuild passed; all four V3 Chromium cases passed (4.2s),
  covering existing mobile/post-stop behavior and new selection explanations.
- Sol handoff evidence review PASS for document accuracy: independently checked
  the source-deduplicated post-fit pattern MAE/MFE table, all denominators,
  template identity, Champion targets/net planned returns and evidence caveats.
  The separate final numeric review accepts the last validator follow-up.
- Stage 5 accepted: final tests/build/browser checks, sequential independent
  reviews, Vietnamese report and requirement-by-requirement completion audit
  are present. All five stages are complete within the local implementation
  scope; prospective profitability and deployment are not claimed.
- No deployment, real alert, live trade, selector change or quality promotion
  has been authorized by this checkpoint.

## Preserved baseline identities

- `src/dao_vang/labels/specs/distribution_short_v3.py` SHA-256:
  `5ee5088f9626b7f2315f7d60cd5bdda154d456cf91a087a7bae2e9fc81414ff5`.
- `configs/distribution_v3_research_standard.yaml` SHA-256:
  `f092fa6a56503fc4fd662f8f9940bdcf231e53a404e0d8dbada05739f3596263`.
- `artifacts/v3_six_month_20260915/oos_reference_events.json` SHA-256:
  `5bfa857534a23ab3d9312afb676119c91d3cac5f534d9c9e2a5efdfc35fbf924`.
