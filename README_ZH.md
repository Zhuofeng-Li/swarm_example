# Open Swarm

一个轻量级、可扩展的多智能体编排框架。
注：本项目的核心代码由 **Kimi（kimi-k2.5）** 独立完成。

## 声明（Disclaimer）

本仓库是一个**个人性质的实验性项目**，仅用于 demo / 参考实现，请勿将其视为生产级系统。

- 本项目**并非生产可用**：
  并发控制、成本控制、工具等真实部署所需的问题，均未系统性处理。
- 该仓库的主要目的，是展示**如何使用k2.5调用agent swarm**，

本项目**不代表任何公司或官方产品的立场**，也未获得任何组织的背书或认可。
所有设计均属于探索性尝试，可能随时调整或发生不兼容变更。

## 安装

```bash
pip install -e .
```

## 快速开始

参考 `run_examples/` 目录下的完整示例：

```bash
# 设置环境变量
export KIMI_API_KEY="your-kimi-api-key"
export OPENAI_API_KEY="your-openai-api-key"
export SERPER_API_KEY="your-serper-api-key"  # 可选，用于搜索

# 运行 kimi + kimi 配置
python run_examples/run_kimi_kimi.py

# 运行 kimi + qwen 配置
python run_examples/run_kimi_qwen.py
```

### 简单智能体

```python
import asyncio
from open_swarm import Agent, AgentConfig, MainRollout, RolloutConfig, SearchTool

async def main():
    config = AgentConfig(
        name="assistant",
        system_prompt="你是一个有用的助手。",
        model_id="kimi-k2.5",
        api_key="your-api-key",
        api_base_url="https://api.moonshot.cn/v1",
    )

    agent = Agent(config, tools=[SearchTool()])

    rollout = MainRollout(RolloutConfig(max_steps=10))
    result = await rollout.run(agent, "你好！你能做什么？")

    print(result.final_response)

asyncio.run(main())
```

### 多智能体系统

```python
import asyncio
from open_swarm import (
    Agent, AgentConfig, MainRollout, RolloutConfig,
    SearchTool, CreateSubagentTool, TaskTool
)

async def main():
    agent_registry = {}

    # 创建工具
    search = SearchTool()
    create_subagent = CreateSubagentTool(agent_registry)
    task = TaskTool(agent_registry=agent_registry, max_steps=15)

    # 创建编排智能体，主/子智能体使用不同模型
    config = AgentConfig(
        name="orchestrator",
        system_prompt="你是一个编排智能体，可以创建子智能体并分配任务。",
        model_id="kimi-k2.5",
        api_key="your-kimi-key",
        api_base_url="https://api.moonshot.cn/v1",
        # 子智能体可以使用不同的模型
        subagent_model_id="qwen2.5-72b-instruct",
        subagent_api_key="your-qwen-key",
        subagent_api_base_url="https://openai.app.msh.team/v1",
        temperature=1.0,  # kimi-k2.5 需要 temperature=1.0
    )

    agent = Agent(config, tools=[search, create_subagent, task])
    task.set_parent_agent(agent)
    task.set_parent_tools([search])

    # 运行并保存结果
    rollout = MainRollout(RolloutConfig(
        max_steps=30,
        storage_path="result/output.jsonl",
    ))
    result = await rollout.run(
        agent,
        "研究最新的 AI 发展并总结。"
    )

    print(f"创建的智能体: {list(agent_registry.keys())}")
    print(f"使用的子智能体数量: {len(result.subs)}")
    print(result.final_response)

asyncio.run(main())
```

## 配置说明

### 环境变量

```bash
# Kimi API (api.moonshot.cn)
export KIMI_API_KEY=your-kimi-key

# OpenAI 兼容 API (用于 qwen 等模型)
export OPENAI_API_KEY=your-api-key
export OPENAI_BASE_URL=https://api.openai.com/v1  # 可选

# 搜索工具 (Serper - Google Search API)
export SERPER_API_KEY=your-serper-key  # 从 https://serper.dev 获取
```

### AgentConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | 必填 | 智能体名称 |
| `system_prompt` | str | "You are a helpful assistant." | 系统提示词 |
| `model_id` | str | "kimi-k2.5" | 模型标识 |
| `api_key` | str | None | API 密钥（未设置时使用环境变量） |
| `api_base_url` | str | None | API 地址（未设置时使用环境变量） |
| `subagent_model_id` | str | None | 子智能体模型（默认同 model_id） |
| `subagent_api_key` | str | None | 子智能体 API 密钥 |
| `subagent_api_base_url` | str | None | 子智能体 API 地址 |
| `max_tokens` | int | 4096 | 单次请求最大 token 数 |
| `temperature` | float | 0.7 | 采样温度 |

### RolloutConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_steps` | int | 50 | 最大执行步数 |
| `terminal_mode` | bool | True | 是否在终端打印输出 |
| `storage_path` | str | None | 结果保存路径（JSONL 格式） |
| `print_tool_calls` | bool | True | 是否打印工具调用 |
| `print_tool_results` | bool | True | 是否打印工具结果 |

## 自定义工具

```python
from open_swarm import BaseTool, ToolResult

class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "工具功能描述"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "第一个参数"
                }
            },
            "required": ["param1"]
        }

    async def execute(self, param1: str) -> ToolResult:
        result = f"处理结果: {param1}"
        return ToolResult(content=result, success=True)
```

## 项目结构

```
open_swarm/
├── agent/          # 智能体类和配置
├── rollout/        # Rollout 实现（Main, Sub）
├── tool/           # 基础工具和 SearchTool
├── swarm_tool/     # CreateSubagent 和 Task 工具
├── utils/          # LLM 客户端
└── run_examples/   # 示例脚本
```

## 存储格式

结果以 JSONL 格式保存，结构如下：

```json
{
  "main": [...],  // 主智能体对话消息
  "subs": [...]   // 子智能体对话记录
}
```

每个子智能体记录包含：

```json
{
  "agent": "agent_name",      // 智能体配置名称
  "agent_id": "subagent_1",   // 唯一标识
  "prompt": "任务描述",        // 分配的任务
  "messages": [...],          // 对话历史
  "status": "completed",      // 状态
  "steps": 5                  // 执行步数
}
```

## 核心概念

### Rollout（执行循环）

Rollout 管理智能体的执行循环，负责：
- 消息历史管理
- 步数计数和限制
- 工具执行流程
- 完成检测

**MainRollout**：主智能体执行循环，支持结果存储
**SubRollout**：子智能体执行循环，带有步数提示

### Swarm Tools（群体工具）

- **create_subagent**：动态创建具有特定能力的子智能体
- **assign_task**：将任务分配给已创建的子智能体

### 执行流程

```
用户请求
    ↓
MainRollout 启动
    ↓
主智能体思考 → 调用工具
    ↓
create_subagent → 创建专业子智能体
    ↓
assign_task → SubRollout 执行子任务
    ↓
子智能体完成 → 返回结果给主智能体
    ↓
主智能体汇总 → 生成最终响应
    ↓
保存结果到 JSONL
```

## 许可证

MIT License
