#!/usr/bin/env bash

#set -x
set -euo pipefail

clear

# Resolve paths relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SERVICES_ROOT="$(realpath "$SCRIPT_DIR/../../backend/services")"
DATA_DIR="$(realpath "$SCRIPT_DIR/../../data")"

export MY_START_SH_MARKER="my-microservice-bundle"

echo "Resolved DATA_DIR:    $DATA_DIR"
echo "Resolved SERVICES_ROOT: $SERVICES_ROOT"

mkdir -p "$DATA_DIR/logs"
ALL_TERM_LOG="$DATA_DIR/logs/all-terminal.log"
rm -f "$ALL_TERM_LOG" && touch "$ALL_TERM_LOG"

# check for unbuffer (from expect)
if ! command -v unbuffer >/dev/null 2>&1; then
  echo "ERROR: 'unbuffer' not found!  sudo apt-get install expect"
  exit 1
fi

# detect user’s login shell so we know which venv-activate script to use
shell_name="$(basename "${SHELL:-bash}")"
if [ "$shell_name" = "fish" ]; then
  ACTIVATE_SCRIPT="venv/bin/activate.fish"
  SHELL_CMD="fish"
else
  ACTIVATE_SCRIPT="venv/bin/activate"
  SHELL_CMD="bash"
fi
echo "Detected login shell: $shell_name → will use $ACTIVATE_SCRIPT"

# service definitions:  name, port, extra_env…
SERVICES=(
  "configs 8010 SERVICE_URL_CONFIGS=http://localhost:8010"
  "repos   8002"
  "agents  8000"
  "tools   8001"
)

echo "==== Services to be launched ===="
for svc in "${SERVICES[@]}"; do
  echo "  $svc"
done

#
# Clean up any old uvicorn processes listening on our ports
#
echo "==== Killing leftover uvicorn processes (if any)... ===="
for svc in "${SERVICES[@]}"; do
  IFS=' ' read -r name port _ <<<"$svc"
  uvicorn_pids=$(
    lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null \
      | xargs -r ps -o pid,comm= \
      | grep uvicorn || true \
      | awk '{print $1}'
  )
  for pid in $uvicorn_pids; do
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
      echo "Killing old uvicorn (PID $pid) on port $port"
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
done
sleep 2

#
# Wait for ports to be free
#
echo "==== Waiting for all ports to be released ===="
for svc in "${SERVICES[@]}"; do
  IFS=' ' read -r name port _ <<<"$svc"
  for i in {1..10}; do
    if ! lsof -i TCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    echo " Port $port still in use, retrying… ($i/10)"
    sleep 1
  done
done

#
# helper: build a “|”-separated tuple for each service
#
TEMPLATE(){
  local name="$1" port="$2" extra="$3"
  local dir="$SERVICES_ROOT/$name/src"
  local mod="service_$name"
  local envs="SERVICE_NAME=$mod MY_START_SH_MARKER=$MY_START_SH_MARKER"
  [[ -n "$extra" ]] && envs="$envs $extra"
  echo "$name|$dir|$mod|$port|$envs"
}

#
# helper: wait for HTTP health endpoint
#
wait_for_health(){
  local p="$1"
  for i in {1..30}; do
    if curl -fs "http://localhost:$p/health" \
         || curl -fs "http://localhost:$p/api/v1/health"; then
      echo "  port $p → healthy!"
      return 0
    fi
    echo "  waiting for health on port $p… ($i/30)"
    sleep 1
  done
  echo "Health check FAILED for port $p"
  return 1
}

#
# supervise loop: start uvicorn, log to $ALL_TERM_LOG, restart on crash
#
supervise(){
  local name="$1" dir="$2" mod="$3" port="$4" envs="$5"
  while :; do
    if [ "$SHELL_CMD" = "fish" ]; then
      echo "[$name][fish] starting on :$port" | tee -a "$ALL_TERM_LOG"
      fish -c "
        cd '$dir'
        source '$ACTIVATE_SCRIPT'
        echo '[$name][fish] ENV: $envs'
        unbuffer env $envs \
          uvicorn $mod:app \
            --host 0.0.0.0 --port $port \
            --no-access-log --use-colors --log-level debug --reload
      " 2>&1 | tee -a "$ALL_TERM_LOG"
      exit_code=${PIPESTATUS[0]}
    else
      pushd "$dir" >/dev/null
      source "$ACTIVATE_SCRIPT"
      echo "[$name][bash] starting on :$port" | tee -a "$ALL_TERM_LOG"
      echo "[$name][bash] ENV: $envs" | tee -a "$ALL_TERM_LOG"
      unbuffer env $envs \
        uvicorn "$mod:app" \
          --host 0.0.0.0 --port "$port" \
          --no-access-log --use-colors --log-level debug --reload \
      2>&1 | tee -a "$ALL_TERM_LOG"
      exit_code=${PIPESTATUS[0]}
      popd >/dev/null
    fi

    echo "[$name] crashed (exit $exit_code), restarting in 2s…" | tee -a "$ALL_TERM_LOG"
    sleep 2
  done
}

# launch one supervisor per service
declare -a pgids
echo "==== Launching supervisors ===="
for svc in "${SERVICES[@]}"; do
  IFS=' ' read -r n p extra <<<"$svc"
  IFS="|" read -r name dir mod port envs < <(TEMPLATE "$n" "$p" "$extra")

  echo "Launching $name @ port $port"
  (
    supervise "$name" "$dir" "$mod" "$port" "$envs"
  ) &

  pid=$!
  pgids+=("$(ps -o pgid= $pid | tr -d ' ')")
  wait_for_health "$port"
done

# final status
echo "==== All services launched ===="
ps aux | grep '[u]vicorn' || true

# on CTRL-C, clean up entire process groups
trap '
  echo "Stopping all services…"
  for pg in "${pgids[@]}"; do
    kill -TERM -"$pg" 2>/dev/null || true
  done
  exit 0
' SIGINT

wait
