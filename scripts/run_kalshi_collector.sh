#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATASET_ROOT="${DATASET_ROOT:-$ROOT_DIR/data/kalshi}"
WATCHLIST_PATH="${WATCHLIST_PATH:-$DATASET_ROOT/watchlist.json}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-300}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PY_CACHE_PREFIX="${PY_CACHE_PREFIX:-$ROOT_DIR/.pycache}"

cd "$ROOT_DIR"

mkdir -p "$DATASET_ROOT" "$PY_CACHE_PREFIX"

exec env PYTHONPYCACHEPREFIX="$PY_CACHE_PREFIX" \
  "$PYTHON_BIN" -m kalshi_research.main collect-loop \
  --dataset-root "$DATASET_ROOT" \
  --watchlist-path "$WATCHLIST_PATH" \
  --interval-seconds "$INTERVAL_SECONDS"
