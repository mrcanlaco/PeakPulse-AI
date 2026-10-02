# GCP data freshness and automatic recovery — 24 September 2026

## Incident evidence

- Host: `ubuntu@136.110.29.208`, application `/home/ubuntu/dao_vang`.
- The candidate and system-stat snapshots stopped advancing at 13:51 UTC+7,
  while new heartbeat writes continued and `/api/ready` returned HTTP 200.
- Scanner logs contained DuckDB fatal errors: `Failed to delete all rows from
  index`, followed by `database has been invalidated`. The first failing row
  was an `alert_episodes` status transition for ONEUSDT.
- Normalization/alignment was taking 1,087–1,237 seconds per cycle. The lake
  held approximately 591,000 JSONL files and 591,000 Parquet files.
- Candidate comparison V2 was intentionally disabled. The UI nevertheless
  monitored its inactive observation/decision tables and reported 11-day lag.
- The freshness UI also used the old snapshot's own timestamp as its clock,
  concealing the full duration of an outage.

## Changes

1. Remove the unnecessary secondary index on mutable episode status, preserving
   episode rows and primary-key enforcement. DuckDB documents that updating
   indexed columns entails row deletion/reinsertion; the upstream project also
   has a report of this error family. This is a targeted workload mitigation,
   not a claim that all possible DuckDB index failures are eliminated.
   References: [DuckDB index limitations](https://duckdb.org/docs/current/sql/indexes),
   [upstream issue 21394](https://github.com/duckdb/duckdb/issues/21394).
2. Publication failures now fail the scanner cycle and process. Docker's
   existing restart policy can reopen the invalidated database.
3. Incrementally cache source Parquet rows and file identities. Handle replaced
   files, expired partitions, decimal/schema widening and interrupted warm-up.
   Commit rows and their manifest in bounded batches; publish source tables
   only after the complete source is ready. Preserve the archive.
4. Avoid repeated filesystem existence checks for each normalized file.
5. Readiness checks heartbeat, candidate publication, statistics publication
   and actual candle/timeline/feature/OI timestamps. Stale output is HTTP 503.
6. The history UI follows active V1 sources, separates settled funding from OI,
   and measures lag against the current report time.
7. A host watchdog runs every two minutes, even when the application is hung.
   It restarts a stalled running scanner, or an unresponsive web server when
   the scanner is healthy. Cooldown: 30 minutes; budget: three recoveries per
   six hours. Allow five minutes for the first scan after startup. It does not
   start intentionally stopped services.

## Operations

- Inspect: `python3 scripts/production_watchdog.py` (read-only).
- Install/update schedule: `bash scripts/install_production_cron.sh --apply`.
- Latest check and recovery attempts: `data/watchdog_state.json`.
- Watchdog output: `data/watchdog.log`.
- During planned maintenance, create `data/maintenance.flag`; remove it when
  maintenance is finished. An existing flag deliberately pauses recovery.
- Existing daily backup/pruning jobs are preserved by the managed installer.
- Backups for this repair: `backups/incident-20260924/` (database, WAL and code).
- Previous runtime images: `dao_vang-scanner:before-health-fix-20260924` and
  `dao_vang-web:before-health-fix-20260924`.
- The repair is applied to the server checkout and container images. Keep these
  source changes in the next release; the deployment helper intentionally
  refuses to overwrite a dirty checkout.

## Verification

Local regression suite: 194 tests passed, followed by targeted checks for
decimal widening, interrupted warm-up and stale source timestamps. The final
Linux-container suite passed all 70 tests, including source/timeline equivalence,
episode transitions, readiness HTTP responses, cron preservation and watchdog
cooldown/maintenance behavior. New Python files passed Ruff checks; the deployed
React build passed TypeScript and Vite compilation.

Code on the server matches the local repair sources (allowing CRLF/LF differences).
Initial warm-up measurements: candles 47.9 seconds, OI 141.5 seconds; a subsequent
candle pass read zero new files and completed in 0.46 seconds. The final
filesystem optimization also stops existence searches at the first matching
file instead of enumerating the entire partition.

### Final production verification (UTC+7)

| Cycle | Started | Completed | Total | Normalize/alignment |
| --- | --- | --- | --- | --- |
| 1 | 17:06:39 | 17:09:26 | 167.9 seconds | 44.694 seconds |
| 2, automatically scheduled | 17:11:39 | 17:13:15 | 96.3 seconds | 36.577 seconds |

- The second cycle started automatically five minutes after the first.
- At 17:14:35 the authenticated candidate API returned 33 candidates, zero stale.
- Candles, timeline, features and predictions advanced to 17:09:59.999;
  OI advanced to 17:10; settled funding was 17:00.
- Public HTTPS `/api/ready` returned HTTP 200. Scanner and web containers were
  healthy; the Cloudflare tunnel remained running.
- The managed watchdog schedule was installed at 17:11. Real scheduled checks
  at 17:12 and 17:14 recorded `healthy`; no recovery restart was needed.
- The final startup-grace watchdog tests passed all five cases in Linux.
- The live database had zero instances of the removed secondary status index
  and retained 69 episode records before the final live scans.
- Scanner memory measured approximately 708 MiB during the second cycle,
  compared with 5.6 GiB during the incident. This is a point-in-time observation,
  not a peak-memory guarantee.
- Machine-readable confirmation: server
  `backups/incident-20260924/verification.json`.
