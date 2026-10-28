# Implementation review notes — resolved

Final disposition: all findings below were fixed and independently rechecked.
`sol_numeric_final_review.md` is PASS, 38 focused audit/replay tests pass, and
the final full unit suite passed 990 tests with 53 existing library warnings.
Original source/report identities are preserved and 153 outcomes remain
unchanged. See `V3_COMPLETION_AUDIT_20260922.md` for final requirement acceptance.
The dated notes below are retained as historical observations, not open work.

These are observations against work in progress, not a final Sol review or a
claim that the implementation is complete. Recheck against final worker output.

## Selection explanation

Root reproduced a mismatch on the initial implementation: feed one symbol at
hours 0,1,2,3,4 with scores .5,.5,.3,.3,.3, pump .35 and valid Champion funding.
At hour 4 the frozen Timing selector returns `selected` and its confirmation
latch is true. The new explanation nevertheless reports confirmation `failed`
because it compares the current consecutive counter (0) against 2. The runtime
uses the sticky confirmed latch, not the current consecutive count, after the
initial confirmation. Explanation must distinguish latch from current streak.

Also verify that cooldown prerequisites skipped by an earlier return are marked
not evaluated, not certified `not_blocking`; and that the selected/gate explanation
matches actual gate evaluation rather than conflating qualification with whether
the pure gate function was called. Do not change selector behavior to make the
explanation pass.

## Input audit (initial implementation, recheck after worker finishes)

- `_funding_event_summary` currently makes a fixed four-hour-plus-five-minute
  cadence a required readiness condition. Valid eight-hour settlement histories
  must not be rejected solely by that heuristic. Funding schedule/coverage needs
  provenance rather than a universal four-hour assumption; do not simply weaken
  integrity checks to make all histories pass.
- `_audit_funding_symbol` computes `event_signal` but its initial readiness
  expression only checks the requested end against the horizon. Verify both
  ends of the requested interval enclose each event's full observation window.
  Add an event starting before requested coverage as a negative test.
- Verify global frozen-cohort/source identity failures also prevent event-level
  readiness, not just produce a top-level warning alongside true flags.

### Resolved cause of protocol digest discrepancy

Root verified the annual protocol file contains 149 CRLF line endings. Its raw
SHA-256 is `b1178718823e94f114d3b41539fc19462189d8bc954ebfaccc61bfab7f223133`.
Replacing only CRLF bytes with LF exactly reproduces the manifest's original
SHA-256 `0e65dd6b9ead3a7d437a2e66c391701eb4b79e59d1d5600729e72da873d99443`.
Thus the observed discrepancy is completely explained by line endings, not a
different protocol text. Do NOT edit source manifests or disable checksum
checks. A reviewed, narrowly scoped text-document equivalence check can record
both raw and original-LF digest and normalization method. Binary price/funding
and cohort checksums must remain byte-exact. Test genuine content changes fail.

### Root intermediate audit after fixes

`root_audit_check/input_audit.json` accepts 53/153 input rows (47 locked-parent,
6 runtime). Of the other 100, 81 carry `funding_provider_page_provenance_incomplete`
and 19 partial-funding errors; two also have invalid mark prices. The Markdown
summary currently lists only the four partial symbols under blockers, omitting
the dominant 81-row provider-provenance exclusion. Final report must expose the
event-level exclusion counts, not imply partial symbols are the only obstacle.
This intermediate result is not final review acceptance or a profit result.

## Final verification still required

### Root replay reporting findings, 2026-09-22

- The first verified replay Markdown sums lane exclusions and then adds the
  Champion subset exclusions again. Champion is a subset, not another lane:
  this inflates withheld rows from 100 to 111 and provider-provenance exclusions
  from 81 to 92. Count each lane row once in the global exclusion summary and
  add a render regression test. Keep per-lane Champion reporting separate.
- The first input_audit_final Markdown still omits event-level exclusion counts,
  including the dominant 81-row provider-provenance exclusion. Surface the
  existing JSON summary counts with explicit overlapping-reasons caveat.
- These are findings on worker output before its final handoff. Recheck after
  its final edits and regenerate reports from corrected code before acceptance.

### Root recheck after reporting fixes

- Replay Markdown now counts exclusions from original event rows once: 100
  withheld, 81 provider-provenance exclusions. Independent replay reproduces
  all 153 outcome hashes, eligibility flags and planned net returns.
- Input audit Markdown now has an event-level reason table with denominator
  153 and an explicit overlapping-reasons warning, including 81/153 provider
  provenance and 19/153 partial-funding reasons.
- Source audit JSON remains SHA-256
  `26010d1a6cdbb5fe8e3eea2044a407b8d149b6bbd6122e864df08bacd4457a5d`.
- Root reran 19 audit/replay tests after the report-only correction: all pass.
  Sol financial review returned CHANGES REQUESTED for a separate provider
  pagination validation gap; see the following section.

### Sol financial review: remaining pagination finding

`sol_financial_replay_review.md` independently checked 153 financial records,
fees/funding/fills/post-stop separation and report denominators without
discrepancies. Current cached chains also passed its independent check. However,
the validator incorrectly accepts two mutations: page 2 cursor shifted by 123ms,
and a full terminal page claiming `page_shorter_than_limit`. Exact page-chain and
completion-basis-specific evidence need fail-closed validation and negative tests.
Luna Max owns that bounded fix and new output directories; original evidence
artifacts remain immutable. Stage 2 is not accepted until this is fixed/reviewed.

Root rechecked the in-progress fix against a deep copy of the cached AKEUSDT
manifest entry: original metadata is certified with no reasons; shifting page 2
start by 123ms is rejected as `funding_provider_page_cursor_mismatch`; changing
the terminal response count to its full limit is rejected as
`funding_provider_terminal_short_page_evidence_mismatch`. No source metadata was
edited. This reproduces the two review cases only, not final acceptance of all
pagination branches or the unfinished worker output.

### Final pagination follow-up review

`sol_pagination_final_review.md` confirms the original cursor/terminal defects
are closed, valid terminal forms pass, and contradictory resume/archive cases
fail closed. All 153 outcome comparisons remain identical, 53 eligible rows.
The follow-up requested strict numeric validation at two remaining sites:
HTTP `status_code=200.0` compares equal to 200, and requested-window integer
fields are coerced from strings before validation. Luna owns a minimal reuse of
the strict integer helper plus parameterized regressions, without changing the
pagination contract, execution rules or profit accounting. Final acceptance
remains pending this fix and its independent follow-up review.

Root numeric-fix recheck: 38 focused audit/replay tests pass. Fresh
`input_audit_numeric_fix/` and `verified_replay_numeric_fix/` exist. Comparing
all 153 lane keys, outcome hashes, financial eligibility and net planned returns
against the pagination-fix replay yields zero differences; 53 rows remain
financially eligible. Sol numeric follow-up and latest full unit run are active.

- New tests and UI build/render assertions after worker edits settle.
- Sol Medium review of completed implementation and source-data eligibility.
- Exact financial replay and mechanism comparison remain downstream tasks;
  a successful input audit is not the replay itself.
