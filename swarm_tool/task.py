"""Task Tool - Launch sub-agents to execute tasks"""

import logging
from typing import Dict, List, Any, Optional

from tool.base import BaseTool, ToolResult
from agent.agent import Agent, AgentConfig
from rollout.sub_rollout import SubRollout, SubRolloutConfig

logger = logging.getLogger(__name__)


class TaskTool(BaseTool):
    """Tool for launching sub-agents to execute tasks

    This tool spawns a sub-agent to handle a specific subtask,
    allowing for hierarchical task decomposition and parallel execution.
    """

    def __init__(
        self,
        agent_registry: Dict[str, Dict[str, Any]],
        parent_agent: Optional[Agent] = None,
        parent_tools: Optional[List[BaseTool]] = None,
        max_steps: int = 20,
    ):
        """Initialize Task tool

        Args:
            agent_registry: Registry of available agent configurations
            parent_agent: Reference to parent agent (for context forking)
            parent_tools: Tools to pass to sub-agents
            max_steps: Maximum steps for sub-agent execution
        """
        self.agent_registry = agent_registry
        self.parent_agent = parent_agent
        self.parent_tools = parent_tools or []
        self.max_steps = max_steps
        self.subagent_counter = 0
        self.sub_results: List[Dict[str, Any]] = []  # Store sub-agent results

    def set_parent_agent(self, agent: Agent):
        """Set the parent agent reference"""
        self.parent_agent = agent

    def set_parent_tools(self, tools: List[BaseTool]):
        """Set tools available to sub-agents"""
        self.parent_tools = tools

    @property
    def name(self) -> str:
        return "assign_task"

    @property
    def description(self) -> str:
        return (
            "Launch a new agent.\n"
            "Usage notes:\n"
            "1. You can launch multiple agents concurrently whenever possible, to maximize performance;\n"
            "2. When the agent is done, it will return a single message back to you."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Name of the agent to use (must be created first with create_subagent)"
                },
                "prompt": {
                    "type": "string",
                    "description": "Detailed task description for the sub-agent"
                },
                "fork_context": {
                    "type": "boolean",
                    "description": "Whether to include parent conversation context (default: false)"
                }
            },
            "required": ["agent", "prompt"]
        }

    async def execute(
        self,
        agent: str,
        prompt: str,
        fork_context: bool = False,
    ) -> ToolResult:
        """Launch a sub-agent to execute a task

        Args:
            agent: Name of the agent configuration to use
            prompt: Task description for the sub-agent
            fork_context: Whether to include parent context

        Returns:
            ToolResult with sub-agent's response
        """
        try:
            # Get agent configuration
            if agent not in self.agent_registry:
                available = list(self.agent_registry.keys())
                return ToolResult(
                    content=f"Agent '{agent}' not found. Available agents: {available}. Create one first with create_subagent.",
                    success=False,
                    error=f"Agent '{agent}' not found"
                )

            agent_config = self.agent_registry[agent]

            # Increment counter
            self.subagent_counter += 1
            subagent_id = f"subagent_{self.subagent_counter}"

            logger.info(f"Launching {subagent_id} with agent config: {agent}")

            # Build sub-agent system prompt
            system_prompt = agent_config["system_prompt"]
            system_prompt += f"\n\nIMPORTANT:"
            system_prompt += f"\n- You have a MAXIMUM of {self.max_steps} steps to complete your task."
            system_prompt += f"\n- Return results AS SOON AS you have sufficient information."
            system_prompt += f"\n- If approaching step limit, summarize findings and return."

            # Create sub-agent configuration
            # Use subagent config if specified, otherwise fall back to parent config
            if self.parent_agent:
                subagent_model = self.parent_agent.config.subagent_model_id or self.parent_agent.config.model_id
                subagent_api_key = self.parent_agent.config.subagent_api_key or self.parent_agent.config.api_key
                subagent_base_url = self.parent_agent.config.subagent_api_base_url or self.parent_agent.config.api_base_url
            else:
                subagent_model = "kimi-k2.5"
                subagent_api_key = None
                subagent_base_url = None

            subagent_config = AgentConfig(
                name=subagent_id,
                system_prompt=system_prompt,
                model_id=subagent_model,
                api_key=subagent_api_key,
                api_base_url=subagent_base_url,
                max_tokens=self.parent_agent.config.max_tokens if self.parent_agent else 4096,
                temperature=self.parent_agent.config.temperature if self.parent_agent else 0.7,
            )

            # Create sub-agent with tools (excluding swarm tools to prevent recursion)
            subagent_tools = [
                tool for tool in self.parent_tools
                if tool.name not in ("create_subagent", "task")
            ]

            subagent = Agent(
                config=subagent_config,
                tools=subagent_tools,
            )

            # Prepare context if forking
            context_messages = None
            if fork_context and self.parent_agent:
                # Get parent's conversation (excluding system message)
                # This would need access to rollout's messages
                # For now, we skip this feature
                logger.info("Context forking requested (not implemented in this version)")

            # Run sub-rollout
            rollout_config = SubRolloutConfig(
                max_steps=self.max_steps,
                step_hint=True,
                terminal_mode=True,
            )

            sub_rollout = SubRollout(rollout_config)
            result = await sub_rollout.run(
                agent=subagent,
                initial_message=prompt,
                context_messages=context_messages,
            )

            # Format result
            if result.status.value == "completed":
                content = result.final_response or "Task completed but no response generated."
            elif result.status.value == "max_steps_reached":
                content = f"Sub-agent reached step limit.\n\nLast response:\n{result.final_response or 'No response'}"
            elif result.status.value == "error":
                content = f"Sub-agent encountered an error: {result.error}"
            else:
                content = f"Sub-agent finished with status: {result.status.value}"

            logger.info(f"{subagent_id} completed with status: {result.status.value}")

            # Store sub-agent result for collection
            self.sub_results.append({
                "agent": agent,
                "agent_id": subagent_id,
                "prompt": prompt,
                "messages": result.messages,
                "status": result.status.value,
                "steps": result.steps,
            })

            return ToolResult(
                content=content,
                success=result.status.value in ("completed", "max_steps_reached"),
            )

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            import traceback
            traceback.print_exc()
            return ToolResult(
                content="",
                success=False,
                error=str(e)
            )
