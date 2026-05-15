"""LLM Client - Simple wrapper for OpenAI-compatible APIs"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


class LLMClient:
    """Simple LLM client using OpenAI SDK"""

    def __init__(
        self,
        model_id: str = "kimi-k2-0711-preview",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model_id = model_id
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        import httpx
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(300.0, connect=30.0),
            max_retries=0,  # We handle retries ourselves
        )

    def _token_param_name(self) -> str:
        """Return the preferred output-token parameter for this endpoint/model."""
        base_url = (self.base_url or "").lower()
        model_id = (self.model_id or "").lower()

        if "api.openai.com" in base_url or model_id.startswith(("gpt-5", "o1", "o3", "o4")):
            return "max_completion_tokens"

        return "max_tokens"

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Send chat completion request with retry logic

        Args:
            messages: List of conversation messages
            tools: Optional list of tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Response dict with content and optional tool_calls
        """
        token_param = self._token_param_name()
        kwargs = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            token_param: max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await self.client.chat.completions.create(**kwargs)

                # Extract response
                choice = response.choices[0]
                message = choice.message

                result = {
                    "role": "assistant",
                    "content": message.content or "",
                    "finish_reason": choice.finish_reason,
                }

                # Handle reasoning_content for thinking models (like kimi-k2.5)
                if hasattr(message, 'reasoning_content') and message.reasoning_content:
                    result["reasoning_content"] = message.reasoning_content

                # Handle tool calls
                if message.tool_calls:
                    result["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in message.tool_calls
                    ]

                return result

            except Exception as e:
                last_error = e
                logger.warning(f"LLM request attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

        logger.error(f"LLM request failed after {MAX_RETRIES} attempts: {last_error}")
        return {
            "role": "assistant",
            "content": f"Error: {str(last_error)}",
            "finish_reason": "error",
        }
