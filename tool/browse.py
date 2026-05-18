"""Browse Tool - Fetch web page content using Serper Scrape API"""

import os
import re
import logging
from typing import Dict, Any

import httpx

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 20000


def _clean_text(text: str) -> str:
    """Clean scraped text content"""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    text = text.strip()
    if len(text) > MAX_CONTENT_LENGTH:
        text = text[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"
    return text


class BrowseTool(BaseTool):
    """Web browsing tool using Serper Scrape API

    Fetches and extracts text content from web pages.
    Uses the same SERPER_API_KEY as the search tool.

    Environment variable:
        SERPER_API_KEY: Your Serper API key
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        self.scrape_url = "https://scrape.serper.dev/"

    @property
    def name(self) -> str:
        return "browse"

    @property
    def description(self) -> str:
        return (
            "Open a web page URL and read its text content. "
            "Use this tool to visit URLs found from search results "
            "and extract detailed information from web pages."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the web page to visit"
                }
            },
            "required": ["url"]
        }

    async def execute(self, url: str, **kwargs) -> ToolResult:
        if not self.api_key:
            return ToolResult(
                content="Error: SERPER_API_KEY environment variable not set.",
                success=False,
                error="Missing API key"
            )

        try:
            logger.info(f"Browsing: {url}")

            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {"url": url}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.scrape_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            text_content = data.get("text", "")
            metadata = data.get("metadata", {})
            title = ""
            if isinstance(metadata, dict):
                title = metadata.get("title", "")

            if not text_content:
                return ToolResult(
                    content=f"No content could be extracted from: {url}",
                    success=True
                )

            result_parts = []
            if title:
                result_parts.append(f"Title: {title}")
            result_parts.append(f"URL: {url}")
            result_parts.append("")
            result_parts.append(_clean_text(text_content))

            return ToolResult(
                content="\n".join(result_parts),
                success=True
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Serper scrape API error: {e}")
            return ToolResult(
                content="",
                success=False,
                error=f"Scrape API error: {e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"Browse failed: {e}")
            return ToolResult(
                content="",
                success=False,
                error=str(e)
            )
