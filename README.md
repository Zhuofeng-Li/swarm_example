# Open Swarm

A lightweight, extensible multi-agent rollout framework for orchestrating AI agents.

Note: The implementation of this project was independently written by **Kimi (kimi-k2.5)**.

## Disclaimer

This repository is a **personal experimental project** and should be treated strictly as a demo / reference implementation.

- It is **not production-ready**.
- Many aspects required for real-world deployment (e.g., concurrency limits, robustness, cost control, tools) are intentionally not handled.
- The primary goal is to demonstrate **how to call and wire up agent swarm-style rollouts**, rather than how to build a full system.

This project is **not affiliated with, endorsed by, or representative of any company or official offering**.
All design choices reflect exploratory work and may change without notice.


## Installation

```bash
pip install -e .
```

## Quick Start

See `run_examples/` for complete working examples:

```bash
# Set environment variables
export KIMI_API_KEY="your-kimi-api-key"
export OPENAI_API_KEY="your-openai-api-key"
export SERPER_API_KEY="your-serper-api-key"  # optional

# Run kimi + kimi configuration
python run_examples/run_kimi_kimi.py

# Run kimi + qwen configuration
python run_examples/run_kimi_qwen.py
```

### Simple Agent

```python
import asyncio
from open_swarm import Agent, AgentConfig, MainRollout, RolloutConfig, SearchTool

async def main():
    config = AgentConfig(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model_id="kimi-k2.5",
        api_key="your-api-key",
        api_base_url="https://api.moonshot.cn/v1",
    )

    agent = Agent(config, tools=[SearchTool()])

    rollout = MainRollout(RolloutConfig(max_steps=10))
    result = await rollout.run(agent, "Hello! What can you do?")

    print(result.final_response)

asyncio.run(main())
```

### Multi-Agent System

```python
import asyncio
from open_swarm import (
    Agent, AgentConfig, MainRollout, RolloutConfig,
    SearchTool, CreateSubagentTool, TaskTool
)

async def main():
    agent_registry = {}

    # Create tools
    search = SearchTool()
    create_subagent = CreateSubagentTool(agent_registry)
    task = TaskTool(agent_registry=agent_registry, max_steps=15)

    # Create orchestrator with different models for main/sub
    config = AgentConfig(
        name="orchestrator",
        system_prompt="You are an orchestrator that delegates to sub-agents.",
        model_id="kimi-k2.5",
        api_key="your-kimi-key",
        api_base_url="https://api.moonshot.cn/v1",
        # Sub-agent can use a different model
        subagent_model_id="qwen2.5-72b-instruct",
        subagent_api_key="your-qwen-key",
        subagent_api_base_url="https://openai.app.msh.team/v1",
        temperature=1.0,  # kimi-k2.5 requires temperature=1.0
    )

    agent = Agent(config, tools=[search, create_subagent, task])
    task.set_parent_agent(agent)
    task.set_parent_tools([search])

    # Run with storage
    rollout = MainRollout(RolloutConfig(
        max_steps=30,
        storage_path="result/output.jsonl",
    ))
    result = await rollout.run(
        agent,
        "Research the latest AI developments and summarize them."
    )

    print(f"Created agents: {list(agent_registry.keys())}")
    print(f"Sub-agents used: {len(result.subs)}")
    print(result.final_response)

asyncio.run(main())
```

## Configuration

### Environment Variables

```bash
# Kimi API (api.moonshot.cn)
export KIMI_API_KEY=your-kimi-key

# OpenAI-compatible API (for qwen, etc.)
export OPENAI_API_KEY=your-api-key
export OPENAI_BASE_URL=https://api.openai.com/v1  # Optional

# Search Tool (Serper - Google Search API)
export SERPER_API_KEY=your-serper-key  # Get from https://serper.dev
```

### AgentConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | required | Agent name |
| `system_prompt` | str | "You are a helpful assistant." | System prompt |
| `model_id` | str | "kimi-k2.5" | Model identifier |
| `api_key` | str | None | API key (uses env var if not set) |
| `api_base_url` | str | None | API base URL (uses env var if not set) |
| `subagent_model_id` | str | None | Model for sub-agents (defaults to model_id) |
| `subagent_api_key` | str | None | API key for sub-agents |
| `subagent_api_base_url` | str | None | API base URL for sub-agents |
| `max_tokens` | int | 4096 | Max tokens per request |
| `temperature` | float | 0.7 | Sampling temperature |

### RolloutConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_steps` | int | 50 | Maximum execution steps |
| `terminal_mode` | bool | True | Print output to terminal |
| `storage_path` | str | None | Path to save results as JSONL |
| `print_tool_calls` | bool | True | Print tool calls to terminal |
| `print_tool_results` | bool | True | Print tool results to terminal |

## Creating Custom Tools

```python
from open_swarm import BaseTool, ToolResult

class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Description of what this tool does"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "First parameter"
                }
            },
            "required": ["param1"]
        }

    async def execute(self, param1: str) -> ToolResult:
        result = f"Processed: {param1}"
        return ToolResult(content=result, success=True)
```

## Architecture

```
open_swarm/
├── agent/          # Agent class and configuration
├── rollout/        # Rollout implementations (Main, Sub)
├── tool/           # Base tool and SearchTool
├── swarm_tool/     # CreateSubagent and Task tools
├── utils/          # LLM client
└── run_examples/   # Example scripts
```

## Storage Format

Results are saved as JSONL with the following structure:

```json
{
  "main": [...],  // Main agent conversation messages
  "subs": [...]   // Sub-agent conversation records
}
```

## License

MIT License
