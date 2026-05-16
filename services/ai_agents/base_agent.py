"""Base agent — Claude Agent SDK tool runner with a required structured decision.

Every agent invocation:
  1. Runs the agent loop (tool calls + reasoning)
  2. Requires the agent to call `record_decision(action_type, confidence, rationale, ...)`
     before ending — that tool call is the ground-truth action/confidence (NOT inferred
     from text)
  3. Persists the decision to agent_actions
  4. Emits a reasoning trace event with the actual tool calls/results
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from anthropic import AsyncAnthropic

from events.models import AIReasoningTraceEvent, ReasoningStep, AgentType
from services.shared.anthropic_client import make_async_client
from services.shared.db import execute_insert

logger = logging.getLogger(__name__)


class CollectionsAgent:
    agent_type: AgentType = AgentType.DIGITAL_CHANNEL
    model: str = "claude-opus-4-7"
    max_tokens: int = 4096

    def __init__(self):
        self.client = make_async_client()

    def get_system_prompt(self) -> str:
        raise NotImplementedError

    def get_tools(self) -> list:
        raise NotImplementedError

    def _build_user_message(self, context: dict) -> str:
        raise NotImplementedError

    async def invoke(self, context: dict) -> dict:
        start_time = time.time()
        reasoning_steps: list[ReasoningStep] = []
        total_tokens = 0

        # Always include record_decision as the closing tool — every subclass gets it.
        from services.ai_agents.tools import record_decision
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
            "  - parameters: JSON string with structured parameters (amounts, dates, channels)\n"
            "If you cannot complete the analysis, still call record_decision with action_type='escalated_to_human' and explain why."
        )
        system_prompt = self.get_system_prompt() + decision_addendum
        user_message = self._build_user_message(context)

        reasoning_steps.append(ReasoningStep(
            step="context_loaded",
            result=f"Customer: {context.get('customer_id', 'unknown')}",
        ))

        recorded_decision: dict | None = None

        try:
            runner = self.client.beta.messages.tool_runner(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                tools=tools,
                messages=[{"role": "user", "content": user_message}],
            )

            final_message = None
            async for message in runner:
                total_tokens += message.usage.input_tokens + message.usage.output_tokens

                for block in message.content:
                    if block.type == "tool_use":
                        reasoning_steps.append(ReasoningStep(
                            step=f"tool_call:{block.name}",
                            result=json.dumps(block.input, default=str)[:600],
                        ))
                        if block.name == "record_decision":
                            # The LLM is asking to record — capture the structured input directly.
                            recorded_decision = {
                                "action_type": block.input.get("action_type", "unknown"),
                                "confidence": float(block.input.get("confidence", 0.0)),
                                "rationale": block.input.get("rationale", ""),
                                "escalate": bool(block.input.get("escalate", False)),
                                "parameters": _parse_params(block.input.get("parameters", "{}")),
                            }
                    elif block.type == "tool_result":
                        reasoning_steps.append(ReasoningStep(
                            step="tool_result",
                            result=_block_to_text(block)[:600],
                        ))
                    elif block.type == "text":
                        text = block.text or ""
                        if text.strip():
                            reasoning_steps.append(ReasoningStep(
                                step="text",
                                result=text[:600],
                            ))

                final_message = message

            response_text = _final_text(final_message)
            elapsed_ms = int((time.time() - start_time) * 1000)

            if recorded_decision is None:
                # Agent ended without calling record_decision — that itself is a signal.
                logger.warning("Agent %s ended without record_decision call", self.agent_type.value)
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

            # Persist the action to agent_actions (the receipt).
            if customer_id:
                try:
                    await execute_insert("""
                        INSERT INTO agent_actions (action_id, trace_id, agent_type, customer_id,
                                                   workflow_id, action_type, parameters,
                                                   rationale, confidence, status)
                        VALUES (:action_id, :trace_id, :agent_type, :cid, :wid,
                                :atype, :params, :rationale, :conf, :status)
                    """, {
                        "action_id": str(uuid.uuid4()),
                        "trace_id": str(trace_id),
                        "agent_type": self.agent_type.value,
                        "cid": customer_id,
                        "wid": workflow_id,
                        "atype": recorded_decision["action_type"],
                        "params": json.dumps(recorded_decision["parameters"]),
                        "rationale": recorded_decision["rationale"],
                        "conf": recorded_decision["confidence"],
                        "status": "escalated" if recorded_decision["escalate"] else "recorded",
                    })
                except Exception:
                    logger.exception("Failed to persist agent_action")

            trace = AIReasoningTraceEvent(
                event_id=str(trace_id),
                agent_type=self.agent_type,
                customer_id=customer_id or None,
                workflow_id=workflow_id,
                input_summary=self._summarize_input(context),
                reasoning_steps=reasoning_steps,
                action_taken=recorded_decision["action_type"],
                confidence=recorded_decision["confidence"],
                escalated=recorded_decision["escalate"],
                tokens_used=total_tokens,
                latency_ms=elapsed_ms,
                model=self.model,
                occurred_at=datetime.now(timezone.utc),
                source_service=f"ai-agent-{self.agent_type.value}",
            )

            return {
                "response_text": response_text,
                "action_taken": recorded_decision["action_type"],
                "confidence": recorded_decision["confidence"],
                "escalated": recorded_decision["escalate"],
                "rationale": recorded_decision["rationale"],
                "parameters": recorded_decision["parameters"],
                "reasoning_trace": trace.model_dump(mode="json"),
                "tokens_used": total_tokens,
                "latency_ms": elapsed_ms,
                "trace_id": str(trace_id),
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

    def _summarize_input(self, context: dict) -> str:
        parts = []
        if context.get("customer_id"):
            parts.append(f"Customer: {context['customer_id']}")
        if context.get("message"):
            parts.append(f"Message: {context['message'][:100]}")
        if context.get("channel"):
            parts.append(f"Channel: {context['channel']}")
        if context.get("reason"):
            parts.append(f"Reason: {context['reason'][:120]}")
        return " | ".join(parts) or "No context"


def _parse_params(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"raw": str(value)}


def _block_to_text(block) -> str:
    content = getattr(block, "content", None)
    if isinstance(content, list):
        parts = [getattr(c, "text", str(c)) for c in content]
        return " ".join(parts)
    if isinstance(content, str):
        return content
    return str(block)


def _final_text(message) -> str:
    if message is None:
        return ""
    return "\n".join(b.text for b in message.content if b.type == "text")
