#!/usr/bin/env bash
# XeroPi4 — run directly via:
# curl -fsSL https://raw.githubusercontent.com/YOUR_USER/XeroPi4/main/run.sh | bash
set -euo pipefail

TARBALL_URL="https://github.com/XeroLinux/XeroArchArm/archive/refs/heads/main.tar.gz"
INSTALL_DIR="$HOME/.local/share/XeroArchArm"
DEPS=(python python-pyside6 curl libarchive uboot-tools polkit)

_info() { printf '\e[1;34m::\e[0m %s\n' "$*"; }
_die()  { printf '\e[1;31mERROR\e[0m %s\n' "$*" >&2; exit 1; }

# ── dependency check ──────────────────────────────────────────────────────────

MISSING=()
for dep in "${DEPS[@]}"; do
    pacman -Q "$dep" &>/dev/null || MISSING+=("$dep")
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
    _info "Installing dependencies: ${MISSING[*]}"
    sudo pacman -S --noconfirm --needed "${MISSING[@]}"
fi

# ── download and extract ──────────────────────────────────────────────────────

_info "Downloading XeroPi4…"
mkdir -p "$INSTALL_DIR"
curl -fsSL "$TARBALL_URL" \
    | tar -xz --strip-components=1 -C "$INSTALL_DIR"

# ── polkit policy (only needed once, re-runs are harmless) ────────────────────

_info "Installing polkit policy (requires sudo)…"
sudo bash "$INSTALL_DIR/worker/install.sh"

# ── launch ────────────────────────────────────────────────────────────────────

exec python "$INSTALL_DIR/main.py" "$@"
