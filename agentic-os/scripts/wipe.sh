#!/usr/bin/env bash

set -euo pipefail

clear

#-------------------------------------------------------------------------------
# Locate our “data” directory (parent of dbs/ and repos/)
#-------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"

#-------------------------------------------------------------------------------
# 1) Remove local DB files (quiet if already gone)
#-------------------------------------------------------------------------------
shopt -s nullglob
db_files=("$DATA_DIR/dbs"/*)
if ((${#db_files[@]})); then
  echo "Removing DB files in $DATA_DIR/dbs/"
  rm -v "$DATA_DIR/dbs"/*
else
  echo "No DB files to remove in $DATA_DIR/dbs/"
fi
shopt -u nullglob

#-------------------------------------------------------------------------------
# 2) Wipe all subdirectories under repos/ (quiet if already gone)
#-------------------------------------------------------------------------------
shopt -s nullglob
repo_dirs=("$DATA_DIR/repos"/*)
if ((${#repo_dirs[@]})); then
  echo "Removing all subdirectories in $DATA_DIR/repos/"
  for dir in "${repo_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
      rm -rfv "$dir"
    fi
  done
else
  echo "No repos subdirectories to remove in $DATA_DIR/repos/"
fi
shopt -u nullglob

#-------------------------------------------------------------------------------
# 3) Delete NATS JetStream consumer & stream (if present)
#-------------------------------------------------------------------------------
if ! command -v nats &>/dev/null; then
  echo "ERROR: 'nats' CLI not found in PATH."
  exit 1
fi

NATS_SERVER="nats://localhost:${NATS_CLIENT_PORT:-4222}"

# consumer
if nats --server "$NATS_SERVER" consumer info STREAM_TOOLS TOOLS_EXEC_REQ &>/dev/null; then
  echo "Deleting consumer STREAM_TOOLS > TOOLS_EXEC_REQ"
  nats --server "$NATS_SERVER" consumer delete --force STREAM_TOOLS TOOLS_EXEC_REQ
else
  echo "No consumer STREAM_TOOLS > TOOLS_EXEC_REQ to delete."
fi

# stream
if nats --server "$NATS_SERVER" stream info STREAM_TOOLS &>/dev/null; then
  echo "Deleting stream STREAM_TOOLS"
  nats --server "$NATS_SERVER" stream delete --force STREAM_TOOLS
else
  echo "No stream STREAM_TOOLS to delete."
fi

echo "Cleanup complete."
