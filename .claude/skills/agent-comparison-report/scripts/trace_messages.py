#!/usr/bin/env python3
"""Trace the full message log for a single qid in a results.jsonl file.

Useful for deep-diving on "only-one-side-correct" questions to determine:
  - When (if ever) subagents were spawned
  - What search keywords drove the search
  - Where the failing side went off the rails

Usage:
    uv run python trace_messages.py <results_dir> <qid>
"""
import argparse
import json
from pathlib import Path


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def trace(results_dir: Path, qid: int):
    results = load_jsonl(results_dir / "results.jsonl")
    target = next((r for r in results if r["qid"] == qid), None)
    if target is None:
        print(f"qid={qid} not found in {results_dir}/results.jsonl")
        return

    metrics = target.get("metrics", {})
    print(f"=== qid={qid} ({results_dir.name}) ===")
    print(f"status={target.get('status')}, metrics={metrics}\n")

    msgs = target.get("messages", [])
    print(f"Total messages: {len(msgs)}\n")

    subagent_creations = []
    for i, msg in enumerate(msgs):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        if not content.strip():
            continue

        if "Successfully created agent" in content:
            subagent_creations.append((i, content[:200]))

        # Print non-empty assistant + tool messages succinctly
        if role in ("assistant", "tool"):
            preview = content[:400].replace("\n", " ")
            print(f"[{i}] {role.upper()}: {preview}")

    if subagent_creations:
        print("\n--- SUBAGENT CREATION EVENTS ---")
        for i, c in subagent_creations:
            print(f"  msg[{i}]: {c}")
    else:
        print("\n--- NO SUBAGENTS CREATED ---")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    ap.add_argument("qid", type=int)
    args = ap.parse_args()
    trace(Path(args.results_dir), args.qid)


if __name__ == "__main__":
    main()
