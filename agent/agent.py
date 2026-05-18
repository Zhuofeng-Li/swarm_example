"""Agent - Core agent implementation"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from utils.llm_client import LLMClient
from tool.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for an agent"""
    name: str
    system_prompt: str = "You are a helpful assistant."
    model_id: str = "kimi-k2.5"
    api_key: Optional[str] = None  # API key, defaults to OPENAI_API_KEY env var
    api_base_url: Optional[str] = None  # Will use OPENAI_BASE_URL env var if not set
    subagent_model_id: Optional[str] = None  # Model for sub-agents, defaults to model_id
    subagent_api_key: Optional[str] = None  # API key for sub-agents
    subagent_api_base_url: Optional[str] = None  # Base URL for sub-agents
    max_tokens: int = 8192
    temperature: float = 1.0
    top_p: float = 0.95


class Agent:
    """Agent that processes messages and executes tools

    The Agent is responsible for:
    - Managing conversation with the LLM
    - Executing tool calls
    - Formatting responses
    """

    def __init__(
        self,
        config: AgentConfig,
        tools: Optional[List[BaseTool]] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        """Initialize agent

        Args:
            config: Agent configuration
            tools: List of tools available to the agent
            llm_client: Optional custom LLM client (will create one if not provided)
        """
        self.config = config
        self.tools = {tool.name: tool for tool in (tools or [])}

        # Initialize LLM client
        if llm_client:
            self.llm_client = llm_client
        else:
            self.llm_client = LLMClient(
                model_id=config.model_id,
                api_key=config.api_key,
                base_url=config.api_base_url,
            )

    def add_tool(self, tool: BaseTool):
        """Add a tool to the agent"""
        self.tools[tool.name] = tool

    def remove_tool(self, tool_name: str):
        """Remove a tool from the agent"""
        self.tools.pop(tool_name, None)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-format schemas for all tools"""
        return [tool.to_openai_schema() for tool in self.tools.values()]

    def get_system_message(self) -> Dict[str, str]:
        """Get the system message"""
        return {
            "role": "system",
            "content": self.config.system_prompt
        }

    async def process_message(
        self,
        messages: List[Dict[str, Any]],
        include_system: bool = True,
    ) -> Dict[str, Any]:
        """Process messages and return response

        Args:
            messages: Conversation messages
            include_system: Whether to prepend system message

        Returns:
            Response dict with content and optional tool_calls
        """
        # Prepare messages
        if include_system:
            # Check if system message already present
            if not messages or messages[0].get("role") != "system":
                messages = [self.get_system_message()] + messages

        # Get tool schemas
        tool_schemas = self.get_tool_schemas() if self.tools else None

        # Call LLM
        response = await self.llm_client.chat(
            messages=messages,
            tools=tool_schemas,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
        )

        return response

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute a single tool

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult from tool execution
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult(
                content="",
                success=False,
                error=f"Tool '{tool_name}' not found"
            )

        try:
            logger.info(f"Executing tool: {tool_name} with args: {arguments}")
            result = await tool.execute(**arguments)
            logger.info(f"Tool {tool_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(
                content="",
                success=False,
                error=str(e)
            )

    async def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute multiple tool calls concurrently

        Args:
            tool_calls: List of tool call dicts from LLM response

        Returns:
            List of tool results formatted for conversation (order preserved)
        """
        import asyncio

        async def _execute_one(tc: Dict[str, Any]) -> Dict[str, Any]:
            tool_name = tc["function"]["name"]
            args_str = tc["function"]["arguments"]

            try:
                arguments = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                arguments = {}

            result = await self.execute_tool(tool_name, arguments)

            return {
                "tool_call_id": tc.get("id", tool_name),
                "role": "tool",
                "content": result.to_str(),
            }

        results = await asyncio.gather(*[_execute_one(tc) for tc in tool_calls])
        return list(results)
