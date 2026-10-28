#!/usr/bin/env bash
# Create a consistent production snapshot and verify its remote copy.

set -Eeuo pipefail
umask 077

PROJECT_DIR="${DAO_VANG_PROJECT_DIR:-/home/ubuntu/dao_vang}"
REMOTE_ROOT="${DAO_VANG_BACKUP_REMOTE:-gdrive:DaoVang_Data_Backup}"
REMOTE_RETENTION_DAYS="${DAO_VANG_BACKUP_RETENTION_DAYS:-30}"
RUNTIME_UID="${DAO_VANG_RUNTIME_UID:-$(id -u)}"
RUNTIME_GID="${DAO_VANG_RUNTIME_GID:-$(id -g)}"

[[ "$REMOTE_RETENTION_DAYS" =~ ^[0-9]+$ ]] && (( REMOTE_RETENTION_DAYS >= 1 )) || {
    echo "Backup retention days must be a positive integer" >&2
    exit 2
}

PROJECT_DIR="$(realpath -e "$PROJECT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
ARTIFACT_DIR="$PROJECT_DIR/artifacts"
BACKUP_DIR="$PROJECT_DIR/backups"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
LOG_FILE="$DATA_DIR/backup.log"
SUCCESS_MARKER="$DATA_DIR/last_successful_backup.json"
LOCK_FILE="/tmp/dao_vang_backup.lock"

log() {
    printf '%s %s\n' "$(date -Iseconds)" "$*"
}

for command_name in docker rclone flock sha256sum git realpath; do
    command -v "$command_name" >/dev/null || {
        log "ERROR: missing required command: $command_name"
        exit 1
    }
done

test -f "$COMPOSE_FILE" || {
    log "ERROR: compose file not found: $COMPOSE_FILE"
    exit 1
}
test -d "$DATA_DIR" || {
    log "ERROR: data directory not found: $DATA_DIR"
    exit 1
}

mkdir -p "$BACKUP_DIR/snapshots"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
exec 9>"$LOCK_FILE"
flock -n 9 || {
    log "ERROR: another backup is already running"
    exit 1
}

compose() {
    DAO_VANG_RUNTIME_UID="$RUNTIME_UID" DAO_VANG_RUNTIME_GID="$RUNTIME_GID" docker compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE" "$@"
}

timestamp="$(date +'%Y%m%d_%H%M%S')"
snapshot_dir="$BACKUP_DIR/snapshots/$timestamp"
remote_snapshot="$REMOTE_ROOT/snapshots/$timestamp"
services_stopped=0
execution_was_running=0
if compose --profile trading ps --services --status running | grep -qx execution; then
    execution_was_running=1
fi

cleanup() {
    exit_code=$?
    if (( services_stopped == 1 )); then
        log "Backup interrupted; restarting web and scanner"
        compose up -d scanner web || true
        if (( execution_was_running == 1 )); then compose --profile trading up -d execution || true; fi
    fi
    if (( exit_code != 0 )); then
        log "ERROR: backup failed with exit code $exit_code"
    fi
    trap - EXIT INT TERM
    exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

case "$snapshot_dir" in
    "$BACKUP_DIR"/snapshots/*) ;;
    *)
        log "ERROR: unsafe snapshot path: $snapshot_dir"
        exit 1
        ;;
esac

mkdir -p "$snapshot_dir/release" "$snapshot_dir/state"
log "Starting consistent snapshot $timestamp"

services_stopped=1
compose stop --timeout 60 web scanner
if (( execution_was_running == 1 )); then compose --profile trading stop --timeout 60 execution; fi

if [[ -f "$DATA_DIR/live.duckdb" ]]; then
    compose run --rm --no-deps -T scanner python -c 'import duckdb; connection = duckdb.connect("/app/data_live/live.duckdb"); connection.execute("CHECKPOINT"); connection.close()'
    cp --reflink=auto --sparse=always "$DATA_DIR/live.duckdb" "$snapshot_dir/live.duckdb"
fi

cp "$DATA_DIR"/*.json "$snapshot_dir/state/" 2>/dev/null || true
if [[ -d "$ARTIFACT_DIR/frozen_models" ]]; then
    cp -a "$ARTIFACT_DIR/frozen_models" "$snapshot_dir/frozen_models"
fi
cp "$PROJECT_DIR/configs/live.yaml" "$snapshot_dir/release/live.yaml"
cp "$COMPOSE_FILE" "$snapshot_dir/release/docker-compose.yml"
cp "$PROJECT_DIR/uv.lock" "$snapshot_dir/release/uv.lock"
git -C "$PROJECT_DIR" rev-parse HEAD > "$snapshot_dir/release/git-revision.txt"

# Nested V3/notification/execution SQLite stores and every active artifact are
# part of the same quiesced snapshot, not merely the root DuckDB file.
compose run --rm --no-deps -T -v "$snapshot_dir:/snapshot" scanner \
    python -m dao_vang.execution.archive capture \
    --data /app/data_live --artifacts /app/artifacts --snapshot /snapshot/runtime

if (( execution_was_running == 1 )); then compose --profile trading up -d execution; fi
compose up -d --wait --wait-timeout 180 scanner web
services_stopped=0

(
    cd "$snapshot_dir"
    find . -type f ! -name SHA256SUMS -print0 |
        sort -z |
        xargs -0 sha256sum
) > "$snapshot_dir/SHA256SUMS"

rclone mkdir "$REMOTE_ROOT"
rclone copy "$snapshot_dir/" "$remote_snapshot/" --checksum
rclone check "$snapshot_dir/" "$remote_snapshot/" --one-way --checksum

for partition in raw normalized; do
    if [[ -d "$DATA_DIR/$partition" ]]; then
        rclone copy "$DATA_DIR/$partition/" "$REMOTE_ROOT/data-lake/$partition/" --update --checksum
    fi
done

if [[ -f "$snapshot_dir/live.duckdb" ]]; then
    rclone copyto "$snapshot_dir/live.duckdb" "$REMOTE_ROOT/latest/live.duckdb" --checksum
fi
rclone copyto "$snapshot_dir/SHA256SUMS" "$REMOTE_ROOT/latest/SHA256SUMS" --checksum

rclone delete "$REMOTE_ROOT/snapshots" --min-age "${REMOTE_RETENTION_DAYS}d"
rclone rmdirs "$REMOTE_ROOT/snapshots" --leave-root

revision="$(git -C "$PROJECT_DIR" rev-parse HEAD)"
marker_tmp="$SUCCESS_MARKER.tmp"
printf '{"completed_at":"%s","snapshot":"%s","revision":"%s","remote":"%s"}\n' "$(date -Iseconds)" "$timestamp" "$revision" "$remote_snapshot" > "$marker_tmp"
mv "$marker_tmp" "$SUCCESS_MARKER"

rm -rf -- "$snapshot_dir"
log "Backup $timestamp uploaded and checksum-verified successfully"
trap - EXIT INT TERM
