#!/usr/bin/env bash
# Copy to the verified persistent CQA root, then use as the existing Pod's startup command.
set -euo pipefail
CQA_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
CQA_RELEASE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release"])' "$CQA_ROOT/config/runtime.json")"
exec "$CQA_RELEASE/backend/.venv/bin/python" "$CQA_RELEASE/scripts/production_bootstrap.py" --root "$CQA_ROOT"
