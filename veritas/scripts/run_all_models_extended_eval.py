"""Compatibility entry point for real runtime sweeps (no simulated measurements).

Use --config configs/suite.yaml --output runs/runtime-matrix --execute.
"""
import sys

from veritas.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "suite")
    main()
