#!/usr/bin/env python3
"""Frozen SWE policy matrix; every completed patch is officially graded.

Example: uv run python scripts/run_swe_online_comparison.py --output runs/swe-policy-v2
Add --execute explicitly to invoke local models; use Linux/WSL2 for SWE on Windows.
"""

import sys

from veritas.cli import main

if __name__ == "__main__":
    sys.argv = [
        "veritas",
        "compare",
        "--config",
        "configs/policy-comparison-swe.yaml",
        *sys.argv[1:],
    ]
    main()
