#!/usr/bin/env python3
"""Merge real exported/annotated records, rejecting duplicate IDs and partition leakage."""

import argparse
from collections import defaultdict
from pathlib import Path

from veritas.io import file_hash, read_records, write_json, write_jsonl
from veritas.schema import StepRecord


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", nargs="+")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    seen, groups = set(), defaultdict(set)

    def rows():
        for source in a.inputs:
            for row in read_records(source):
                record = StepRecord.model_validate(row)
                if record.event_id in seen:
                    raise ValueError(f"Duplicate event: {record.event_id}")
                seen.add(record.event_id)
                groups[record.group_id].add((record.split, record.calibration_role))
                if len(groups[record.group_id]) != 1:
                    raise ValueError(f"Partition leakage: {record.group_id}")
                yield record.model_dump(mode="json")

    write_jsonl(a.output, rows())
    write_json(
        a.output + ".manifest.json",
        {
            "input_sha256": {x: file_hash(Path(x)) for x in a.inputs},
            "rows": len(seen),
        },
    )


if __name__ == "__main__":
    main()
