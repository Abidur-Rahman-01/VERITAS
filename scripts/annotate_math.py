"""Conservative math annotation. Never auto-labels intermediate actions."""

import argparse
import json

from veritas.labels import annotate_math_queue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default="artifacts/annotation-queue.jsonl")
    parser.add_argument("--tasks", default="data/prepared")
    parser.add_argument("--output", default="artifacts/annotations-safe.jsonl")
    args = parser.parse_args()
    result = annotate_math_queue(args.queue, args.tasks, args.output)
    print(json.dumps(result, indent=2))
    print("Unknown actions require independent semantic review before replay. No labels invented.")


if __name__ == "__main__":
    main()
