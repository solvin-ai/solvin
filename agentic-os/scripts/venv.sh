#!/usr/bin/env bash

set -euo pipefail
clear

# =============================================================================
# Rebuild all Python virtual environments for each service directory.
# Detects whether your login shell is Bash or Fish and uses the matching
# activation script when installing requirements.
# =============================================================================

# Find this script’s directory and the services root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SERVICES_ROOT="$(realpath "$SCRIPT_DIR/../backend")"

# List of directories in which to (re)create virtualenvs
targets=(
  "$SERVICES_ROOT"
  "$SERVICES_ROOT/services/agents/src"
  "$SERVICES_ROOT/services/configs/src"
  "$SERVICES_ROOT/services/repos/src"
  "$SERVICES_ROOT/services/tools/src"
)

# Detect the user’s login shell (fallback to bash)
shell_name="$(basename "${SHELL:-bash}")"
case "$shell_name" in
  fish)
    ACTIVATOR="venv/bin/activate.fish"
    SHELL_CMD="fish"
    ;;
  *)
    ACTIVATOR="venv/bin/activate"
    SHELL_CMD="bash"
    DEACTIVATOR="deactivate"
    ;;
esac

echo "Detected login shell: $shell_name"
echo "Using activation script: $ACTIVATOR"
echo

for t in "${targets[@]}"; do
  echo "======================"
  echo "Rebuilding venv in: $t"
  (
    cd "$t" || { echo "ERROR: Could not cd to $t"; exit 1; }
    rm -rf venv/
    python3 -m venv venv
    echo "  → created venv"

    if [ -f requirements.txt ]; then
      echo "  → installing from requirements.txt"
      if [ "$SHELL_CMD" = "fish" ]; then
        # Fish: spawn a fish shell, source the fish activator, then pip install
        fish -c "source $ACTIVATOR; pip install --upgrade pip; pip install -r requirements.txt"
      else
        # Bash (or POSIX): spawn bash, source the activator, install, then deactivate
        bash -c "source $ACTIVATOR; pip install --upgrade pip; pip install -r requirements.txt; $DEACTIVATOR"
      fi
      echo "  → dependencies installed"
    else
      echo "  → no requirements.txt found, skipping pip install"
    fi
  )
  echo "$t venv done."
  echo
done

echo "All venvs rebuilt successfully."
