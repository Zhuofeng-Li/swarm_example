# BrowseComp Single Agent 运行参数总结

> 脚本: `examples/browsecomp_single_agent.py`

---

## 1. 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--model_id` | `kimi-k2.5` | 模型 ID |
| `--api_base_url` | `https://api.moonshot.ai/v1` | API endpoint |
| `--max_tokens` | `8192` | 每次 LLM 调用的最大生成 token 数 |
| `--max_steps` | `300` | 每个问题最大 tool-calling 步数 |
| `--max_samples` | `None` (全量) | 跑多少道题，`None` 跑全部 |
| `--max_concurrency` | `8` | 最大并发 agent 数 |
| `--result_dir` | `result/browsecomp` | 结果输出目录 |

---

## 2. 模型采样参数 (硬编码，来自 Paper)

| 参数 | 值 | 来源 |
|---|---|---|
| Temperature | **1.0** | Kimi K2.5 Technical Report |
| Top-p | **0.95** | Kimi K2.5 Technical Report |
| Context Length | **256k** (模型限制) | Kimi K2.5 Technical Report |

---

## 3. 工具配置

通过 OpenAI function calling 协议注入（`tools` 参数），不在 system prompt 中。

### 3.1 SearchTool (`tool/search.py`)

| 项目 | 值 |
|---|---|
| Tool Name | `search` |
| API | Serper Google Search (`https://google.serper.dev/search`) |
| 返回结果数 | Top 5 (organic results) |
| 超时 | 30s |
| 输出格式 | 标题 + 摘要 + URL，附 Knowledge Graph (如有) |

**Schema 传给模型的参数:**
```json
{
  "query": {"type": "string", "description": "The search query to look up"}
}
```

### 3.2 BrowseTool (`tool/browse.py`)

| 项目 | 值 |
|---|---|
| Tool Name | `browse` |
| API | Serper Scrape (`https://scrape.serper.dev/`) |
| 内容截断 | 20,000 字符 |
| 超时 | 30s |
| 输出格式 | Title + URL + 清洗后的网页文本 |

**Schema 传给模型的参数:**
```json
{
  "url": {"type": "string", "description": "The URL of the web page to visit"}
}
```

---

## 4. System Prompt

```
You are Kimi, today's date: {动态时间戳}.
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

---

## 5. 并发执行架构

```
asyncio event loop
├── Semaphore(max_concurrency)  ← 控制同时跑多少个 agent
├── asyncio.create_task(process_item) × N  ← 每个 question 一个 task
├── asyncio.as_completed  ← 先完成先写盘
└── asyncio.Lock  ← 保护 JSONL 文件写入
```

- 每个 agent session 独立：独立的 Agent 实例 + MainRollout 实例
- 并发模式下关闭 terminal 输出（`terminal_mode=False`）

---

## 6. LLM Client 配置 (`utils/llm_client.py`)

| 项目 | 值 |
|---|---|
| SDK | `openai.AsyncOpenAI` |
| 请求超时 | 300s (连接 30s) |
| 重试次数 | 3 次 |
| 重试间隔 | 5s × (attempt + 1) 递增 |
| Token 参数 | `max_tokens` (非 OpenAI 用) / `max_completion_tokens` (OpenAI 用) |
| Tool Choice | `auto` |

---

## 7. Rollout 执行逻辑 (`rollout/main_rollout.py`)

| 项目 | 值 |
|---|---|
| 终止条件 | 模型返回纯文本无 tool_calls，或 `finish_reason=stop` |
| 步数限制 | `max_steps=300` |
| 超步行为 | 取最后一条 assistant content 作为 final_response |
| Tool 执行 | 同一轮多个 tool_calls 通过 `asyncio.gather` 并行执行 |

---

## 8. 断点续传

- 启动时读取 `result_dir/results.jsonl`，收集已完成的 `qid`
- 跳过已完成的问题，只处理 pending 的

---

## 9. 环境变量 (`.env`)

| 变量 | 用途 |
|---|---|
| `KIMI_API_KEY` | Kimi API 认证 |
| `SERPER_API_KEY` | Serper 搜索 + 网页抓取 |

---

## 10. 运行示例

```bash
# 跑 2 道题测试
python examples/browsecomp_single_agent.py --max_concurrency 16 --max_samples 2

# 全量运行
python examples/browsecomp_single_agent.py --max_concurrency 16

# 调整模型参数
python examples/browsecomp_single_agent.py \
    --model_id kimi-k2.5 \
    --max_tokens 16384 \
    --max_steps 300 \
    --max_concurrency 32
```
