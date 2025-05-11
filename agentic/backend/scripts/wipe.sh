#!/usr/bin/env bash

set -euo pipefail

clear

#----------------------------------------
# Remove local DBs (quiet if already gone)
#----------------------------------------

shopt -s nullglob
db_files=(../../data/dbs/*)
if ((${#db_files[@]})); then
  rm -v ../../data/dbs/*
else
  echo "No DB files to remove in ../../data/dbs/"
fi
shopt -u nullglob

#----------------------------------------
# Delete NATS JetStream stream & consumer
#----------------------------------------

# If nats CLI is not installed, exit with error
if ! command -v nats &>/dev/null; then
  echo "ERROR: 'nats' CLI not found in PATH."
  exit 1
fi

NATS_SERVER="nats://localhost:4222"

# Delete consumer if it exists
if nats --server "$NATS_SERVER" consumer info STREAM_TOOLS TOOLS_EXEC_REQ &>/dev/null; then
  nats --server "$NATS_SERVER" consumer delete --force STREAM_TOOLS TOOLS_EXEC_REQ
else
  echo "No consumer STREAM_TOOLS > TOOLS_EXEC_REQ to delete."
fi

# Delete stream if it exists
if nats --server "$NATS_SERVER" stream info STREAM_TOOLS &>/dev/null; then
  nats --server "$NATS_SERVER" stream delete --force STREAM_TOOLS
else
  echo "No stream STREAM_TOOLS to delete."
fi

echo "Cleanup complete."
