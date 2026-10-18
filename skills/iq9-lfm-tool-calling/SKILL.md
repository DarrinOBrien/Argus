---
name: iq9-lfm-tool-calling
description: Add tool and function calling to an app on the IQ-9075 with LiquidAI LFM2-1.2B-Tool through GenieX's OpenAI-compatible tools API, with schema validation, an allowlist, and a policy check in code before any write action. Use when the user wants the model to call functions, use tools, drive hardware, or run a multi-step agent loop, or asks about tool_calls on GenieX.
compatibility: IQ-9075, geniex serve v0.8.0, LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_0 in the cache.
metadata:
  version: "0.1"
---

# Tool calling with LFM2-1.2B-Tool

The working reference is `examples/tool-calling/tool_calling.py`, and its README has the measured behaviour. Copy its structure: `TOOLS`, `validate()`, `check_policy()`, `run_tool()`, and `run()`. `python3 tool_calling.py --self-test` checks the guards without a server.

## How the API works on v0.8.0 (measured on the board)

- Send a standard OpenAI `tools` array to `/v1/chat/completions`. The reply has `message.tool_calls` and `finish_reason: "tool_calls"`. GenieX does the parsing, so don't parse JSON out of the model's text yourself.
- Send results back as `{"role": "tool", "tool_call_id": ..., "content": json.dumps(result)}` after the assistant message that holds the `tool_calls`.
- About 0.9 s per model turn (median), and 0.6–1.1 s for a final answer of 25–50 tokens.
- The model sometimes returns two calls in one turn. Run them in order.
- `LFM2.5-2.6B` is the explainer model. Use `LFM2-1.2B-Tool` for tool calls.

## What the model gets wrong (all measured; design around each one)

| Behaviour | Guard |
|---|---|
| It alerted on 12 of 12 readings, 39 °C included, and its alert text invented numbers | The **policy runs in code**: a write tool needs a fresh measurement and a rule that passes. The model only proposes actions |
| It said "alert logged" without making the call (4 of 7 runs) | Report actions from your own executed list. Never from the model's text |
| It made up arguments, or left out required ones | `validate()` against a JSON schema with `additionalProperties: false` and `enum` |
| It skipped the tool and asked a question instead (2 of 5 on vague prompts) | Specific prompts, and 3–5 tools at most |
| It called a write tool before reading the state | The policy refuses it, and the refusal goes back as the tool result so the model can correct itself |

## Adding a tool

1. Add the schema to `TOOLS`. Give it a precise description, `additionalProperties: false`, and an `enum` wherever the values are fixed.
2. Add the implementation to `run_tool()`. Never call `subprocess`, `eval`, or a shell with model-supplied strings.
3. Read-only tools go in `READ_ONLY`. Every other tool needs a rule in `check_policy()`; with no rule, it's refused.
4. Add a `self_test()` case for a valid call, a malformed one, and a call the policy should refuse.
5. Run it on the board several times. Note how often the model picks the right tool, and put that rate in the app's README.

## Turn budget

Cap each turn at `max_completion_tokens` (128 is enough) and cap the turns (`--max-steps 4`). Retry a zero-token turn once with a new tag in the system prompt, as the example does.
