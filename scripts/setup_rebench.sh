#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Separate environment: the upstream fork and official swebench share a Python package name.
uv venv --python 3.12 .venv-rebench
uv pip install --python .venv-rebench/bin/python -e . \
  'swebench @ git+https://github.com/SWE-rebench/SWE-bench-fork.git@d307ff9f2168a0448843c0d5881d2cd498d9f73f'
.venv-rebench/bin/veritas doctor
