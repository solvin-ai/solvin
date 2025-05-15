#!/usr/bin/env bash

#set -x
set -euo pipefail

clear

declare -A services=(
    [3000]="frontend"
    [8222]="jetstream"
    [8010]="configs"
    [8000]="agents"
    [8001]="tools"
    [8002]="repos"
)

for port in "${!services[@]}"; do
    name="${services[$port]}"
    if ss -lnt "( sport = :$port )" | grep -q LISTEN; then
        echo "$name ($port): LISTENING"
    else
        echo "$name ($port): --"
    fi
done
