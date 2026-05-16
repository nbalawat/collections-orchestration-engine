"""Base AI agent harness — Claude Agent SDK tool runner with required structured decision.

Every agent invocation:
  1. Runs the tool_runner loop
  2. Auto-appends `record_decision` to the agent's tool list
  3. Adds a system-prompt addendum demanding the LLM call record_decision before ending
  4. Captures the structured payload from the tool_use block (NOT from response text)
  5. Persists a row to agent_actions
  6. Emits a reasoning trace event with every tool call + intermediate output

Adapt:
  - Change `model` to your provider's model id
  - Change `execute_insert` to your project's DB helper
  - Implement your `record_reasoning_trace` to emit to your event stream
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from anthropic import AsyncAnthropic
from .record_decision import record_decision  # the required closing tool

logger = logging.getLogger(__name__)


async def execute_insert(sql: str, params: dict) -> None:
    """Replace with your project's DB helper."""
    raise NotImplementedError("plug in your project's DB helper")


async def record_reasoning_trace(trace: dict) -> None:
    """Replace with your project's event publisher (Kafka, EventBridge, etc.)."""
    raise NotImplementedError("plug in your project's event publisher")


class CollectionsAgent:
    """Base class — subclass for each agent role.

    Subclass responsibilities:
      - agent_type: str class attr (e.g. "digital_channel")
      - get_system_prompt() -> str
      - get_tools() -> list of @beta_async_tool functions (without record_decision)
      - _build_user_message(context) -> str
    """

    agent_type: str = "generic"
    model: str = "claude-opus-4-7"
    max_tokens: int = 4096

    def __init__(self):
        self.client = AsyncAnthropic()

    def get_system_prompt(self) -> str:
        raise NotImplementedError

    def get_tools(self) -> list:
        raise NotImplementedError

    def _build_user_message(self, context: dict) -> str:
        raise NotImplementedError

    async def invoke(self, context: dict) -> dict:
        start_time = time.time()
        reasoning_steps: list[dict] = []
        total_tokens = 0

        tools = list(self.get_tools())
        if record_decision not in tools:
            tools.append(record_decision)

        decision_addendum = (
            "\n\n## FINAL STEP — REQUIRED\n"
            "Before you finish, you MUST call the `record_decision` tool with:\n"
            "  - action_type: the concrete action you took or are recommending\n"
            "  - confidence: 0.0–1.0, calibrated to your actual evidence "
            "(do not default to 0.85; reflect uncertainty honestly)\n"
            "  - rationale: 1-3 sentences citing the evidence\n"
            "  - escalate: true if a human should take over\n"
            "  - parameters: JSON string with structured parameters\n"
            "If you cannot complete the analysis, still call record_decision with "
            "action_type='escalated_to_human' and explain why."
        )
        system_prompt = self.get_system_prompt() + decision_addendum
        user_message = self._build_user_message(context)

        recorded_decision: dict | None = None

        try:
            runner = self.client.beta.messages.tool_runner(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                tools=tools,
                messages=[{"role": "user", "content": user_message}],
            )

            async for message in runner:
                total_tokens += message.usage.input_tokens + message.usage.output_tokens
                for block in message.content:
                    if block.type == "tool_use":
                        reasoning_steps.append({
                            "step": f"tool_call:{block.name}",
                            "result": json.dumps(block.input, default=str)[:600],
                        })
                        if block.name == "record_decision":
                            recorded_decision = {
                                "action_type": block.input.get("action_type", "unknown"),
                                "confidence": float(block.input.get("confidence", 0.0)),
                                "rationale": block.input.get("rationale", ""),
                                "escalate": bool(block.input.get("escalate", False)),
                                "parameters": _parse_params(block.input.get("parameters", "{}")),
                            }

            elapsed_ms = int((time.time() - start_time) * 1000)

            if recorded_decision is None:
                logger.warning("Agent %s ended without record_decision call", self.agent_type)
                recorded_decision = {
                    "action_type": "incomplete_no_decision",
                    "confidence": 0.0,
                    "rationale": "Agent ended its turn without recording a structured decision.",
                    "escalate": True,
                    "parameters": {},
                }

            customer_id = context.get("customer_id") or ""
            workflow_id = context.get("workflow_id")
            trace_id = uuid.uuid4()

            if customer_id:
                try:
                    await execute_insert(
                        """INSERT INTO agent_actions
                           (action_id, trace_id, agent_type, customer_id, workflow_id,
                            action_type, parameters, rationale, confidence, status)
                           VALUES (:action_id, :trace_id, :agent_type, :cid, :wid,
                                   :atype, :params, :rationale, :conf, :status)""",
                        {
                            "action_id": str(uuid.uuid4()),
                            "trace_id":  str(trace_id),
                            "agent_type": self.agent_type,
                            "cid":   customer_id,
                            "wid":   workflow_id,
                            "atype": recorded_decision["action_type"],
                            "params": json.dumps(recorded_decision["parameters"]),
                            "rationale": recorded_decision["rationale"],
                            "conf":   recorded_decision["confidence"],
                            "status": "escalated" if recorded_decision["escalate"] else "recorded",
                        },
                    )
                except Exception:
                    logger.exception("Failed to persist agent_action")

            await record_reasoning_trace({
                "event_id":      str(trace_id),
                "agent_type":    self.agent_type,
                "customer_id":   customer_id or None,
                "workflow_id":   workflow_id,
                "reasoning_steps": reasoning_steps,
                "action_taken":  recorded_decision["action_type"],
                "confidence":    recorded_decision["confidence"],
                "escalated":     recorded_decision["escalate"],
                "tokens_used":   total_tokens,
                "latency_ms":    elapsed_ms,
                "model":         self.model,
                "occurred_at":   datetime.now(timezone.utc).isoformat(),
            })

            return {
                "action_taken":   recorded_decision["action_type"],
                "confidence":     recorded_decision["confidence"],
                "escalated":      recorded_decision["escalate"],
                "rationale":      recorded_decision["rationale"],
                "parameters":     recorded_decision["parameters"],
                "tokens_used":    total_tokens,
                "latency_ms":     elapsed_ms,
                "trace_id":       str(trace_id),
            }

        except Exception as e:
            logger.exception("Agent invocation failed")
            return {
                "error": str(e),
                "action_taken": "agent_error",
                "escalated": True,
                "confidence": 0.0,
                "rationale": f"Agent crashed: {e}",
            }


def _parse_params(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"raw": str(value)}
