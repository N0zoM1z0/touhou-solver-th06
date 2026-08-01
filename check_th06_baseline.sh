#!/usr/bin/env bash
set -euo pipefail

TH06_REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$TH06_REPO_DIR"

export PYTHONPATH="$TH06_REPO_DIR/scripts"
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -c 'import th06.agent, th06.native, th06.safety, th06.solver, th06.ranking'
git diff --check

echo "TH06 focused checkpoint passed."
