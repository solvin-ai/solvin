#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

#─── helpers ────────────────────────────────────────────────────────────────────
info(){ printf "⏩ %s\n" "$*"; }
die (){ printf "❌ ERROR: %s\n" "$*" >&2; exit 1; }

#─── locate dirs ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"

#─── sanity ─────────────────────────────────────────────────────────────────────
command -v pipx >/dev/null || die "pipx is not installed; please install pipx first."

#─── work in backend ────────────────────────────────────────────────────────────
pushd "$BACKEND_DIR" >/dev/null

info "Cleaning build artifacts…"
rm -rf build/ dist/ *.egg-info/ || true

info "Uninstalling any existing solvin…"
pipx uninstall solvin \
  && info "✅ solvin uninstalled" \
  || info "ℹ️  solvin was not installed"

info "Installing solvin in editable mode via pipx…"
pipx install --editable . --force

popd >/dev/null

info "✅ All done!"
