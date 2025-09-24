# Troubleshooting: Principal Produces Blank Outputs

This document captures a recurring symptom where the Principal agent stalls or “finishes” with no visible content, particularly when launching execution or synthesizing Associate results. It outlines likely root causes, how to validate them without code changes, and targeted actions to isolate the underlying issue.

## Symptom
- During the Principal stage, the LLM final response has empty `content` while the run appears to progress or terminate.
- Associates may complete their tasks, but the Principal fails to generate a summary or call finalization tools (e.g., `generate_markdown_report`, `finish_flow`).
- In UI: the Principal “can’t continue” or silently ends, often after a larger context exchange.

## Why Principal Is More Susceptible
- Larger prompts: Principal prompt includes many segments plus tool descriptions and plan state, stressing the provider/bridge and context window.
- Strict post-turn rules: A profile rule ends the turn immediately on empty content, masking real failures and preventing recovery.
- Reasoning-only output: Some providers/bridges emit “reasoning” without user-facing `content`. Current rules treat this as “empty”.

Relevant files:
- Profile: `core/agent_profiles/profiles/Principal_Planner_EN.yaml`
- Node engine: `core/agent_core/nodes/base_agent_node.py`
- LLM streaming: `core/agent_core/llm/call_llm.py`
- Tool registry/prompt size: `core/agent_core/framework/tool_registry.py`

## Potential Root Causes (ranked)
1) Principal profile rule masks blanks
- Rule: `post_turn_observers` → `rule_immediate_meltdown_on_empty_content`
- Effect: If `content` is empty and no tool was called, the Principal immediately ends the turn with “success”, hiding failures.

2) Context window/overload
- Principal’s prompt + tools + plan state can exceed or stress the model/bridge; some providers then emit minimal/empty content or only reasoning.

3) Bridge transform edge cases
- The Gemini→OpenAI bridge may produce responses with low/no `message.content` under heavy prompts, or differ in how reasoning/tool deltas are surfaced.

4) Content-only checks in logic
- Flow/observer rules use `content` emptiness to decide; they ignore `reasoning_content`, so reasoning-only responses are treated as empty and cause early termination.

5) Tool description bloat
- Injecting large tool descriptions for Principal inflates token usage and increases likelihood of degraded/blank outputs.

## How To Validate (no code changes)
Use existing logs and events to confirm the nature of “blank” responses.

1) Inspect WebSocket events
- Look for `llm_chunk` events: do you see `reasoning` deltas but no `content`? Are there zero/late `tool_calls`?
- Final `llm_response` with `data.content: ""` but `reasoning` present indicates reasoning-only outputs.

2) Check backend logs for aggregation metrics
- Log key: `llm_response_aggregated` (from `call_llm.py`).
  - Inspect `content_length`, `tool_calls_count`, `reasoning_length` in `extra` fields.
  - If `content_length=0` and `reasoning_length>0`, the profile’s empty-content rule likely triggered prematurely.

3) Examine Turn/state snapshots
- In team state/turns, check the last assistant message:
  - `content == ""` and `reasoning_content` populated?
  - `state.current_action` unset (no tool call)? That matches the “empty content meltdown” path.
- Optional: enable state dump to file with env `STATE_DUMP=true` for Principal flow completion (`flow.py`).

4) Compare behavior across models/providers
- Temporarily point Principal to another provider/model via `principal_llm` and see if blanks subside. If they do, bridge/provider behavior is implicated.

5) Bridge logs
- Run the bridge in debug/verbose and confirm it emits non-empty `choices[].message.content` for large prompts. Differences here point to adapter issues.

## Suggested Actions To Isolate Root Cause

Short, reversible experiments; apply one at a time and observe with the above validation steps.

1) Relax the Principal’s immediate empty-content rule
- Change behavior of `rule_immediate_meltdown_on_empty_content` from ending the turn “success” to a self-reflection retry (or no-op). If progress resumes, the rule was masking valid-but-delayed outputs.

2) Consider reasoning-only as a non-empty signal
- Adjust decision rules to treat messages with `reasoning_content` as “made progress” even if `content` is empty, avoiding premature termination.

3) Reduce prompt/tool noise for Principal
- Temporarily narrow `allowed_toolsets` for Principal, or remove lower-priority `system_prompt_segments` to cut tokens. If blanks disappear, token pressure is the primary driver.

4) Swap model/provider for Principal
- Point `principal_llm` to a different, reliable model/endpoint. If the issue disappears, the bridge/provider path is the main culprit.

5) Increase monitoring granularity
- Enable `DEBUG_LLM=1` to record chunk-by-chunk details from the provider for the failing turns (already supported in `call_llm.py`).

## Experiment Matrix (what to expect)
- E1: Relax empty-content rule → If Principal resumes tool calling or summarization, rule masking was primary.
- E2: Treat reasoning-only as valid → If Principal stops “finishing empty” and continues thinking, provider emits reasoning-only under load.
- E3: Reduce prompt/toolsets → If blanks vanish, context load is the main trigger.
- E4: Change model/provider → If blanks vanish, bridge/provider translation is implicated.
- E5: Debug bridge → Logs show content present pre-bridge but empty post-bridge → adapter transform issue.

## Monitoring & Signals
- WS: `llm_chunk` and `llm_response` payloads.
- Logs: `llm_response_aggregated`, `token_estimation_failed`, `ContextWindowExceededError`, retry logs.
- State: `state.current_action`, last assistant message `content` vs `reasoning_content`.

## Success Criteria
- Principal reliably continues past planning into dispatch/synthesis.
- Final report step consistently emits non-empty content or calls `generate_markdown_report` + `finish_flow`.
- No premature “success” end states on empty `content` when `reasoning_content` or tool calls are present.

## Notes
- This phenomenon tends to surface at the Principal due to higher token budgets and stricter decision rules; Associates are less impacted because they call tools quickly with smaller prompts.
- The bridge can amplify the symptom, but the profile rule and content-only checks are strong multipliers—addressing those first is often the most effective lever.

## 2025-09-19: Partner & Runtime Tweaks to Prevent Empty-Response Stalls

While testing with Gemini via the MCP bridge, we hit a related-but-earlier failure: after the user approved the Partner’s plan, the follow-up turn intended to call `manage_work_modules` returned an entirely blank response. Because no tool call was emitted, the turn ended in `error` and the plan never formalized.

### What Changed

1. **Partner prompt guidance tightened** (`core/agent_profiles/profiles/Partner_StrategicAdvisor_EN.yaml`)
   - Descriptions are now explicitly limited to short, numbered steps.
   - Ares is instructed to send work modules in batches of ≤3 and to process one pillar at a time.
   - On receiving an internal retry directive, Ares resends the next batch with even smaller payloads.

2. **Automated retry directives**
   - New post-turn observer `retry_manage_work_modules_after_blank_turn` detects when the previous assistant message was empty and queues an `INTERNAL_DIRECTIVE` reminding the Partner to immediately retry with a smaller batch.
   - Runtime safety net in `base_agent_node.post_async` injects the same retry directive whenever the LLM throws `FunctionCallErrorException` with the “empty response” message.

### Why

- A single tool call that attempts to create 8–10 work modules (each with multi-sentence descriptions) can push the Gemini bridge toward timeout/blank outputs.
- Without a structured reminder, the agent simply fails the turn and waits for user input, forcing manual intervention.

### Result

- After restarting the backend (`docker compose restart core`), approved plans now produce a sequence of smaller `manage_work_modules` calls. If Gemini returns nothing, the Partner immediately retries using the directive, keeping the flow moving without manual resets.
