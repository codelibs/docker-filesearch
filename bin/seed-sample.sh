#!/bin/bash
# Generate the sample file tree (a sample company, "Codelibs, Inc."; every name, figure and text in it is generated) under
# data/files, which compose.yaml mounts read-only into Fess as /data/files.
#
#   bash bin/seed-sample.sh                 # generate (or regenerate in place)
#   bash bin/seed-sample.sh --clean         # remove the generated files first
#   SAMPLE_REFERENCE_DATE=today bash bin/seed-sample.sh
#                                           # make the newest file "today" instead of 2026-09-30
#
# The output is deterministic: the same seed and reference date always give the
# same files, contents and modification times.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v python3 >/dev/null || { echo "ERROR: python3 is required." >&2; exit 1; }

OUT=./data/files
if [ "${1:-}" = "--clean" ]; then
  # Empty the directory but keep it, so a running container's bind mount stays valid.
  [ -d "${OUT}" ] && find "${OUT}" -mindepth 1 -delete
fi
mkdir -p "${OUT}"

python3 ./bin/generate_sample.py --out "${OUT}" \
  --seed "${SAMPLE_SEED:-20260930}" \
  --reference-date "${SAMPLE_REFERENCE_DATE:-2026-09-30}"
