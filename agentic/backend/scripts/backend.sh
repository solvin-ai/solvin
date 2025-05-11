#!/usr/bin/env bash

#set -x
set -euo pipefail

clear

# Always resolve paths relative to this script file itself
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." &> /dev/null && pwd)"
DATA_PATH="$(realpath "$REPO_ROOT/../data")"

export MY_START_SH_MARKER="my-microservice-bundle"

echo "Resolved DATA_PATH: $DATA_PATH"

mkdir -p "$DATA_PATH/logs"
ALL_TERM_LOG="$DATA_PATH/logs/all-terminal.log"
rm -f "$ALL_TERM_LOG"
touch "$ALL_TERM_LOG"

# Check for unbuffer (from expect package)
if ! command -v unbuffer > /dev/null 2>&1; then
  echo "ERROR: 'unbuffer' not found! Please run: sudo apt-get install expect"
  exit 1
fi

# Define all services: name port optional extra_env
SERVICES=(
  "configs 8010 SERVICE_URL_CONFIGS=http://localhost:8010"
  "repos   8002"
  "agents  8000"
  "tools   8001"
)

echo "==== Debug: SERVICES to be launched ===="
for svc in "${SERVICES[@]}"; do
  echo "  $svc"
done

echo "==== Killing leftover uvicorn processes (if any)... ===="
for svc in "${SERVICES[@]}"; do
  IFS=' ' read -r name port _ <<<"$svc"
  uvicorn_pids=$( \
    lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null \
      | xargs -r ps -o pid,comm= \
      | grep uvicorn || true \
      | awk '{print $1}' \
  )
  for upid in $uvicorn_pids; do
    if [[ "$upid" =~ ^[0-9]+$ ]]; then
      echo "Process tree for old uvicorn on port $port (PID $upid):"
      pstree -ps "$upid" 2>/dev/null || true
      ppid=$(ps -o ppid= -p "$upid" | tr -d ' ')
      if [[ -n "$ppid" && "$ppid" != "1" && "$ppid" =~ ^[0-9]+$ ]]; then
        echo "Killing supervisor process $ppid (parent of uvicorn pid $upid) for port $port"
        kill -9 "$ppid" 2>/dev/null || true
      fi
      kill -9 "$upid" 2>/dev/null || true
    else
      echo "Warning: Skipping invalid PID '$upid' for port $port"
    fi
  done
done
echo "==== Done with leftover processes. ===="
sleep 2

echo "==== Waiting for all ports to become available ===="
for svc in "${SERVICES[@]}"; do
  IFS=' ' read -r name port _ <<<"$svc"
  for i in {1..10}; do
    if ! lsof -i TCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    echo "Waiting up to $((10 - i + 1))s for port $port to be released..."
    sleep 1
  done
done
echo "==== All ports are now available. ===="

# ---- TEMPLATE ----
TEMPLATE() {
  local name="$1" port="$2" extra_env="${3:-}"
  local dir="$REPO_ROOT/services/${name}/src"
  local mod="service_${name}"
  local env_vars="SERVICE_NAME=service_${name} MY_START_SH_MARKER=$MY_START_SH_MARKER"
  [[ -n "$extra_env" ]] && env_vars="$env_vars $extra_env"
  echo "$name|$dir|$mod|$port|$env_vars"
}

# ---- Wait for /health to become available ----
wait_for_health() {
  local port="$1"
  for i in {1..30}; do
    if curl -fs "http://localhost:$port/health" >/dev/null \
      || curl -fs "http://localhost:$port/api/v1/health" >/dev/null; then
      echo "Service at port $port responded to /health."
      return 0
    fi
    echo "Waiting for /health at :$port ($i/30)..."
    sleep 1
  done
  echo "Health check failed for $port"
  return 1
}

# ---- SUPERVISE FUNCTION WITH DEBUG LOG ----
supervise() {
  local name="$1" dir="$2" mod="$3" port="$4" envs="$5"
  export MY_START_SH_MARKER
  while :; do
    pushd "$dir" > /dev/null
    source venv/bin/activate
    echo "($name) [supervise $$] starting on :$port (launching: uvicorn $mod:app)"
    echo "($name) [supervise $$] ENV: $envs"
    unbuffer env $envs \
      uvicorn "$mod:app" \
        --host 0.0.0.0 --port "$port" \
        --no-access-log --use-colors \
        --log-level debug --reload \
    2>&1 | tee -a "$ALL_TERM_LOG"
    local exit_code=$?
    popd > /dev/null
    echo "($name) [supervise $$] crashed (exit $exit_code), restarting..." | tee -a "$ALL_TERM_LOG"
    sleep 2
  done
}

# Arrays to track supervisor shell PIDs and their process‐group IDs
pids=()
pgids=()

echo "==== Debug: Launching supervisor for each service ===="
for svc in "${SERVICES[@]}"; do
  IFS=' ' read -r n1 n2 n3 <<<"$svc"
  name="$n1"
  port="$n2"
  extra_env="${n3:-}"

  IFS="|" read -r name dir mod port env_vars < <(TEMPLATE "$name" "$port" "$extra_env")

  echo "Launching supervisor for $name in $dir module $mod on $port env='$env_vars'"

  (
    supervise "$name" "$dir" "$mod" "$port" "$env_vars"
  ) &
  sup_pid=$!
  pids+=("$sup_pid")
  sleep 0.5
  pgid=$(ps -o pgid= "$sup_pid" | tr -d ' ')
  pgids+=("$pgid")

  wait_for_health "$port"
done

echo "==== Debug: All supervisors launched, listing processes ===="
ps aux | grep '[u]vicorn' || true
echo "==== Running bash supervise procs: ===="
ps aux | grep '[b]ash' | grep -E 'service_.*:app' || true
ps aux | grep "$MY_START_SH_MARKER" || true
echo "==== If you see your services here, everything is running! ===="

# Trap SIGINT (Ctrl+C) only; killing the child process‐groups
trap '
  echo "Stopping all services..."
  for pgid in "${pgids[@]:-}"; do
    echo "Killing PGID $pgid"
    kill -TERM -"$pgid" 2>/dev/null || true
  done
  exit 0
' SIGINT

wait
