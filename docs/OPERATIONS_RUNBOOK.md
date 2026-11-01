# Production operations runbook

## Service objectives

- Recovery point objective (RPO): at most 24 hours for DuckDB and release
  state.
- Recovery time objective (RTO): 60 minutes for a verified snapshot restore.
- Local raw/normalized retention: 7 days by default.
- Remote versioned snapshot retention: 30 days by default.
- The normalized/raw data lake is copied incrementally and is not deleted by
  the local prune script.

Secrets are not included in Google Drive snapshots. Keep the Docker environment
file, SSH key, Telegram token and AI credentials in the approved secret store
and test their recovery separately.

## Health contract

- /api/health is web-process liveness. It remains compatible with simple load
  balancer checks.
- /api/ready is application readiness. It returns HTTP 503 when the scanner
  heartbeat is missing, stale, stopped, its last cycle failed, the official
  `fibo_trend_short` lane failed (`reason: fibo_trend_short_failed`), disk use
  reaches 90%, or free space falls below 5 GiB.
- See `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` for the official 2-tier signal
  routing architecture (`Fibo Short v4.0.21` primary Telegram engine + `V3.1`
  UI-only overheating radar) and emergency Kill Switch commands.
- Docker Compose, deployment verification and the 15-minute GitHub production
  monitor all use /api/ready.
- The scheduled workflow is .github/workflows/production-health.yml.

An HTTP 200 from /api/health with an HTTP 503 from /api/ready means the
dashboard process is alive but production scanning is not ready.

## Backup schedule

Run the consistent backup once per day, then prune only after it succeeds:

    10 2 * * * cd /home/ubuntu/dao_vang && bash scripts/backup_to_gdrive.sh
    0 4 * * * cd /home/ubuntu/dao_vang && bash scripts/prune_old_data.sh --apply

The deploy workflow installs these entries through
scripts/install_production_cron.sh. The installer backs up the prior crontab,
preserves unrelated jobs, removes the legacy five-minute git reset job and
maintains one repository-owned block. Preview it with --print before applying
manually.

Web and scanner run with the host deployment UID/GID rather than root. Deploy
runs scripts/prepare_runtime_permissions.sh before Compose so existing
root-owned data and artifact files are migrated once. On a different host,
export DAO_VANG_RUNTIME_UID and DAO_VANG_RUNTIME_GID before using Compose.
The same migration sets .env.docker to mode 600 and gives tunnel credentials
only to the deployment owner and cloudflared group.

The backup script:

1. Acquires a host lock so two backups cannot overlap.
2. Gracefully stops web/scanner, checkpoints DuckDB and copies the database.
3. Restarts both services and waits for their healthchecks.
4. Captures runtime JSON state, all frozen bundles, live config, lockfile and
   Git revision.
5. Writes SHA256SUMS, uploads the versioned snapshot, and runs rclone check.
6. Updates data-lake copies and latest/live.duckdb.
7. Writes data/last_successful_backup.json only after remote verification.
8. Deletes remote snapshot files older than the configured retention period.

Optional environment overrides:

- DAO_VANG_BACKUP_REMOTE
- DAO_VANG_BACKUP_RETENTION_DAYS
- DAO_VANG_LOCAL_RETENTION_DAYS
- DAO_VANG_MAX_BACKUP_AGE_HOURS
- DAO_VANG_PROJECT_DIR

The prune command is a dry run unless --apply is present. It refuses to delete
anything if the verified-backup marker is missing or older than 36 hours.

## Restore and monthly drill

List snapshots:

    bash scripts/restore_from_gdrive.sh --list

Download and verify a selected snapshot without changing services:

    bash scripts/restore_from_gdrive.sh --snapshot YYYYMMDD_HHMMSS

Apply during a maintenance window:

    bash scripts/restore_from_gdrive.sh --snapshot YYYYMMDD_HHMMSS --apply

The apply path stops web/scanner, moves the current database into
backups/pre-restore, installs the verified database, restores any missing
immutable model bundles, starts both services, and checks liveness/readiness.
If verification fails, it automatically restores the previous database.

Perform the dry-run verification monthly. Perform an apply drill on a separate
staging checkout at least quarterly. Record snapshot ID, duration, result and
the application revision embedded in the snapshot.

## Incident triage

1. Check /api/health and /api/ready.
2. Check docker compose ps and scanner heartbeat age.
3. Review scanner/web container logs without changing data.
4. Confirm free disk space; act before usage exceeds 85%.
5. If the current DB is corrupt, select the newest checksum-verified snapshot
   and follow the restore procedure.
6. Never reset the server worktree or promote a challenger during recovery.

## Credential follow-up

Historical SSH passwords may remain recoverable from Git history even after
their removal from the current tree. Rotate the old server credential, revoke
unused keys, update GitHub secrets, and verify key-only SSH before considering
the security item closed.
