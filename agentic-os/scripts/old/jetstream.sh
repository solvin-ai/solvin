#!/usr/bin/env bash

set -euo pipefail

clear

pushd ../../backend/services/3rd-party/jetstream/
docker-compose up
popd
