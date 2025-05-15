#!/usr/bin/env bash

set -e
clear

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES_ROOT="$(realpath "$SCRIPT_DIR/../backend/services")"

# Default list of targets if none provided as argument
TARGET_LIST="${1:-agents,tools,repos,configs}"
IFS=',' read -ra TARGETS <<< "$TARGET_LIST"

for target in "${TARGETS[@]}"; do
    target=$(xargs <<< "$target")  # trim whitespace

    # Extract the service name (the part before the first '/')
    SERVICE="${target%%/*}"
    service_dir="$SERVICES_ROOT/$SERVICE/src"
    tests_dir="$service_dir/tests"
    venv_activate="$service_dir/venv/bin/activate"

    if [[ "$target" == *"/"* ]]; then
        # file or file::test (e.g. tools/test_x.py or tools/test_x.py::test_foo)
        subpath="${target#*/}"
        test_target="$service_dir/$subpath"
        if [[ ! -e "$test_target" && ! "$test_target" =~ "::" ]]; then
            echo "Test file or test not found: $test_target"
            continue
        fi
    else
        # plain service name
        if [ ! -d "$service_dir" ]; then
            echo "Directory not found: $service_dir"
            continue
        fi

        # GENERALIZED: any service with a tests/ directory
        if [ -d "$tests_dir" ]; then
            test_target="tests/"
        elif [ -f "$service_dir/test_${SERVICE}.py" ]; then
            test_target="test_${SERVICE}.py"
        else
            echo "No tests found for $SERVICE"
            continue
        fi
    fi

    cd "$service_dir"
    echo "=== Running tests for $target ==="
    [[ -f $venv_activate ]] && source "$venv_activate"

    SERVICE_NAME="service_${SERVICE}" \
    SOLVIN_CONFIG_DEBUG=1 \
    pytest --capture=no --log-level=DEBUG --verbose \
           --color=yes --code-highlight=yes \
           "$test_target" 2>&1
done
