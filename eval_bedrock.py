import json
import os
import glob
import argparse
import boto3
from prettytable import PrettyTable
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

GRADER_TEMPLATE = """
Judge whether the following [response] to [question] is correct or not based on the precise and unambiguous [correct_answer] below.

[question]: {question}

[response]: {response}

Your judgement must be in the format and criteria specified below:

extracted_final_answer: The final exact answer extracted from the [response]. Put the extracted answer as 'None' if there is no exact, final answer to extract from the response.

[correct_answer]: {correct_answer}

reasoning: Explain why the extracted_final_answer is correct or incorrect based on [correct_answer], focusing only on if there are meaningful differences between [correct_answer] and the extracted_final_answer. Do not comment on any background to the problem, do not attempt to solve the problem, do not argue for any answer different than [correct_answer], focus only on whether the answers match.

correct: Answer 'yes' if extracted_final_answer matches the [correct_answer] given above, or is within a small margin of error for numerical problems. Answer 'no' otherwise, i.e. if there is any inconsistency, ambiguity, non-equivalency, or if the extracted answer is incorrect.

confidence: The extracted confidence score between 0% and 100% from [response]. Put 100 if there is no confidence score available.
""".strip()


def call_bedrock(client, model_id, prompt, max_tokens=1024):
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "anthropic_version": "bedrock-2023-05-31",
    }
    response = client.invoke_model(
        body=json.dumps(payload),
        modelId=model_id,
    )
    body = json.loads(response["body"].read())
    return body["content"][0]["text"]


def parse_judge_response(text: str) -> dict:
    import re

    result = {"extracted_final_answer": None, "reasoning": None,
              "correct": None, "confidence": None, "parse_error": False}

    if not text:
        result["parse_error"] = True
        return result

    def _find(pattern):
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else None

    result["extracted_final_answer"] = (
        _find(r"\*\*extracted_final_answer:\*\*\s*(.*?)(?=\n|$)")
        or _find(r"\*\*extracted_final_answer\*\*:\s*(.*?)(?=\n|$)")
        or _find(r"extracted_final_answer:\s*(.*?)(?=\n|$)")
    )
    result["reasoning"] = (
        _find(r"\*\*reasoning:\*\*\s*(.*?)(?=\n\*\*correct[:\*]|\ncorrect:|$)")
        or _find(r"reasoning:\s*(.*?)(?=\ncorrect:|$)")
    )
    correct_raw = (
        _find(r"\*\*correct:\*\*\s*(yes|no)")
        or _find(r"\*\*correct\*\*:\s*(yes|no)")
        or _find(r"correct:\s*(yes|no)")
    )
    if correct_raw:
        result["correct"] = correct_raw.lower() == "yes"

    conf_raw = (
        _find(r"\*\*confidence:\*\*\s*(\d+(?:\.\d+)?)\s*%?")
        or _find(r"\*\*confidence\*\*:\s*(\d+(?:\.\d+)?)\s*%?")
        or _find(r"confidence:\s*(\d+(?:\.\d+)?)\s*%?")
    )
    if conf_raw:
        result["confidence"] = min(float(conf_raw), 100.0)

    if result["correct"] is None:
        result["parse_error"] = True

    return result


def get_final_response(entry: dict) -> str:
    if entry.get("final_response"):
        return entry["final_response"]
    for msg in reversed(entry.get("messages", [])):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def load_data(input_path: str) -> list:
    if os.path.isdir(input_path):
        files = [f for f in glob.glob(os.path.join(input_path, "*.jsonl"))
                 if not f.endswith("evaluated.jsonl")]
    else:
        files = [input_path]

    entries = {}
    for fpath in files:
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                entries[d["qid"]] = d
    return list(entries.values())


def judge_one(args_tuple):
    client, model_id, entry, max_retries = args_tuple
    qid = entry["qid"]
    question = entry["question"]
    answer = entry["answer"]
    response_text = get_final_response(entry)
    prompt = GRADER_TEMPLATE.format(
        question=question,
        response=response_text,
        correct_answer=answer,
    )
    for attempt in range(1, max_retries + 1):
        try:
            raw = call_bedrock(client, model_id, prompt)
            result = parse_judge_response(raw)
            result["qid"] = qid
            result["question"] = question
            result["gen_output"] = response_text
            result["correct_answer"] = answer
            result["raw_judge"] = raw
            return result
        except Exception as e:
            if attempt == max_retries:
                return {"qid": qid, "correct": False, "parse_error": True, "error": str(e)}
            import time
            time.sleep(2 ** attempt)


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate results using Claude via AWS Bedrock")
    parser.add_argument("--input", required=True,
                        help="JSONL file or directory of JSONL files to evaluate")
    parser.add_argument("--output", default=None,
                        help="Output JSONL path (default: <input_dir>/evaluated.jsonl)")
    parser.add_argument("--model", default="anthropic.claude-sonnet-4-5-20251001-v1:0",
                        help="Bedrock model ID")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--max-workers", type=int, default=64)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser.parse_args()


def main():
    args = parse_args()

    if args.output:
        output_file = args.output
        output_dir = os.path.dirname(output_file) or "."
    elif os.path.isdir(args.input):
        output_dir = args.input
        output_file = os.path.join(args.input, "evaluated.jsonl")
    else:
        output_dir = os.path.dirname(args.input) or "."
        output_file = os.path.join(output_dir, "evaluated.jsonl")

    data = load_data(args.input)
    print(f"Loaded {len(data)} entries")

    clean_data = [d for d in data if d.get("status") in ("completed", "success")
                  and d.get("question") and d.get("answer")]
    error_data = [d for d in data if d not in clean_data]
    print(f"Success: {len(clean_data)}  |  Skipped/Error: {len(error_data)}")

    if not clean_data:
        print("Nothing to judge.")
        return

    client = boto3.client("bedrock-runtime", region_name=args.region)
    judge_args = [(client, args.model, d, args.max_retries) for d in clean_data]

    outputs = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = [ex.submit(judge_one, a) for a in judge_args]
        for f in tqdm(as_completed(futures), total=len(futures), desc="Judging"):
            outputs.append(f.result())

    # Save (strip verbose fields)
    strip_keys = {"extracted_final_answer", "reasoning", "confidence", "parse_error", "raw_judge"}
    saved = [{k: v for k, v in r.items() if k not in strip_keys} for r in outputs]
    saved.sort(key=lambda x: x.get("qid") or 0)

    os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for item in saved:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"\nSaved to: {output_file}")

    # Metrics
    parsed = [x for x in outputs if not x.get("parse_error")]
    correct = [x for x in parsed if x.get("correct") is True]
    incorrect = [x for x in parsed if x.get("correct") is False]

    total = len(data)
    n_success = len(clean_data)
    n_parsed = len(parsed)
    n_parse_err = len(outputs) - n_parsed
    n_correct = len(correct)

    table = PrettyTable()
    table.title = "Evaluation Results"
    table.field_names = ["Metric", "Count", "Rate"]
    table.align = "l"
    table.align["Count"] = "r"
    table.align["Rate"] = "r"
    table.add_row(["Total samples", total, ""])
    table.add_row(["  Successful runs", n_success, f"{n_success/total:.1%}"])
    table.add_row(["  Skipped/error", total - n_success, f"{(total-n_success)/total:.1%}"])
    table.add_row(["-"*28, "-"*7, "-"*8], divider=True)
    table.add_row(["Judged", len(outputs), ""])
    table.add_row(["  Parsed OK", n_parsed, f"{n_parsed/len(outputs):.1%}" if outputs else ""])
    table.add_row(["  Parse error", n_parse_err, f"{n_parse_err/len(outputs):.1%}" if outputs else ""])
    table.add_row(["-"*28, "-"*7, "-"*8], divider=True)
    table.add_row(["Correct", n_correct, ""])
    table.add_row(["Judged accuracy (correct/parsed)", "", f"{n_correct/n_parsed:.1%}" if n_parsed else "N/A"])
    table.add_row(["Overall accuracy (correct/total)", "", f"{n_correct/total:.1%}" if total else "N/A"])
    print("\n" + str(table))

    # Turn stats
    qid_map = {d["qid"]: d for d in clean_data}

    def avg_turns(items):
        counts = [sum(1 for m in qid_map[x["qid"]]["messages"] if m.get("role") == "assistant")
                  for x in items if x.get("qid") in qid_map]
        if not counts:
            return "N/A", "N/A"
        return f"{sum(counts)/len(counts):.1f}", f"{sorted(counts)[len(counts)//2]}"

    c_mean, c_med = avg_turns(correct)
    i_mean, i_med = avg_turns(incorrect)
    print(f"\nTurns — Correct: mean={c_mean} median={c_med} | Incorrect: mean={i_mean} median={i_med}")


if __name__ == "__main__":
    main()

"""
ada credentials update --provider=conduit --account=684288478426 --role=RufusScienceConduitRole --once --profile=default
"""