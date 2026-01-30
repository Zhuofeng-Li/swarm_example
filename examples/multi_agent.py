"""Multi-Agent Example - Using sub-agents with Open Swarm"""

import asyncio
import logging
import sys
import os

# Add parent directory to path for imports (when running from examples/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from open_swarm import (
    Agent,
    AgentConfig,
    MainRollout,
    RolloutConfig,
    SearchTool,
    CreateSubagentTool,
    TaskTool,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def main():
    """Run a multi-agent example"""

    # Create shared agent registry
    agent_registry = {}

    # Create tools
    search_tool = SearchTool()
    create_subagent = CreateSubagentTool(agent_registry)
    task_tool = TaskTool(
        agent_registry=agent_registry,
        max_steps=15,
    )

    # Create main agent configuration
    config = AgentConfig(
        name="orchestrator",
        system_prompt=(
            "You are an orchestrator agent that can delegate tasks to specialized sub-agents.\n"
            "\n"
            "Your workflow:\n"
            "1. Use create_subagent to define specialized agents for specific tasks\n"
            "2. Use task tool to assign work to the created agents\n"
            "3. Synthesize results from sub-agents to answer the user\n"
            "\n"
            "Available actions:\n"
            "- search: Search for information directly\n"
            "- create_subagent: Create a new specialized agent\n"
            "- task: Assign a task to a created agent\n"
            "\n"
            "Be strategic about when to delegate vs handle directly."
        ),
        model_id="kimi-k2-0711-preview",
        temperature=0.7,
    )

    # Create main agent
    agent = Agent(
        config=config,
        tools=[search_tool, create_subagent, task_tool]
    )

    # Set parent references for task tool
    task_tool.set_parent_agent(agent)
    task_tool.set_parent_tools([search_tool])

    # Create rollout
    rollout_config = RolloutConfig(
        max_steps=30,
        terminal_mode=True,
    )
    rollout = MainRollout(rollout_config)

    # Run agent
    print("\n" + "="*60)
    print("Starting Multi-Agent Example")
    print("="*60)

    # Example task that benefits from sub-agents
    user_message = (
        "I want to learn about the latest developments in AI agents. "
        "Please create a research agent to find information about this topic, "
        "and then summarize the key findings for me."
    )

    result = await rollout.run(
        agent=agent,
        initial_message=user_message
    )

    print("\n" + "="*60)
    print("Final Result:")
    print("="*60)
    print(f"Status: {result.status.value}")
    print(f"Steps: {result.steps}")
    print(f"Agents created: {list(agent_registry.keys())}")
    if result.final_response:
        print(f"\nResponse:\n{result.final_response}")


if __name__ == "__main__":
    asyncio.run(main())
