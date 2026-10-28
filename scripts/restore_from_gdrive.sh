#!/usr/bin/env bash
# Verify a remote snapshot, then restore DuckDB only with explicit --apply.

set -Eeuo pipefail
umask 077

PROJECT_DIR="${DAO_VANG_PROJECT_DIR:-/home/ubuntu/dao_vang}"
REMOTE_ROOT="${DAO_VANG_BACKUP_REMOTE:-gdrive:DaoVang_Data_Backup}"
RUNTIME_UID="${DAO_VANG_RUNTIME_UID:-$(id -u)}"
RUNTIME_GID="${DAO_VANG_RUNTIME_GID:-$(id -g)}"
snapshot=""
apply=0
list_only=0

usage() {
    echo "Usage: $0 --list | --snapshot YYYYMMDD_HHMMSS [--apply]"
}

while (( $# > 0 )); do
    case "$1" in
        --list)
            list_only=1
            shift
            ;;
        --snapshot)
            [[ $# -ge 2 ]] || {
                usage
                exit 2
            }
            snapshot="$2"
            shift 2
            ;;
        --apply)
            apply=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

for command_name in docker rclone sha256sum curl realpath mktemp; do
    command -v "$command_name" >/dev/null || {
        echo "Missing required command: $command_name" >&2
        exit 1
    }
done

if (( list_only == 1 )); then
    rclone lsf "$REMOTE_ROOT/snapshots" --dirs-only
    exit 0
fi

[[ "$snapshot" =~ ^[0-9]{8}_[0-9]{6}$ ]] || {
    echo "Snapshot must match YYYYMMDD_HHMMSS" >&2
    exit 2
}

PROJECT_DIR="$(realpath -e "$PROJECT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
BACKUP_DIR="$PROJECT_DIR/backups"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
STAGING_ROOT="$BACKUP_DIR/restore-staging"
ROLLBACK_ROOT="$BACKUP_DIR/pre-restore"
REMOTE_SNAPSHOT="$REMOTE_ROOT/snapshots/$snapshot"

test -f "$COMPOSE_FILE" || {
    echo "Compose file not found: $COMPOSE_FILE" >&2
    exit 1
}
mkdir -p "$STAGING_ROOT" "$ROLLBACK_ROOT"
stage_dir="$(mktemp -d "$STAGING_ROOT/$snapshot.XXXXXX")"
rollback_dir="$ROLLBACK_ROOT/$(date +'%Y%m%d_%H%M%S')"
restore_started=0
restore_succeeded=0
old_db_moved=0
runtime_restore=0
execution_was_running=0

compose() {
    DAO_VANG_RUNTIME_UID="$RUNTIME_UID" DAO_VANG_RUNTIME_GID="$RUNTIME_GID" docker compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE" "$@"
}

if compose --profile trading ps --services --status running | grep -qx execution; then
    execution_was_running=1
fi

cleanup() {
    exit_code=$?
    if (( restore_started == 1 && restore_succeeded == 0 )); then
        echo "Restore failed; rolling back the previous database" >&2
        compose stop --timeout 60 web scanner || true
        if (( execution_was_running == 1 )); then compose --profile trading stop --timeout 60 execution || true; fi
        if (( runtime_restore == 1 )); then
            compose run --rm --no-deps -T -v "$stage_dir:/snapshot:ro" -v "$rollback_dir:/rollback" scanner \
                python -m dao_vang.execution.archive rollback --data /app/data_live \
                --artifacts /app/artifacts --snapshot /snapshot/runtime --rollback /rollback/runtime || true
        fi
        if (( runtime_restore == 0 )); then
        if [[ -f "$DATA_DIR/live.duckdb" ]]; then
            mv "$DATA_DIR/live.duckdb" "$rollback_dir/failed-restored.duckdb" || true
        fi
        if (( old_db_moved == 1 )) && [[ -f "$rollback_dir/live.duckdb" ]]; then
            mv "$rollback_dir/live.duckdb" "$DATA_DIR/live.duckdb" || true
        fi
        if [[ -f "$rollback_dir/live.duckdb.wal" ]]; then
            mv "$rollback_dir/live.duckdb.wal" "$DATA_DIR/live.duckdb.wal" || true
        fi
        fi
        compose up -d scanner web || true
        if (( execution_was_running == 1 )); then compose --profile trading up -d execution || true; fi
    fi
    case "$stage_dir" in
        "$STAGING_ROOT"/*) rm -rf -- "$stage_dir" ;;
        *) echo "Refusing unsafe staging cleanup: $stage_dir" >&2 ;;
    esac
    trap - EXIT INT TERM
    exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Downloading snapshot $snapshot for checksum verification"
rclone copy "$REMOTE_SNAPSHOT/" "$stage_dir/" --checksum
(
    cd "$stage_dir"
    sha256sum --check SHA256SUMS
)
test -f "$stage_dir/live.duckdb" || {
    echo "Snapshot has no live.duckdb" >&2
    exit 1
}

revision="unknown"
if [[ -f "$stage_dir/release/git-revision.txt" ]]; then
    revision="$(tr -d '[:space:]' < "$stage_dir/release/git-revision.txt")"
fi
echo "Verified snapshot: $snapshot"
echo "Recorded application revision: $revision"

if (( apply == 0 )); then
    echo "Dry run only. Re-run with --apply to stop services and restore DuckDB."
    exit 0
fi

mkdir -p "$rollback_dir"
restore_started=1
compose stop --timeout 60 web scanner
if (( execution_was_running == 1 )); then compose --profile trading stop --timeout 60 execution; fi

if [[ -f "$stage_dir/runtime/manifest.json" ]]; then
    runtime_restore=1
    compose run --rm --no-deps -T -v "$stage_dir:/snapshot:ro" -v "$rollback_dir:/rollback" scanner \
        python -m dao_vang.execution.archive install --data /app/data_live \
        --artifacts /app/artifacts --snapshot /snapshot/runtime --rollback /rollback/runtime
else

if [[ -f "$DATA_DIR/live.duckdb" ]]; then
    mv "$DATA_DIR/live.duckdb" "$rollback_dir/live.duckdb"
    old_db_moved=1
fi
if [[ -f "$DATA_DIR/live.duckdb.wal" ]]; then
    mv "$DATA_DIR/live.duckdb.wal" "$rollback_dir/live.duckdb.wal"
fi

install -m 600 "$stage_dir/live.duckdb" "$DATA_DIR/live.duckdb"
if [[ -d "$stage_dir/frozen_models" ]]; then
    mkdir -p "$PROJECT_DIR/artifacts/frozen_models"
    cp -an "$stage_dir/frozen_models/." "$PROJECT_DIR/artifacts/frozen_models/"
fi
fi

if (( execution_was_running == 1 )); then compose --profile trading up -d execution; fi
compose up -d --wait --wait-timeout 180 scanner web
curl --fail --silent --show-error http://localhost:8000/api/health >/dev/null
curl --fail --silent --show-error http://localhost:8000/api/ready >/dev/null

restore_succeeded=1
echo "Restore completed. Previous database retained in $rollback_dir"
trap - EXIT INT TERM
case "$stage_dir" in
    "$STAGING_ROOT"/*) rm -rf -- "$stage_dir" ;;
    *) echo "Refusing unsafe staging cleanup: $stage_dir" >&2 ;;
esac
