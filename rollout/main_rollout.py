"""Main Rollout - Rollout for main agent execution"""

import json
import logging
import os
from typing import Dict, List, Any, Optional

from .base import BaseRollout, RolloutConfig, RolloutResult, RolloutStatus

logger = logging.getLogger(__name__)


class MainRollout(BaseRollout):
    """Rollout for main agent execution

    MainRollout provides full capabilities including:
    - Complete tool access
    - Sub-agent spawning via Task tool
    - Message storage (optional)
    - Terminal output formatting
    """

    def __init__(self, config: Optional[RolloutConfig] = None):
        """Initialize main rollout

        Args:
            config: Rollout configuration
        """
        super().__init__(config)
        self.sub_results: List[Dict[str, Any]] = []  # Collect sub-agent results

    async def run(
        self,
        agent,
        initial_message: str,
        context_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> RolloutResult:
        """Execute the main rollout loop

        Args:
            agent: The agent to run
            initial_message: Initial user message
            context_messages: Optional previous context to include

        Returns:
            RolloutResult with execution results
        """
        # Reset state
        self.reset()

        # Initialize messages
        self.messages = [agent.get_system_message()]

        # Add context if provided
        if context_messages:
            self.messages.extend(context_messages)

        # Add initial user message
        self.messages.append({
            "role": "user",
            "content": initial_message
        })

        result = RolloutResult(
            status=RolloutStatus.RUNNING,
            messages=self.messages,
            steps=0,
        )

        # Main execution loop
        while self.current_step < self.config.max_steps and not self.interrupted:
            try:
                # Get agent response
                response = await agent.process_message(
                    messages=self.messages,
                    include_system=False,  # System already in messages
                )

                # Print step info
                self._print_step(self.current_step, response)

                # Add assistant message
                assistant_msg = self._format_assistant_message(response)
                self.messages.append(assistant_msg)

                # Handle tool calls
                if response.get("tool_calls"):
                    tool_results = await agent.execute_tool_calls(response["tool_calls"])

                    # Print and add tool results
                    for tr in tool_results:
                        self._print_tool_result(
                            tr.get("tool_call_id", "unknown"),
                            tr.get("content", "")
                        )
                        self.messages.append(tr)

                    self.current_step += 1
                    continue

                # Check completion
                if self._is_complete(response):
                    result = RolloutResult(
                        status=RolloutStatus.COMPLETED,
                        messages=self.messages,
                        steps=self.current_step,
                        final_response=response.get("content"),
                    )
                    break

                self.current_step += 1

            except Exception as e:
                logger.error(f"Error in rollout step {self.current_step}: {e}")
                result = RolloutResult(
                    status=RolloutStatus.ERROR,
                    messages=self.messages,
                    steps=self.current_step,
                    error=str(e),
                )
                break

        # Handle max steps reached
        if self.current_step >= self.config.max_steps:
            result = RolloutResult(
                status=RolloutStatus.MAX_STEPS_REACHED,
                messages=self.messages,
                steps=self.current_step,
                final_response=self._get_last_assistant_content(),
            )

        # Handle interruption
        if self.interrupted:
            result = RolloutResult(
                status=RolloutStatus.INTERRUPTED,
                messages=self.messages,
                steps=self.current_step,
            )

        if self.config.terminal_mode:
            print(f"\n{'='*60}")
            print(f"Rollout completed: {result.status.value}")
            print(f"Total steps: {result.steps}")
            print('='*60)

        # Collect sub-agent results from TaskTool if available
        result.subs = self._collect_sub_results(agent)

        # Save to storage if path configured
        if self.config.storage_path:
            self._save_result(result)

        return result

    def _get_last_assistant_content(self) -> Optional[str]:
        """Get content from the last assistant message"""
        for msg in reversed(self.messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]
        return None

    def _collect_sub_results(self, agent) -> List[Dict[str, Any]]:
        """Collect sub-agent results from TaskTool"""
        subs = []
        # Find TaskTool in agent's tools (now named assign_task)
        task_tool = agent.tools.get("assign_task")
        if task_tool and hasattr(task_tool, "sub_results"):
            subs = task_tool.sub_results
        return subs

    def _save_result(self, result: RolloutResult):
        """Save result to storage path as jsonl

        storage_path can be:
        - A directory: saves to {dir}/result.jsonl
        - A file path ending with .jsonl: saves directly to that file
        """
        try:
            storage_path = self.config.storage_path

            if storage_path.endswith(".jsonl"):
                # Direct file path
                filepath = storage_path
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            else:
                # Directory path
                os.makedirs(storage_path, exist_ok=True)
                filepath = os.path.join(storage_path, "result.jsonl")

            # Append to jsonl file
            with open(filepath, "a", encoding="utf-8") as f:
                data = result.to_storage_format()
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

            logger.info(f"Saved result to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save result: {e}")
