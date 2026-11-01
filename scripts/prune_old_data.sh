#!/usr/bin/env bash
# Prune old local partitions only after a recent verified backup.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${DAO_VANG_PROJECT_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
RETENTION_DAYS="${DAO_VANG_LOCAL_RETENTION_DAYS:-7}"
MAX_BACKUP_AGE_HOURS="${DAO_VANG_MAX_BACKUP_AGE_HOURS:-36}"
apply=0

usage() {
    echo "Usage: $0 [--apply] [--days N]"
}

while (( $# > 0 )); do
    case "$1" in
        --apply)
            apply=1
            shift
            ;;
        --days)
            [[ $# -ge 2 ]] || {
                usage
                exit 2
            }
            RETENTION_DAYS="$2"
            shift 2
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

[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && (( RETENTION_DAYS >= 1 )) || {
    echo "Retention days must be a positive integer" >&2
    exit 2
}
[[ "$MAX_BACKUP_AGE_HOURS" =~ ^[0-9]+$ ]] && (( MAX_BACKUP_AGE_HOURS >= 1 )) || {
    echo "Maximum backup age must be a positive integer" >&2
    exit 2
}

PROJECT_DIR="$(realpath -e "$PROJECT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
SUCCESS_MARKER="$DATA_DIR/last_successful_backup.json"

[[ -f "$SUCCESS_MARKER" ]] || {
    echo "Refusing to prune: verified-backup marker is missing" >&2
    exit 1
}

now_epoch="$(date +%s)"
marker_epoch="$(stat -c %Y "$SUCCESS_MARKER")"
marker_age_seconds=$(( now_epoch - marker_epoch ))
max_marker_age_seconds=$(( MAX_BACKUP_AGE_HOURS * 3600 ))
(( marker_age_seconds >= 0 && marker_age_seconds <= max_marker_age_seconds )) || {
    echo "Refusing to prune: latest verified backup is too old" >&2
    exit 1
}

mode="DRY RUN"
(( apply == 1 )) && mode="APPLY"
echo "[$mode] Local retention: $RETENTION_DAYS days"

found=0
for root in "$DATA_DIR/raw" "$DATA_DIR/normalized"; do
    [[ -d "$root" ]] || continue
    while IFS= read -r -d '' candidate; do
        resolved="$(realpath -e "$candidate")"
        case "$resolved" in
            "$root"/*/date=*) ;;
            *)
                echo "Refusing unsafe prune target: $resolved" >&2
                exit 1
                ;;
        esac
        found=$(( found + 1 ))
        echo "$resolved"
        if (( apply == 1 )); then
            rm -rf -- "$resolved"
        fi
    done < <(
        find "$root" -mindepth 2 -maxdepth 2 -type d -name 'date=*' -mtime "+$RETENTION_DAYS" -print0
    )
done

if (( found == 0 )); then
    echo "No expired partitions found"
elif (( apply == 0 )); then
    echo "Nothing deleted. Re-run with --apply after reviewing these paths."
else
    echo "Deleted $found expired partition directories"
fi
