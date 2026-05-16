"""Base agent class using Claude Agent SDK tool runner pattern.

Every agent uses `client.beta.messages.tool_runner()` which handles the full agentic loop
automatically — calling tools, feeding results back, repeating until done. Tools are
decorated with `@beta_async_tool` and defined in tools.py. Every invocation produces
a reasoning trace event for the AI Explorer UI.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from anthropic import AsyncAnthropic

from events.models import AIReasoningTraceEvent, ReasoningStep, AgentType

logger = logging.getLogger(__name__)


class CollectionsAgent:
    agent_type: AgentType = AgentType.DIGITAL_CHANNEL
    model: str = "claude-sonnet-4-6"
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
        reasoning_steps: list[ReasoningStep] = []
        total_tokens = 0

        system_prompt = self.get_system_prompt()
        tools = self.get_tools()
        user_message = self._build_user_message(context)

        reasoning_steps.append(ReasoningStep(
            step="context_loaded",
            result=f"Customer: {context.get('customer_id', 'unknown')}",
        ))

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
                            result=str(block.input)[:300],
                        ))
                    elif block.type == "tool_result":
                        reasoning_steps.append(ReasoningStep(
                            step=f"tool_result",
                            result=str(block)[:300],
                        ))

                final_message = message

            result = self._extract_result(final_message, context)
            elapsed_ms = int((time.time() - start_time) * 1000)

            trace = AIReasoningTraceEvent(
                event_id=str(uuid.uuid4()),
                agent_type=self.agent_type,
                customer_id=context.get("customer_id"),
                workflow_id=context.get("workflow_id"),
                input_summary=self._summarize_input(context),
                reasoning_steps=reasoning_steps,
                action_taken=result.get("action_taken"),
                confidence=result.get("confidence", 0.0),
                escalated=result.get("escalated", False),
                tokens_used=total_tokens,
                latency_ms=elapsed_ms,
                model=self.model,
                occurred_at=datetime.now(timezone.utc),
                source_service=f"ai-agent-{self.agent_type.value}",
            )

            result["reasoning_trace"] = trace.model_dump(mode="json")
            result["tokens_used"] = total_tokens
            result["latency_ms"] = elapsed_ms
            return result

        except Exception as e:
            logger.exception("Agent invocation failed")
            return {
                "error": str(e),
                "action_taken": None,
                "escalated": True,
                "confidence": 0.0,
            }

    def _extract_result(self, message, context: dict) -> dict:
        if message is None:
            return {"response_text": "", "action_taken": None, "confidence": 0.0, "escalated": True}

        text_blocks = [b.text for b in message.content if b.type == "text"]
        response_text = "\n".join(text_blocks)

        action_taken = None
        escalated = False
        confidence = 0.85

        response_lower = response_text.lower()
        if "escalat" in response_lower:
            escalated = True
            action_taken = "escalated_to_human"
        elif "payment link" in response_lower:
            action_taken = "sent_payment_link"
        elif "promise to pay" in response_lower or "ptp" in response_lower:
            action_taken = "recorded_ptp"
        elif "hardship" in response_lower:
            action_taken = "initiated_hardship"
        elif "settlement" in response_lower:
            action_taken = "settlement_discussion"
        elif "arrangement" in response_lower:
            action_taken = "offered_arrangement"
        else:
            action_taken = "responded"

        return {
            "response_text": response_text,
            "action_taken": action_taken,
            "confidence": confidence,
            "escalated": escalated,
        }

    def _summarize_input(self, context: dict) -> str:
        parts = []
        if context.get("customer_id"):
            parts.append(f"Customer: {context['customer_id']}")
        if context.get("message"):
            parts.append(f"Message: {context['message'][:100]}")
        if context.get("channel"):
            parts.append(f"Channel: {context['channel']}")
        return " | ".join(parts) or "No context"
