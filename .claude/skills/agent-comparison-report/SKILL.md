---
name: agent-comparison-report
description: >
  Generate deep comparison reports between two LLM agent runs (e.g., Single Agent vs Swarm,
  Model A vs Model B) on a benchmark. Use this skill whenever the user wants to:
  - Compare results from two `results.jsonl` + `evaluated.jsonl` runs
  - Analyze accuracy, latency, and per-question outcomes between two agent configurations
  - Determine whether a multi-agent / Swarm mechanism actually contributed to wins
  - Produce a structured Chinese analysis report (Markdown by default; HTML only if user asks)

  Trigger phrases include: "对比这两个的结果", "分析这两次运行", "compare two runs",
  "swarm vs single agent", "哪些题答对/答错", "深度分析", "生成对比报告".
  Proactively invoke this skill when the user references two result directories
  containing `results.jsonl` / `evaluated.jsonl` files and asks for analysis.
---

# Agent Comparison Report Skill

Your goal: produce a rigorous, evidence-driven comparison report between two agent runs on the
same benchmark. The report must distinguish between **surface-level metric differences** and
**root-cause attributions** (e.g., did Swarm actually use subagents, or did it just behave like
a better Single Agent?).

The user must provide two result directories. Each directory should contain:

- `results.jsonl` — per-question runtime data (qid, status, metrics, messages)
- `evaluated.jsonl` — per-question correctness judgments (qid, correct, gen_output, correct_answer)

---

## Step 1: Establish Ground Truth Counts (Do Not Skip)

Before any analysis, count exactly what was run vs. evaluated. **Mismatch is common** — e.g.,
some questions may run but not be evaluated, or only a subset may have been run.

```python
import json
from collections import Counter

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f]

a_results = load_jsonl(f"{dir_a}/results.jsonl")
b_results = load_jsonl(f"{dir_b}/results.jsonl")
a_eval    = load_jsonl(f"{dir_a}/evaluated.jsonl")
b_eval    = load_jsonl(f"{dir_b}/evaluated.jsonl")

print(f"A: results={len(a_results)}, eval={len(a_eval)}, statuses={Counter(r['status'] for r in a_results)}")
print(f"B: results={len(b_results)}, eval={len(b_eval)}, statuses={Counter(r['status'] for r in b_results)}")

a_run_qids   = {r['qid'] for r in a_results}
b_run_qids   = {r['qid'] for r in b_results}
a_eval_qids  = {e['qid'] for e in a_eval}
b_eval_qids  = {e['qid'] for e in b_eval}
common_eval  = a_eval_qids & b_eval_qids
```

**Critical pitfalls to avoid:**

- Do NOT compute accuracy as `correct / total_questions` if one side ran fewer questions —
  always report **both** the absolute number (`X/50`) and the rate on **the comparable subset**
  (e.g., `X/28` on common evaluated questions).
- If `status == "max_steps_reached"`, the question was likely *not* evaluated. Verify by
  checking `eval_qids` set membership before claiming "X% accuracy".
- Always state the denominator explicitly (e.g., "27/28 = 96.4% on completed questions").

---

## Step 2: Required Metrics

Compute these and present them in tables:

### 2.1 Accuracy

| Dimension | A | B |
|---|---|---|
| Total questions | … | … |
| Correct (overall) | X / N = Y% | X / N = Y% |
| Correct (on common evaluated subset) | X / N = Y% | X / N = Y% |
| Not-completed | 0 | not_run + not_evaluated |

### 2.2 Latency / Efficiency

For `elapsed_seconds`, `num_turns`, `num_tool_calls`, report mean / median / p90 / max.
Use `statistics.mean`, `statistics.median`. For p90:

```python
def pct(lst, p):
    s = sorted(lst); return s[int(len(s) * p / 100)]
```

### 2.3 Correct vs Wrong Latency

Compute mean elapsed time on **correct-only** vs. **wrong-only** questions for each side.
A high "wrong-mean / correct-mean" ratio (e.g., 3×) signals the agent burns budget on dead
ends instead of failing fast.

### 2.4 Per-Question Categorization

Categorize the **common evaluated subset** into:

- Both correct
- Only A correct
- Only B correct
- Both wrong

List the actual qids in each bucket — these are the cases that need deep dives.

### 2.5 Swarm-Specific (if applicable)

If one side has `num_subagents` in metrics, report:

- Subagent count distribution (0 / 1+ / etc.)
- % of questions that actually used any subagent
- Mean elapsed for subagent-using vs. subagent-free questions

---

## Step 3: Deep Dive on "Only-One-Side-Correct" Questions

**This is the most important section.** A higher overall score does not prove a method
"works" — you must verify *why* it won each question.

For each question where only one side got it right:

1. **Pull the side-by-side metrics** (turns, tool_calls, elapsed, subagents, result).
2. **Read the assistant's final output** in `evaluated.jsonl[gen_output]` for both sides.
3. **For Swarm/multi-agent winners**: trace the message log to see when (if ever) subagents
   were created and whether their outputs *actually drove the answer*. Three possible verdicts:
   - **真正使用了 Swarm 机制** — subagent output directly produced the candidate answer
   - **部分使用了 Swarm 机制** — single-agent search found the answer; subagents only verified
   - **未使用 Swarm 机制** — `num_subagents == 0`, behavior identical to single agent
4. **Trace the failure mode of the losing side**: did it lock onto a wrong candidate early?
   Did it run out of steps? Did its search keywords go in circles?

To find subagent creation events:

```python
for i, msg in enumerate(messages):
    content = str(msg.get('content', ''))
    if 'Successfully created agent' in content:
        print(f"  msg[{i}]: {content[:200]}")
```

To trace search progression, iterate `messages` and print `(role, content[:300])` for every
`tool` and `assistant` message — this reveals the search keywords used at each step.

---

## Step 4: Report Structure

Produce the report in an `analysis/` directory at the workspace root.

**Default output: Markdown only** (`analysis/<benchmark_name>_analysis.md`). Do NOT generate
the HTML version unless the user explicitly asks for it ("生成 HTML", "也要 HTML", "html version
too"). The HTML build adds noise to most workflows because users typically want to read the
report in their editor or paste pieces into chat.

If — and only if — the user asks for HTML, also produce `analysis/<benchmark_name>_analysis.html`
using the conventions in Step 5.

### Required sections

1. **一、Metric 对比：Accuracy 与 Latency**
   - 1.1 Accuracy table (total + common-subset rates)
   - 1.2 Latency table (mean/median/p90/max for elapsed, turns, tool_calls)
   - 1.3 Correct-vs-wrong elapsed time
   - 1.4 (Optional) Subagent usage distribution

2. **二、题号全景总览** — categorization table with **explicit qid lists** in each bucket

3. **三、Per-case deep dive** — one card per "only-one-side-correct" question:
   - Side-by-side metrics table (Turns / Tool Calls / Elapsed / Subagents / Result)
   - **Verdict on whether the multi-agent mechanism was actually used**
   - For the most important case (e.g., the one that genuinely used Swarm): trace the
     phases — single-agent exploration → decision point → subagent creation → integration.
     Include a search-keyword timeline table.

4. **核心价值总结 / Conclusion** — what the data actually proves, separating signal from noise.

---

## Step 5: HTML Output Standards (only when explicitly requested)

Skip this step unless the user explicitly asks for an HTML version. When asked, use the
following style template for the HTML version (paste into `<style>` tag). Key visual
conventions:

- **Verdict badges**: `✅ 答对` (green), `❌ 答错` (red), `直接命中` (green), `未能锁定` (orange)
- **Conclusion boxes**:
  - Orange-tinted (`.conclusion`) for "did NOT use the multi-agent mechanism"
  - Green-tinted (`.conclusion-positive`) for "genuinely used and benefited from Swarm"
- **Case cards**: each per-question deep-dive in its own bordered card with a `qid-tag`
- **TOC at the top** with anchor links to each section and case
- **Code spans** (`<code>`) for search keywords and subagent names
- **`<em>` highlighted in yellow** for direct quotes from sources

Reference style (CSS variables, badge classes, case-card layout) is in
`templates/report.html` of this skill.

---

## Step 6: Best Practices and Anti-Patterns

### DO

- **Verify before claiming** — if you say "Swarm answered X correctly", confirm `num_subagents > 0`
  in the metrics AND that subagent output influenced the final answer.
- **State denominators** — always write "X/Y = Z%" never just "Z%".
- **List qids explicitly** — readers want to spot-check; don't hide behind aggregate counts.
- **Show search keyword evolution** — for the headline case, table out each query and result
  so the reader sees *why* single-agent got stuck.
- **Distinguish coverage failures from accuracy failures** — if Swarm didn't run 19 questions,
  its "54% overall" is misleading; report "96% on the 28 it actually completed".

### DON'T

- ❌ Do not claim Swarm "won" without checking `num_subagents`. A subagent count of 0 means
  Swarm won by virtue of being a better single-agent run — the architecture didn't help.
- ❌ Do not lump max_steps_reached questions into the "wrong" bucket without checking whether
  they were evaluated.
- ❌ Do not write only the bottom-line metric; the per-question categorization is where the
  actual insight lives.
- ❌ Do not generate the HTML report unless the user explicitly asks for it. Most users
  read the Markdown directly in their editor or chat — the HTML build is wasted effort.
- ❌ Do not invent verdicts. If a case is ambiguous, write "部分使用了 Swarm 机制" and explain.

### Additional checks learned from prior runs

- **Benchmark leakage**: when one side appears to "win" via a single decisive search hit,
  inspect the URLs in its tool results. arxiv papers, HuggingFace datasets, and GitHub repos
  about the benchmark itself frequently contain the answer in plaintext (e.g.,
  `huggingface.co/datasets/.../browsecomp-*`, `arxiv.org/.../deep-research`). If the winning
  side hit one of these, label the win as "data leakage, not capability" in the report.
- **Echo-chamber risk in early-dispatch Swarm**: if a Swarm run dispatches multiple subagents
  *before* the main agent has done any search of its own (msg index < 5), all subagents share
  the same un-validated framing. If they all return answers consistent with a wrong premise,
  the main agent often locks in. Look for this pattern when a Swarm run loses with high
  `num_subagents` — it can be a *negative* contribution from the multi-agent mechanism.
- **Verdict categories beyond the three**: in addition to "真正使用 / 部分使用 / 未使用 Swarm
  机制", consider a fourth: **"⚠️ Swarm 反向作用"** for cases where multi-agent dispatch
  actively hurt the answer (e.g., shared framing bias, parallel hallucination).

---

## Step 7: Closing the Loop

After writing both files, confirm with the user:

- The path to the HTML file
- A one-line summary of the headline finding (e.g., "Swarm 在完成的题中正确率 96.4% vs SA 64%，
  但仅有 1/5 的独家答对题真正受益于 subagent 机制")
- Open invitation to drill into specific qids if they want more analysis

If the user asks for the report in another language (e.g., English), translate the structure
but keep the analytical rigor identical.
