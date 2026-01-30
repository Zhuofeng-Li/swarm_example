"""Open Swarm - Multi-Agent Rollout Framework

A lightweight, extensible framework for orchestrating multiple AI agents
to collaboratively solve complex tasks.

Example:
    from open_swarm import Agent, AgentConfig, MainRollout, RolloutConfig
    from open_swarm.tool import SearchTool
    from open_swarm.swarm_tool import CreateSubagentTool, TaskTool

    # Create agent registry and tools
    agent_registry = {}
    search_tool = SearchTool()
    create_subagent = CreateSubagentTool(agent_registry)
    task_tool = TaskTool(agent_registry)

    # Create main agent
    config = AgentConfig(name="main", system_prompt="You are helpful.")
    agent = Agent(config, tools=[search_tool, create_subagent, task_tool])

    # Set parent references
    task_tool.set_parent_agent(agent)
    task_tool.set_parent_tools([search_tool])

    # Run
    rollout = MainRollout(RolloutConfig(max_steps=30))
    result = await rollout.run(agent, "Help me research AI safety")
"""

from .agent import Agent, AgentConfig
from .rollout import (
    BaseRollout,
    MainRollout,
    SubRollout,
    RolloutConfig,
    RolloutResult,
)
from .tool import BaseTool, ToolResult, SearchTool
from .swarm_tool import CreateSubagentTool, TaskTool
from .utils import LLMClient

__version__ = "0.1.0"
__author__ = "Open Swarm Contributors"

__all__ = [
    # Agent
    "Agent",
    "AgentConfig",
    # Rollout
    "BaseRollout",
    "MainRollout",
    "SubRollout",
    "RolloutConfig",
    "RolloutResult",
    # Tool
    "BaseTool",
    "ToolResult",
    "SearchTool",
    # Swarm Tools
    "CreateSubagentTool",
    "TaskTool",
    # Utils
    "LLMClient",
]
