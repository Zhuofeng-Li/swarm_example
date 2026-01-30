# Run Examples

Example scripts for running the multi-agent rollout framework.

## Environment Variables

Set the following environment variables before running:

```bash
# Required for kimi models
export KIMI_API_KEY="your-kimi-api-key"

# Required for qwen models 
export OPENAI_API_KEY="your-openai-api-key"

# Optional: for web search functionality
export SERPER_API_KEY="your-serper-api-key"
```

## Examples

### 1. Kimi + Kimi (Main and Sub both use kimi-k2.5)

```bash
export KIMI_API_KEY="sk-xxx"
export SERPER_API_KEY="xxx"  # optional
python run_kimi_kimi.py
```

This configuration uses kimi-k2.5 for both the main agent and sub-agents.
- More thorough results with multiple iterations
- Supports reasoning_content (thinking mode)

### 2. Kimi + Qwen (Main uses kimi-k2.5, Sub uses qwen2.5-72b)

```bash
export KIMI_API_KEY="sk-xxx"
export OPENAI_API_KEY="sk-xxx"
export SERPER_API_KEY="xxx"  # optional
python run_kimi_qwen.py
```

This configuration uses kimi-k2.5 for the main agent and qwen2.5-72b-instruct for sub-agents.
- Faster execution with fewer steps
- Good for tasks requiring quick parallel processing

## Output

Results are saved to the `result/` directory as JSONL files:
- `kimi_kimi_result.jsonl` - Results from kimi+kimi configuration
- `kimi_qwen_result.jsonl` - Results from kimi+qwen configuration

Each file contains:
```json
{
  "main": [...],  // Main agent conversation messages
  "subs": [...]   // Sub-agent conversation records
}
```

## Customization

To use your own query, modify the `query` variable in the scripts:

```python
query = "Your custom task description here"
```

To change the model or API endpoint, modify the `AgentConfig`:

```python
config = AgentConfig(
    model_id="your-model",
    api_key=os.environ.get("YOUR_API_KEY"),
    api_base_url="https://your-api-endpoint/v1",
    subagent_model_id="sub-model",
    subagent_api_key=os.environ.get("SUB_API_KEY"),
    subagent_api_base_url="https://sub-api-endpoint/v1",
)
```
