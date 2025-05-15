#!/usr/bin/env bash

#set -x
set -euo pipefail

clear

pushd ../../frontend
npm run dev
popd
