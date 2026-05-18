# Kimi K2.5 BrowseComp 复现设置 (Single Agent)

> 来源: Kimi K2.5 Technical Report, Section 5.1.1 + Appendix E.1, E.6, E.8

## 1. 目标分数 (Table 4)

| 配置 | 分数 |
|---|---|
| Single Agent (无 context management) | **60.6%** |

---

## 2. System Prompt

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

`{DATE}` 动态替换为当前时间戳。

---

## 3. 推理参数

| 参数 | 值 |
|---|---|
| Temperature | **1.0** |
| Top-p | **0.95** |
| Context Length | **256k tokens** |
| Max Completion Tokens | 未明确给出 |

---

## 4. Step 设置

- Paper **没有明确给出** single agent 的 max step 限制
- 无 context management 时：超出 256k context window 直接算 failure（不截断）
- 有 discard-all 时：超过 token 阈值后截断所有历史（阈值具体数值未给出）

---

## 5. 工具配置 (Tools)

1. **Web Search Tool** — 搜索引擎检索
2. **Code Interpreter** — Python 执行环境（IPython）
3. **Web Browsing Tools** — 访问网页链接、获取页面内容、点击/输入/滚动等交互

---

## 6. 采样协议

- BrowseComp 为 **单次运行** (single-run)，不做多次平均

---

## 7. 关键信息缺失

| 缺失项 | 说明 |
|---|---|
| Single Agent max step 数 | 可能无硬性 step 限制，完全依赖 context window |
| Discard-all 的具体 token 阈值 | 具体数值未给出 |
| Web search / browsing 具体实现 | 搜索引擎 API、浏览器工具的接口细节未给出 |
| max_completion_tokens | 每次 LLM 调用的最大生成 token 数未给出 |

---

## 8. Codebase Gap 分析

### 8.1 已有可复用

| 组件 | 文件 | 说明 |
|---|---|---|
| Agent 核心 | `agent/agent.py` | Agent + tool execution，可直接复用 |
| MainRollout | `rollout/main_rollout.py` | step-by-step 执行循环，支持 max_steps / tool calls |
| SearchTool | `tool/search.py` | Serper API Google 搜索 |
| LLMClient | `utils/llm_client.py` | OpenAI 兼容 client，支持 tool calling + reasoning_content |
| 存储 | `rollout/main_rollout.py` | JSONL 结果存储 |

### 8.2 需要新增

| 组件 | 优先级 | 说明 |
|---|---|---|
| **Web Browsing Tool** | P0 | Paper 三大工具之一，BrowseComp 必须访问网页获取信息 |
| **BrowseComp 数据加载 + 评测脚本** | P0 | 从 HuggingFace 加载 `openai/browsecomp`，跑完后对比答案 |
| **Code Interpreter Tool** | P1 | BrowseComp 用到可能性低，可先不实现 |

### 8.3 需要修改

| 修改项 | 文件 | 变更 |
|---|---|---|
| **top_p 参数** | `utils/llm_client.py` | `chat()` 缺少 top_p，需添加 |
| **max_tokens** | `agent/agent.py` | 默认 4096 太小，建议 16384+ |
| **max_steps** | 运行配置 | 默认 50，建议设为 100 |
| **System Prompt** | 新建 run 脚本 | 换成 Paper 中的版本 |
| **去掉 Swarm 工具** | 新建 run 脚本 | Single agent 不需要 create_subagent / assign_task |

### 8.4 实现优先级

```
1. [P0] 添加 top_p  max tokens max steps 参数到 LLMClient
2. [P0] 实现 Web Browsing Tool（URL → 网页内容） https://github.com/TIGER-AI-Lab/OpenResearcher 参考这里 browse 工具实现直接用 serper 即可
3. [P0] 编写 BrowseComp single agent 运行脚本 可以直接参考 /home/zhuofeng/swarm_example/examples/simple_agent.py code 写在 examples 里面
4. [P0] BrowseComp 数据集加载 + 评测逻辑 https://github.com/TIGER-AI-Lab/OpenResearcher 同样参考这里数据加载逻辑
```
