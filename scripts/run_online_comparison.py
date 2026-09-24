#!/usr/bin/env python3
"""Compatibility entry point for the frozen, resumable policy matrix.

Example: uv run python scripts/run_online_comparison.py --output runs/policy-v2
Add --execute explicitly to invoke local models, or --resume / --report later.
"""

import sys

from veritas.cli import main

if __name__ == "__main__":
    sys.argv = ["veritas", "compare", "--config", "configs/policy-comparison.yaml", *sys.argv[1:]]
    main()
