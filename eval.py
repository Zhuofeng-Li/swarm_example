"""
Evaluation script for swarm_example benchmark results.

Supports two result formats:
  1. Single-agent JSONL: each line is {"qid", "question", "answer", "status",
     "final_response", "num_steps", "messages", "elapsed_seconds", ...}
  2. Multi-agent JSONL: each line is {"main": [...messages], "subs": [...]}
     paired with a separate questions file for ground truth.

Usage:
  # Single-agent results (e.g. browsecomp):
  python eval.py --input result/browsecomp/results.jsonl

  # Directory of single-agent JSONL files:
  python eval.py --input result/browsecomp/

  # Multi-agent result with separate questions file:
  python eval.py --input result/maink2.5_subk2.5.jsonl --questions browsecomp_questions.jsonl
"""

import argparse
import json
import os
import random
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import anthropic
import openai
import dotenv
from prettytable import PrettyTable
from tqdm import tqdm

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# LLM grader prompt (mirrors OpenResearcher's grader for compatibility)
# ---------------------------------------------------------------------------

GRADER_TEMPLATE = """
Judge whether the following [response] to [question] is correct or not based on the precise and unambiguous [correct_answer] below.

[question]: {question}

[response]: {response}

Your judgement must be in the format and criteria specified below:

extracted_final_answer: The final exact answer extracted from the [response]. Put the extracted answer as 'None' if there is no exact, final answer to extract from the response.

[correct_answer]: {correct_answer}

reasoning: Explain why the extracted_final_answer is correct or incorrect based on [correct_answer], focusing only on if there are meaningful differences between [correct_answer] and the extracted_final_answer. Do not comment on any background to the problem, do not attempt to solve the problem, do not argue for any answer different than [correct_answer], focus only on whether the answers match.

correct: Answer 'yes' if extracted_final_answer matches the [correct_answer] given above, or is within a small margin of error for numerical problems. Answer 'no' otherwise, i.e. if there if there is any inconsistency, ambiguity, non-equivalency, or if the extracted answer is incorrect.

confidence: The extracted confidence score between 0% and 100% from [response]. Put 100 if there is no confidence score available.
""".strip()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_judge_response(judge_response: str) -> dict:
    result = {
        "extracted_final_answer": None,
        "reasoning": None,
        "correct": None,
        "confidence": None,
        "parse_error": False,
    }

    if not judge_response:
        result["parse_error"] = True
        return result

    def _search(pattern, text):
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else None

    result["extracted_final_answer"] = (
        _search(r"\*\*extracted_final_answer:\*\*\s*(.*?)(?=\n|$)", judge_response)
        or _search(r"\*\*extracted_final_answer\*\*:\s*(.*?)(?=\n|$)", judge_response)
        or _search(r"extracted_final_answer:\s*(.*?)(?=\n|$)", judge_response)
    )

    result["reasoning"] = (
        _search(r"\*\*reasoning:\*\*\s*(.*?)(?=\n\*\*correct[:\*]|\ncorrect:|$)", judge_response)
        or _search(r"\*\*reasoning\*\*:\s*(.*?)(?=\n\*\*correct[:\*]|\ncorrect:|$)", judge_response)
        or _search(r"reasoning:\s*(.*?)(?=\ncorrect:|$)", judge_response)
    )

    correct_raw = (
        _search(r"\*\*correct:\*\*\s*(yes|no)", judge_response)
        or _search(r"\*\*correct\*\*:\s*(yes|no)", judge_response)
        or _search(r"correct:\s*(yes|no)", judge_response)
    )
    if correct_raw:
        result["correct"] = correct_raw.lower() == "yes"

    conf_raw = (
        _search(r"\*\*confidence:\*\*\s*(\d+(?:\.\d+)?)\s*%?", judge_response)
        or _search(r"\*\*confidence\*\*:\s*(\d+(?:\.\d+)?)\s*%?", judge_response)
        or _search(r"confidence:\s*(\d+(?:\.\d+)?)\s*%?", judge_response)
    )
    if conf_raw:
        result["confidence"] = min(float(conf_raw), 100.0)

    if result["correct"] is None:
        result["parse_error"] = True

    return result


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class ThreadRateLimiter:
    def __init__(self, qps: float):
        self.capacity = max(1, int(qps))
        self.tokens = float(self.capacity)
        self.refill_rate = qps
        self.timestamp = time.perf_counter()
        self.lock = Lock()

    def acquire(self):
        with self.lock:
            now = time.perf_counter()
            self.tokens = min(self.capacity, self.tokens + (now - self.timestamp) * self.refill_rate)
            self.timestamp = now
            wait = max(0.0, (1 - self.tokens) / self.refill_rate)
        if wait:
            time.sleep(wait)
        with self.lock:
            now2 = time.perf_counter()
            self.tokens = min(self.capacity, self.tokens + (now2 - self.timestamp) * self.refill_rate)
            self.timestamp = now2
            self.tokens -= 1


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

KIMI_MODELS = {"kimi-k2.5", "kimi-k2-0711-preview", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"}


class LLMJudge:
    def __init__(self, model="kimi-k2.5", qps=50, max_retries=5):
        self.model = model
        self.max_retries = max_retries
        self.rate_limiter = ThreadRateLimiter(qps)

        if model in KIMI_MODELS or "kimi" in model or "moonshot" in model:
            self.client = openai.OpenAI(
                api_key=os.getenv("KIMI_API_KEY"),
                base_url="https://api.moonshot.ai/v1",
            )
            self.backend = "openai_compat"
        else:
            self.client = anthropic.Anthropic()
            self.backend = "anthropic"

    def judge(self, data: list) -> list:
        results = []
        with ThreadPoolExecutor(max_workers=50) as ex:
            futures = [ex.submit(self._judge_one, d) for d in data]
            for f in tqdm(as_completed(futures), total=len(futures), desc="Judging"):
                results.append(f.result())
        return results

    def _judge_one(self, data: dict) -> dict:
        question = data["question"]
        answer = data["answer"]
        response_text = _extract_final_response(data)
        prompt = GRADER_TEMPLATE.format(
            question=question,
            response=response_text,
            correct_answer=answer,
        )
        for attempt in range(1, self.max_retries + 1):
            self.rate_limiter.acquire()
            try:
                if self.backend == "openai_compat":
                    completion = self.client.chat.completions.create(
                        model=self.model,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = completion.choices[0].message.content
                else:
                    message = self.client.messages.create(
                        model=self.model,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = message.content[0].text

                resp = parse_judge_response(raw)
                resp["qid"] = data["qid"]
                resp["question"] = question
                resp["gen_output"] = response_text
                resp["correct_answer"] = answer
                resp["raw_judge"] = raw
                return resp
            except Exception as e:
                if attempt == self.max_retries:
                    return {"qid": data["qid"], "correct": False, "parse_error": True, "error": str(e)}
                time.sleep(0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.2))


# ---------------------------------------------------------------------------
# Result file loading
# ---------------------------------------------------------------------------

def _extract_final_response(entry: dict) -> str:
    """Pull the agent's final text response from a single-agent entry."""
    if entry.get("final_response"):
        return entry["final_response"]
    messages = entry.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def load_results(path: str, questions_path: str | None = None) -> list:
    """
    Load result entries into a unified list of dicts with keys:
      qid, question, answer, status, final_response, messages, num_steps, elapsed_seconds
    """
    entries = []

    if os.path.isdir(path):
        import glob
        files = [f for f in glob.glob(os.path.join(path, "*.jsonl"))
                 if not f.endswith("evaluated.jsonl")]
    else:
        files = [path] if not path.endswith("evaluated.jsonl") else []

    # Optionally load ground-truth questions for multi-agent files
    qid_to_qa: dict = {}
    if questions_path and os.path.isfile(questions_path):
        with open(questions_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                q = json.loads(line)
                qid_to_qa[q["qid"]] = q

    for fpath in files:
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)

                # Multi-agent format: {"main": [...messages], "subs": [...]}
                if "main" in raw and "subs" in raw and "qid" not in raw:
                    entry = _parse_multiagent_entry(raw, qid_to_qa)
                    if entry:
                        entries.append(entry)
                else:
                    entries.append(raw)

    # Deduplicate by qid (keep last occurrence)
    seen: dict = {}
    for e in entries:
        seen[e.get("qid")] = e
    return list(seen.values())


def _parse_multiagent_entry(raw: dict, qid_to_qa: dict) -> dict | None:
    """Convert multi-agent storage format to unified eval format."""
    main_messages = raw.get("main", [])
    # Try to find qid from messages or fall back to sequential assignment
    qid = raw.get("qid")

    qa = qid_to_qa.get(qid, {}) if qid is not None else {}
    question = raw.get("question", qa.get("question", ""))
    answer = raw.get("answer", qa.get("answer", ""))

    # Extract final response from last assistant message
    final_response = ""
    for msg in reversed(main_messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            final_response = content if isinstance(content, str) else " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
            break

    status = raw.get("status", "completed")
    num_steps = raw.get("num_steps", sum(
        1 for m in main_messages if m.get("role") == "assistant"
    ))

    return {
        "qid": qid,
        "question": question,
        "answer": answer,
        "status": status,
        "final_response": final_response,
        "messages": main_messages,
        "num_steps": num_steps,
        "elapsed_seconds": raw.get("elapsed_seconds"),
        "subs": raw.get("subs", []),
    }


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def count_assistant_turns(messages: list) -> int:
    return sum(1 for m in messages if m.get("role") == "assistant")


def count_tool_calls(messages: list) -> Counter:
    counts: Counter = Counter()
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                name = tc.get("function", {}).get("name", "unknown")
                counts[name] += 1
    return counts


def print_turn_statistics(correct_turns: list, incorrect_turns: list):
    print("\n" + "=" * 60)
    print("Turn Distribution Analysis")
    print("=" * 60)

    def _stats(label, turns):
        if not turns:
            return
        n = len(turns)
        mean = sum(turns) / n
        median = sorted(turns)[n // 2]
        print(f"\n{label} (n={n}):")
        print(f"  Mean:   {mean:.2f}")
        print(f"  Median: {median:.2f}")
        print(f"  Min:    {min(turns)}")
        print(f"  Max:    {max(turns)}")

    _stats("Correct Answers", correct_turns)
    _stats("Incorrect Answers", incorrect_turns)
    print("=" * 60)


def print_tool_statistics(correct_items: list, incorrect_items: list, qid_to_data: dict):
    all_correct: Counter = Counter()
    all_incorrect: Counter = Counter()

    for item in correct_items:
        all_correct += count_tool_calls(qid_to_data.get(item["qid"], {}).get("messages", []))
    for item in incorrect_items:
        all_incorrect += count_tool_calls(qid_to_data.get(item["qid"], {}).get("messages", []))

    all_tools = sorted(set(all_correct) | set(all_incorrect))
    if not all_tools:
        return

    nc = len(correct_items) or 1
    ni = len(incorrect_items) or 1

    print("\n" + "=" * 60)
    print("Tool Usage Analysis (avg per question)")
    print("=" * 60)
    print(f"{'Tool':<30} {'Correct':>10} {'Incorrect':>10}")
    print("-" * 52)
    for tool in all_tools:
        print(f"{tool:<30} {all_correct[tool]/nc:>10.2f} {all_incorrect[tool]/ni:>10.2f}")
    print("=" * 60)


def create_plots(correct_turns: list, incorrect_turns: list, output_dir: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        plot_dir = os.path.join(output_dir.rstrip("/"), "plots")
        os.makedirs(plot_dir, exist_ok=True)

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for ax, turns, color, label in [
            (axes[0], correct_turns, "green", "Correct"),
            (axes[1], incorrect_turns, "red", "Incorrect"),
        ]:
            if not turns:
                ax.set_title(f"{label} (n=0)")
                continue
            ax.hist(turns, bins=30, alpha=0.7, color=color, edgecolor="black")
            ax.axvline(np.mean(turns), color="darkred", linestyle="--",
                       linewidth=2, label=f"Mean: {np.mean(turns):.1f}")
            ax.axvline(np.median(turns), color="blue", linestyle="--",
                       linewidth=2, label=f"Median: {np.median(turns):.1f}")
            ax.set_xlabel("Number of Turns")
            ax.set_ylabel("Frequency")
            ax.set_title(f"{label} Answers (n={len(turns)})")
            ax.legend()
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        out = os.path.join(plot_dir, "turn_distribution.png")
        plt.savefig(out, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"\nTurn distribution plot saved to: {out}")
    except ImportError:
        print("\nNote: install matplotlib to generate plots.")
    except Exception as e:
        print(f"\nWarning: could not generate plots: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate swarm agent benchmark results")
    parser.add_argument("--input", required=True,
                        help="Path to a results JSONL file or directory containing JSONL files")
    parser.add_argument("--questions",
                        help="Path to questions JSONL for multi-agent result files (needs qid/question/answer)")
    parser.add_argument("--output",
                        help="Output path for evaluated JSONL (default: <input_dir>/evaluated.jsonl)")
    parser.add_argument("--model", default="kimi-k2.5",
                        help="Judge model: Kimi (kimi-k2.5, kimi-k2-0711-preview, moonshot-*) or Anthropic (claude-*)")
    parser.add_argument("--qps", type=float, default=200, help="Rate limit (queries per second)")
    parser.add_argument("--no-plots", action="store_true", help="Skip generating plots")
    args = parser.parse_args()

    # Resolve output path
    if args.output:
        output_file = args.output
        output_dir = os.path.dirname(output_file) or "."
    elif os.path.isdir(args.input):
        output_dir = args.input
        output_file = os.path.join(args.input, "evaluated.jsonl")
    else:
        output_dir = os.path.dirname(args.input) or "."
        output_file = os.path.join(output_dir, "evaluated.jsonl")

    # Load results
    data = load_results(args.input, args.questions)
    print(f"Loaded {len(data)} entries from {args.input}")

    # Skip entries without question/answer (can't judge)
    judged_data = [d for d in data if d.get("question") and d.get("answer")]
    skipped = len(data) - len(judged_data)
    if skipped:
        print(f"Skipped {skipped} entries missing question or answer fields")

    clean_data = [d for d in judged_data if d.get("status") in ("completed", "success")]
    error_data = [d for d in judged_data if d not in clean_data]

    print(f"\nTotal samples:   {len(data)}")
    print(f"Success samples: {len(clean_data)}")
    print(f"Error samples:   {len(error_data)}")

    if not clean_data:
        print("\nNo successful samples to judge. Exiting.")
        return

    judge = LLMJudge(model=args.model, qps=args.qps)
    output = judge.judge(clean_data)

    # Save results (drop verbose fields)
    saved = []
    for item in output:
        saved.append({k: v for k, v in item.items()
                      if k not in ("extracted_final_answer", "reasoning", "confidence",
                                   "parse_error", "raw_judge")})
    saved.sort(key=lambda x: x.get("qid") or 0)

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for item in saved:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"\nResults saved to: {output_file}")

    # Metrics
    parsed_output = [x for x in output if not x.get("parse_error")]
    correct_list = [x for x in parsed_output if x.get("correct") is True]
    incorrect_list = [x for x in parsed_output if x.get("correct") is False]

    total = len(data)
    n_success = len(clean_data)
    n_error = len(error_data)
    n_parsed = len(parsed_output)
    n_parse_err = len(output) - n_parsed
    n_correct = len(correct_list)

    success_rate = n_success / total if total else 0
    parse_err_rate = n_parse_err / len(output) if output else 0
    judged_acc = n_correct / n_parsed if n_parsed else 0
    overall_acc = n_correct / total if total else 0

    table = PrettyTable()
    table.title = "Evaluation Results Summary"
    table.field_names = ["Metric", "Count", "Percentage"]
    table.align = "l"
    table.align["Count"] = "r"
    table.align["Percentage"] = "r"
    table.add_row(["Total Samples", total, "100.00%"])
    table.add_row(["  - Success", n_success, f"{success_rate:.2%}"])
    table.add_row(["  - Error", n_error, f"{1 - success_rate:.2%}"])
    table.add_row(["-" * 25, "-" * 8, "-" * 12], divider=True)
    table.add_row(["Judged Samples", len(output), "100% of Success"])
    table.add_row(["  - Parsed OK", n_parsed, f"{1 - parse_err_rate:.2%}"])
    table.add_row(["  - Parse Error", n_parse_err, f"{parse_err_rate:.2%}"])
    table.add_row(["-" * 25, "-" * 8, "-" * 12], divider=True)
    table.add_row(["Correct Predictions", n_correct, ""])
    table.add_row(["Judged Accuracy (Correct/Parsed)", "", f"{judged_acc:.2%}"])
    table.add_row(["Overall Accuracy (Correct/Total)", "", f"{overall_acc:.2%}"])
    print("\n" + str(table))

    # Turn/tool analysis
    qid_to_data = {d["qid"]: d for d in clean_data}

    correct_turns = [count_assistant_turns(qid_to_data[x["qid"]]["messages"])
                     for x in correct_list if x["qid"] in qid_to_data]
    incorrect_turns = [count_assistant_turns(qid_to_data[x["qid"]]["messages"])
                       for x in incorrect_list if x["qid"] in qid_to_data]

    print_turn_statistics(correct_turns, incorrect_turns)
    print_tool_statistics(correct_list, incorrect_list, qid_to_data)

    if not args.no_plots and (correct_turns or incorrect_turns):
        create_plots(correct_turns, incorrect_turns, output_dir)


if __name__ == "__main__":
    main()
