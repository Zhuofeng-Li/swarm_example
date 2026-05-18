#!/usr/bin/env python3
"""Compute all standard comparison metrics between two agent runs.

Usage:
    uv run python compute_metrics.py <dir_a> <dir_b> [--label-a NAME] [--label-b NAME]

Each directory must contain:
    - results.jsonl   (per-question runtime: qid, status, metrics, messages)
    - evaluated.jsonl (per-question correctness: qid, correct, gen_output, correct_answer)
"""
import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def pct(values, p):
    s = sorted(values)
    if not s:
        return 0
    return s[int(len(s) * p / 100)]


def stats_block(values, label):
    if not values:
        return f"  {label}: (no data)"
    return (
        f"  {label}: mean={statistics.mean(values):.1f}, "
        f"median={statistics.median(values):.1f}, "
        f"p90={pct(values,90):.1f}, max={max(values):.1f}"
    )


def analyze(dir_a: Path, dir_b: Path, label_a: str, label_b: str):
    a_results = load_jsonl(dir_a / "results.jsonl")
    b_results = load_jsonl(dir_b / "results.jsonl")
    a_eval    = load_jsonl(dir_a / "evaluated.jsonl")
    b_eval    = load_jsonl(dir_b / "evaluated.jsonl")

    a_map  = {r["qid"]: r for r in a_results}
    b_map  = {r["qid"]: r for r in b_results}
    a_em   = {e["qid"]: e for e in a_eval}
    b_em   = {e["qid"]: e for e in b_eval}

    print("=" * 70)
    print(f"GROUND TRUTH COUNTS")
    print("=" * 70)
    print(f"{label_a}: results={len(a_results)}, eval={len(a_eval)}, "
          f"statuses={dict(Counter(r['status'] for r in a_results))}")
    print(f"{label_b}: results={len(b_results)}, eval={len(b_eval)}, "
          f"statuses={dict(Counter(r['status'] for r in b_results))}")

    a_run, b_run = set(a_map), set(b_map)
    a_eq,  b_eq  = set(a_em),  set(b_em)
    common = a_eq & b_eq

    print(f"\n{label_a} ran {len(a_run)} | {label_b} ran {len(b_run)}")
    print(f"Not run in {label_b}: {sorted(a_run - b_run)}")
    print(f"{label_b} run but not evaluated: {sorted(b_run - b_eq)}")
    print(f"Common evaluated: {len(common)}")

    print("\n" + "=" * 70)
    print("ACCURACY")
    print("=" * 70)
    a_correct = sum(1 for e in a_eval if e["correct"])
    b_correct = sum(1 for e in b_eval if e["correct"])
    print(f"{label_a}: {a_correct}/{len(a_eval)} = {a_correct/len(a_eval)*100:.1f}%")
    print(f"{label_b}: {b_correct}/{len(b_eval)} = {b_correct/len(b_eval)*100:.1f}%")
    if common:
        ac = sum(1 for q in common if a_em[q]["correct"])
        bc = sum(1 for q in common if b_em[q]["correct"])
        print(f"On common {len(common)}: "
              f"{label_a}={ac}/{len(common)}={ac/len(common)*100:.1f}%, "
              f"{label_b}={bc}/{len(common)}={bc/len(common)*100:.1f}%")

    print("\n" + "=" * 70)
    print("LATENCY")
    print("=" * 70)
    for key in ("elapsed_seconds", "num_turns", "num_tool_calls"):
        a_v = [r["metrics"].get(key) for r in a_results if r["metrics"].get(key) is not None]
        b_v = [r["metrics"].get(key) for r in b_results if r["metrics"].get(key) is not None]
        print(f"\n{key}:")
        print(stats_block(a_v, label_a))
        print(stats_block(b_v, label_b))

    print("\n" + "=" * 70)
    print("ELAPSED BY CORRECTNESS")
    print("=" * 70)
    for label, eval_map, results_map in [
        (label_a, a_em, a_map), (label_b, b_em, b_map),
    ]:
        ce = [results_map[q]["metrics"]["elapsed_seconds"]
              for q in eval_map if eval_map[q]["correct"]]
        we = [results_map[q]["metrics"]["elapsed_seconds"]
              for q in eval_map if not eval_map[q]["correct"]]
        ce_mean = statistics.mean(ce) if ce else 0
        we_mean = statistics.mean(we) if we else 0
        ratio = we_mean / ce_mean if ce_mean else 0
        print(f"{label}: correct n={len(ce)} mean={ce_mean:.1f}s | "
              f"wrong n={len(we)} mean={we_mean:.1f}s | ratio={ratio:.1f}x")

    print("\n" + "=" * 70)
    print("CATEGORIZATION (common evaluated subset)")
    print("=" * 70)
    both_right = sorted(q for q in common if a_em[q]["correct"] and b_em[q]["correct"])
    both_wrong = sorted(q for q in common if not a_em[q]["correct"] and not b_em[q]["correct"])
    only_a     = sorted(q for q in common if a_em[q]["correct"] and not b_em[q]["correct"])
    only_b     = sorted(q for q in common if not a_em[q]["correct"] and b_em[q]["correct"])
    print(f"Both correct ({len(both_right)}): {both_right}")
    print(f"Both wrong   ({len(both_wrong)}): {both_wrong}")
    print(f"Only {label_a} correct ({len(only_a)}): {only_a}")
    print(f"Only {label_b} correct ({len(only_b)}): {only_b}")

    print("\n" + "=" * 70)
    print("SUBAGENT USAGE (B-side, if available)")
    print("=" * 70)
    sub_counts = [r["metrics"].get("num_subagents") for r in b_results
                  if "num_subagents" in r.get("metrics", {})]
    if sub_counts:
        dist = Counter(sub_counts)
        for k in sorted(dist):
            print(f"  {k} subagents: {dist[k]} questions")
        used = sum(1 for c in sub_counts if c > 0)
        print(f"Used subagents: {used}/{len(sub_counts)} "
              f"({used/len(sub_counts)*100:.0f}%)")
    else:
        print(f"{label_b} has no num_subagents metric.")

    print("\n" + "=" * 70)
    print("INVESTIGATE NEXT: per-question deep dives needed for")
    print("=" * 70)
    print(f"  Only-{label_b}-correct: {only_b}")
    print(f"  Only-{label_a}-correct: {only_a}")
    print("Use trace_messages.py <dir> <qid> to inspect message logs.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir_a")
    ap.add_argument("dir_b")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    args = ap.parse_args()
    analyze(Path(args.dir_a), Path(args.dir_b), args.label_a, args.label_b)


if __name__ == "__main__":
    main()
