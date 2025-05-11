#!/usr/bin/env bash
set -euo pipefail

# Find script location, and thus repo root (parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

targets=(
    "$REPO_ROOT"
    "$REPO_ROOT/services/agents/src"
    "$REPO_ROOT/services/configs/src"
    "$REPO_ROOT/services/repos/src"
    "$REPO_ROOT/services/tools/src"
)

# Detect user's shell
shell_name="${SHELL:-bash}"
case "$(basename "$shell_name")" in
    fish) activator="venv/bin/activate.fish"; shell_cmd="fish";;
    *)    activator="venv/bin/activate";     shell_cmd="bash"; deactivator="deactivate";;
esac

for t in "${targets[@]}"; do
    echo "======================"
    echo "Rebuilding venv in $t"
    (
        cd "$t" || { echo "Could not cd to $t"; exit 1; }
        rm -rf venv/
        python -m venv venv

        if [ -f requirements.txt ]; then
            if [ "$shell_cmd" = "fish" ]; then
                fish -c "source $activator; pip install -r requirements.txt"
            else
                bash -c "source $activator; pip install -r requirements.txt; $deactivator"
            fi
        else
            echo "No requirements.txt in $t, skipping pip install."
        fi
    )
    echo "$t venv done."
done

echo "All venvs rebuilt."
