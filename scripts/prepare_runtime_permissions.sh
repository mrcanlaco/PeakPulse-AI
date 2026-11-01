#!/usr/bin/env bash
# Align bind-mounted data ownership with the non-root runtime user.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${DAO_VANG_PROJECT_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
RUNTIME_UID="${DAO_VANG_RUNTIME_UID:-$(id -u)}"
RUNTIME_GID="${DAO_VANG_RUNTIME_GID:-$(id -g)}"
CLOUDFLARED_GID="${DAO_VANG_CLOUDFLARED_GID:-65532}"
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

[[ "$RUNTIME_UID" =~ ^[0-9]+$ ]] || {
    echo "Runtime UID must be numeric" >&2
    exit 2
}
[[ "$RUNTIME_GID" =~ ^[0-9]+$ ]] || {
    echo "Runtime GID must be numeric" >&2
    exit 2
}
[[ "$CLOUDFLARED_GID" =~ ^[0-9]+$ ]] || {
    echo "Cloudflared GID must be numeric" >&2
    exit 2
}

PROJECT_DIR="$(realpath -e "$PROJECT_DIR")"
for directory in "$PROJECT_DIR/data" "$PROJECT_DIR/artifacts"; do
    mkdir -p "$directory"
    resolved="$(realpath -e "$directory")"
    case "$resolved" in
        "$PROJECT_DIR/data"|"$PROJECT_DIR/artifacts") ;;
        *)
            echo "Refusing unsafe permission target: $resolved" >&2
            exit 1
            ;;
    esac

    if find "$resolved" -xdev \( ! -uid "$RUNTIME_UID" -o ! -gid "$RUNTIME_GID" \) -print -quit | grep -q . || find "$resolved" -xdev -perm /0007 -print -quit | grep -q .; then
        if (( apply == 0 )); then
            echo "Needs ownership update: $resolved -> $RUNTIME_UID:$RUNTIME_GID"
        else
            sudo -n chown -R "$RUNTIME_UID:$RUNTIME_GID" "$resolved"
            sudo -n chmod -R u+rwX,g+rX,o-rwx "$resolved"
            if find "$resolved" -xdev \( ! -uid "$RUNTIME_UID" -o ! -gid "$RUNTIME_GID" \) -print -quit | grep -q . || find "$resolved" -xdev -perm /0007 -print -quit | grep -q .; then
                echo "Permission migration did not converge: $resolved" >&2
                exit 1
            fi
            echo "Updated ownership: $resolved -> $RUNTIME_UID:$RUNTIME_GID"
        fi
    else
        echo "Ownership already correct: $resolved"
    fi
done

env_file="$PROJECT_DIR/.env.docker"
if [[ -f "$env_file" ]]; then
    env_state="$(stat -c '%u:%g:%a' "$env_file")"
    expected_env_state="$RUNTIME_UID:$RUNTIME_GID:600"
    if [[ "$env_state" != "$expected_env_state" ]]; then
        if (( apply == 0 )); then
            echo "Needs secret-file update: $env_file -> $expected_env_state"
        else
            sudo -n chown "$RUNTIME_UID:$RUNTIME_GID" "$env_file"
            sudo -n chmod 600 "$env_file"
            [[ "$(stat -c '%u:%g:%a' "$env_file")" == "$expected_env_state" ]] || {
                echo "Secret-file permission update failed: $env_file" >&2
                exit 1
            }
            echo "Secured secret file: $env_file"
        fi
    fi
fi

cloudflared_dir="$PROJECT_DIR/cloudflared"
if [[ -d "$cloudflared_dir" ]]; then
    if (( apply == 0 )); then
        echo "Cloudflared files will be owner-readable and group-readable by GID $CLOUDFLARED_GID"
    else
        sudo -n chown -R "$RUNTIME_UID:$CLOUDFLARED_GID" "$cloudflared_dir"
        sudo -n find "$cloudflared_dir" -type d -exec chmod 750 {} +
        sudo -n find "$cloudflared_dir" -type f -exec chmod 640 {} +
        echo "Secured cloudflared files: $cloudflared_dir"
    fi
fi

if (( apply == 0 )); then
    echo "Dry run only. Re-run with --apply before starting non-root containers."
fi
