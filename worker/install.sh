#!/usr/bin/env bash
# Install the XeroPi4 polkit policy.
# Run once as root after cloning/moving the project.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER="$SCRIPT_DIR/flash_worker.py"
POLICY_SRC="$SCRIPT_DIR/xeropi4-flash.policy.template"
POLICY_DST="/usr/share/polkit-1/actions/com.techxero.xeropi4.policy"

if [[ $EUID -ne 0 ]]; then
    echo "error: run as root  (sudo $0)" >&2
    exit 1
fi

if [[ ! -f "$WORKER" ]]; then
    echo "error: worker not found at $WORKER" >&2
    exit 1
fi

chmod +x "$WORKER"

sed "s|WORKER_PATH_PLACEHOLDER|$WORKER|g" "$POLICY_SRC" > "$POLICY_DST"
chmod 644 "$POLICY_DST"

echo "Policy installed : $POLICY_DST"
echo "Worker           : $WORKER"
echo "Done. XeroPi4 flash action is now authorized via polkit."
