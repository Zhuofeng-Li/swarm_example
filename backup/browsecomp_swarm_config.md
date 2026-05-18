# BrowseComp Multi-Agent Swarm 配置分析

> 基于 Kimi K2.5 Technical Report + 当前 codebase 分析

---

## 1. Paper 中的 Multi-Agent 架构

Paper 的 AgentSwarm 是 **Orchestrator + 并行 Sub-Agent** 结构：

```
用户问题
  └── Orchestrator（主 Agent）
        ├── 将问题分解为 N 个子任务
        ├── Sub-Agent A（搜索方向 A）
        ├── Sub-Agent B（搜索方向 B）
        ├── Sub-Agent C（搜索方向 C）
        └── 汇总结果 → 最终答案
```

目标分数：Single Agent 60.6% → Swarm 进一步提升。

---

## 2. 各层 Agent 参数设置

### 2.1 Orchestrator（主 Agent）

| 参数 | 值 | 说明 |
|---|---|---|
| model_id | `kimi-k2.5` | 同 single agent |
| temperature | `1.0` | Paper 规定 |
| top_p | `0.95` | Paper 规定 |
| max_tokens | `8192` | 同 single agent |
| max_steps | `15` | 主要做分解和汇总，步数不需太多 |
| tools | `SearchTool, BrowseTool, CreateSubagentTool, TaskTool` | 比 single agent 多两个 swarm 工具 |

### 2.2 Sub-Agent（子 Agent）

| 参数 | 值 | 说明 |
|---|---|---|
| model_id | `kimi-k2.5` | 与主 agent 相同 |
| temperature | `1.0` | 继承自父 agent |
| top_p | `0.95` | **当前代码未传递，是 bug** |
| max_tokens | `8192` | 继承自父 agent |
| max_steps | `100~150` | 每个子任务需要足够步数做深度搜索 |
| tools | `SearchTool, BrowseTool` | 不含 swarm 工具（防止递归） |
| system_prompt | BrowseComp 研究 prompt | 与 single agent 相同，专注执行分配的子任务 |

### 2.3 并发设置

| 参数 | 值 | 说明 |
|---|---|---|
| max_concurrency | `15~20` | 1 个问题 = 1 orchestrator + 3~5 sub-agents，API 调用是 single agent 的 4~6 倍 |

> **注意**：Swarm 模式下 RPM 消耗远高于 single agent，`max_concurrency=40` 的 single agent 设置在 swarm 下需降至 `15~20`。

---

## 3. System Prompt 设计

> 结构参考 `run_examples/run_kimi_kimi.py` 的 `SYSTEM_PROMPT`，在其基础上加入 BrowseComp 专用要求。

### 3.1 Orchestrator Prompt

```
You are an autonomous AI agent designed for complex, multi-step research tasks.
Today's date: {DATE}.

## Core Principles
1. **Think step-by-step**: Break down the question into independent search angles
2. **Use tools wisely**: Choose the most appropriate tool for each step
3. **Verify results**: Cross-check findings from multiple sub-agents
4. **Iterate as needed**: Refine approach based on sub-agent results
5. **Report findings**: Synthesize all sub-agent results into a final answer

## Sub-Agent Delegation Guidelines
This is a **Very Difficult** research problem. You MUST use sub-agents:
1. Analyze the question and identify 3-5 independent search angles
2. Use create_subagent to create agents with specific research focus
3. Use assign_task to dispatch ALL sub-agents IN PARALLEL (call assign_task multiple times simultaneously, do NOT wait for one to finish before starting another)
4. Synthesize results from all sub-agents to answer the question

## Response Format
Your final response must follow this format exactly:
Explanation: {your explanation synthesized from sub-agent findings, with inline citations [1]}
Exact Answer: {your succinct, final answer}
Confidence: {your confidence score between 0% and 100%}
```

> **注意**：去掉了 `## Available Tools` 列表——工具名、描述、参数 schema 已通过 API 的 `tools` 字段传给模型，prompt 里重复列举只是冗余 token。

### 3.2 Sub-Agent Prompt（复用 single agent BrowseComp prompt）

> 与 `browsecomp_single_agent.py` 的 `SYSTEM_PROMPT_TEMPLATE` 完全一致，sub-agent 专注执行分配的子任务。

```
You are Kimi, today's date: {DATE}.
Your task is to help the user with their questions by using various tools,
thinking deeply, and ultimately answering the user's questions.
Please follow the following principles strictly during the deep research:
1. Always focus on the user's original question during the research process,
   avoiding deviating from the topic.
2. When facing uncertain information, use search tools to confirm.
3. When searching, filter high-trust sources (such as authoritative websites,
   academic databases, and professional media) and maintain a critical mindset
   towards low-trust sources.
4. When performing numerical calculations, prioritize using programming tools
   to ensure accuracy.
5. Please use the format [^index^] to cite any information you use.
6. This is a **Very Difficult** problem--do not underestimate it. You must use
   tools to help your reasoning and then solve the problem.
7. Before you finally give your answer, please recall what the question is
   asking for.
```

> **注意**：sub-agent prompt 通过 `create_subagent` 工具在运行时动态注入，由 orchestrator 调用时传入。实现时在 `SUBAGENT_PROMPT` 常量中定义，orchestrator 的 system prompt 里告知其使用此 prompt 创建 sub-agent。

---

## 4. 当前代码需要修改的地方

### 4.1 `swarm_tool/task.py` — 三处参数传递问题（line 136-144）

**问题一：`top_p` 完全缺失**
**问题二：`temperature` fallback 为 `0.7`，kimi-k2.5 要求 `1.0`**
**问题三：`max_tokens` fallback 为 `4096`，应与 `AgentConfig` 默认值 `8192` 对齐**

```python
# 当前（有问题）
subagent_config = AgentConfig(
    name=subagent_id,
    system_prompt=system_prompt,
    model_id=subagent_model,
    api_key=subagent_api_key,
    api_base_url=subagent_base_url,
    max_tokens=self.parent_agent.config.max_tokens if self.parent_agent else 4096,   # fallback 太小
    temperature=self.parent_agent.config.temperature if self.parent_agent else 0.7,  # fallback 错误
    # top_p 完全缺失！
)

# 修复后
subagent_config = AgentConfig(
    name=subagent_id,
    system_prompt=system_prompt,
    model_id=subagent_model,
    api_key=subagent_api_key,
    api_base_url=subagent_base_url,
    max_tokens=self.parent_agent.config.max_tokens if self.parent_agent else 8192,
    temperature=self.parent_agent.config.temperature if self.parent_agent else 1.0,
    top_p=self.parent_agent.config.top_p if self.parent_agent else 0.95,  # 新增
)
```

### 4.2 `swarm_tool/task.py` — `terminal_mode` 应由调用方控制

**位置**：line 166-170

`SubRolloutConfig` 默认值是 `terminal_mode=True`（`sub_rollout.py` line 17），`TaskTool` 硬编码传入 `terminal_mode=True`，批量评测时会打印海量输出。

```python
# 当前（硬编码，无法从外部控制）
rollout_config = SubRolloutConfig(
    max_steps=self.max_steps,
    step_hint=True,
    terminal_mode=True,
)

# 修复：让调用方传入，默认 False
# TaskTool.__init__ 增加 terminal_mode 参数
def __init__(self, ..., max_steps: int = 100, terminal_mode: bool = False):

rollout_config = SubRolloutConfig(
    max_steps=self.max_steps,
    step_hint=True,
    terminal_mode=self.terminal_mode,
)
```

> 注意：`SubRolloutConfig` 默认值也需改为 `terminal_mode=False`（`sub_rollout.py` line 17）

### 4.3 `swarm_tool/task.py` — sub-agent `max_steps` 默认值太低

**位置**：line 26（TaskTool `__init__`）

```python
# 当前（SubRolloutConfig 默认 20，TaskTool 默认也是 20）
def __init__(self, ..., max_steps: int = 20):

# BrowseComp sub-agent 建议
def __init__(self, ..., max_steps: int = 100):
```

### 4.4 `rollout/base.py` — `RolloutConfig.max_steps` 默认值偏低

**位置**：line 24

```python
# 当前
max_steps: int = 50

# BrowseComp Orchestrator 建议（主 rollout 用）
max_steps: int = 50  # 保持不变，在调用处显式传 max_steps=50~80 即可
```

> 这里实际不需要改默认值，但需要在 `browsecomp_swarm.py` 脚本里显式指定，避免依赖默认值。

### 4.5 改写 `examples/multi_agent.py` 为 BrowseComp Swarm 评测脚本

对标 `browsecomp_single_agent.py` 的结构，分块说明：

**① 修正 `sys.path`**
现在多插了一层 `dirname`，路径会出错，需改为与 `browsecomp_single_agent.py` 一致：
```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

**② imports 补全**
新增：`CreateSubagentTool`, `TaskTool`, `BrowseTool`, `load_browsecomp`, `_decrypt`

**③ 两套 System Prompt（硬编码）**
- `ORCHESTRATOR_PROMPT`：见第 3.1 节
- `SUBAGENT_PROMPT`：复用 single agent 的 BrowseComp 研究 prompt（见第 3.2 节）

**④ `process_item` 核心逻辑**
```
每道题创建：
  agent_registry = {}
  search_tool, browse_tool
  create_subagent_tool = CreateSubagentTool(agent_registry)
  task_tool = TaskTool(agent_registry, max_steps=args.sub_max_steps, terminal_mode=False)

  orchestrator AgentConfig:
    system_prompt = ORCHESTRATOR_PROMPT
    temperature=1.0, top_p=0.95, max_tokens=8192

  task_tool.set_parent_agent(agent)
  task_tool.set_parent_tools([search_tool, browse_tool])  ← 两个工具都传

  RolloutConfig(max_steps=args.max_steps, terminal_mode=False, print_tool_calls=False)
```

**⑤ 并发 & 存储**
完全对齐 `browsecomp_single_agent.py`：`Semaphore` + `as_completed` + `Lock` + 断点续传

**⑥ 命令行参数**

| 参数 | 默认值 | 与 single agent 的差异 |
|---|---|---|
| `--max_steps` | `60` | 降低（orchestrator 只做分解+汇总）|
| `--sub_max_steps` | `100` | 新增（sub-agent 步数）|
| `--max_concurrency` | `15` | 降低（swarm RPM 消耗更大）|
| `--result_dir` | `result/browsecomp_swarm` | 改目录名 |
| 其余 | 同 single agent | `model_id`, `api_base_url`, `max_tokens`, `max_samples` |

---

## 5. 改动文件汇总

| 优先级 | 文件 | 行号 | 修改内容 |
|---|---|---|---|
| P0 | `swarm_tool/task.py` | line 136-144 | 修复 `top_p` 缺失、`temperature` fallback `0.7`→`1.0`、`max_tokens` fallback `4096`→`8192` |
| P0 | `swarm_tool/task.py` | line 26 | `max_steps` 默认值 `20` → `100` |
| P0 | `swarm_tool/task.py` | line 26, 166-170 | `terminal_mode` 参数化，默认 `False` |
| P0 | `rollout/sub_rollout.py` | line 17 | `SubRolloutConfig` 默认 `terminal_mode=True` → `False` |
| P0 | `examples/multi_agent.py` | 改写 | 改写为 BrowseComp swarm 评测脚本 |
| P1 | `swarm_tool/task.py` | — | 父 agent tools 自动传播给子 agent（现在需要手动 `set_parent_tools`）|
