#!/usr/bin/env bash
# Install the repository-owned production cron block without touching other jobs.

set -Eeuo pipefail

PROJECT_DIR="${DAO_VANG_PROJECT_DIR:-/home/ubuntu/dao_vang}"
apply=0

case "${1:-}" in
    --apply)
        apply=1
        ;;
    ""|--print)
        ;;
    -h|--help)
        echo "Usage: $0 [--print|--apply]"
        exit 0
        ;;
    *)
        echo "Unknown argument: $1" >&2
        exit 2
        ;;
esac

for command_name in crontab awk diff mktemp realpath; do
    command -v "$command_name" >/dev/null || {
        echo "Missing required command: $command_name" >&2
        exit 1
    }
done

PROJECT_DIR="$(realpath -e "$PROJECT_DIR")"
test -f "$PROJECT_DIR/scripts/backup_to_gdrive.sh" || {
    echo "Backup script not found under $PROJECT_DIR" >&2
    exit 1
}

existing="$(mktemp)"
proposed="$(mktemp)"
cleanup() {
    rm -f -- "$existing" "$proposed"
}
trap cleanup EXIT

crontab -l > "$existing" 2>/dev/null || true
awk '
    $0 == "# BEGIN DAO_VANG_MANAGED" { managed = 1; next }
    $0 == "# END DAO_VANG_MANAGED" { managed = 0; next }
    managed { next }
    /scripts\/backup_to_gdrive[.]sh/ { next }
    /scripts\/prune_old_data[.]sh/ { next }
    /# auto_update/ { next }
    { print }
' "$existing" > "$proposed"

{
    echo "# BEGIN DAO_VANG_MANAGED"
    echo "*/2 * * * * cd $PROJECT_DIR && flock -n data/watchdog.lock python3 scripts/production_watchdog.py --apply >> data/watchdog.log 2>&1"
    echo "10 2 * * * cd $PROJECT_DIR && bash scripts/backup_to_gdrive.sh"
    echo "0 4 * * * cd $PROJECT_DIR && bash scripts/prune_old_data.sh --apply >> data/prune.log 2>&1"
    echo "# END DAO_VANG_MANAGED"
} >> "$proposed"

echo "Proposed production crontab:"
diff -u "$existing" "$proposed" || true

if (( apply == 0 )); then
    echo "Dry run only. Re-run with --apply to install this managed block."
    exit 0
fi

backup_dir="$PROJECT_DIR/backups/crontab"
mkdir -p "$backup_dir"
cp "$existing" "$backup_dir/crontab-$(date +'%Y%m%d_%H%M%S').txt"
crontab "$proposed"
echo "Production cron installed; previous crontab was backed up to $backup_dir"
