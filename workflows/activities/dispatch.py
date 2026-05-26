"""Activities for dispatching actions and publishing events to Kafka."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import orjson
from aiokafka import AIOKafkaProducer
from temporalio import activity

from events.models import ActionEvent, DecisionEvent, LifecycleEvent, ComplianceEvent, AIReasoningTraceEvent
from events.topics import Topics
from services.shared.config import get_settings
from workflows.types import ActionToDispatch, StrategyDecision, JourneyState, AIAgentResult

logger = logging.getLogger(__name__)


async def _publish(topic: str, event):
    producer = AIOKafkaProducer(bootstrap_servers=get_settings().kafka_bootstrap_servers)
    await producer.start()
    try:
        key = getattr(event, "customer_id", None)
        key_bytes = key.encode() if key else None
        await producer.send_and_wait(topic, value=event.to_kafka_value(), key=key_bytes)
    finally:
        await producer.stop()


@activity.defn
async def dispatch_action(action: ActionToDispatch, customer_id: str, workflow_id: str, trace_id: str | None = None) -> dict:
    event = ActionEvent(
        event_id=str(uuid.uuid4()),
        customer_id=customer_id,
        workflow_id=workflow_id,
        channel=action.channel,
        action_type=action.action_type,
        payload=action.payload,
        status="dispatched",
        correlation_id=trace_id,
        occurred_at=datetime.now(timezone.utc),
        source_service="orchestrator",
    )
    await _publish(Topics.ACTIONS, event)
    logger.info("Dispatched action: %s on %s for %s (trace=%s)", action.action_type, action.channel, customer_id, trace_id)
    return {"dispatched": True, "event_id": event.event_id}


@activity.defn
async def publish_decision(decision: StrategyDecision, customer_id: str, workflow_id: str, trace_id: str | None = None) -> str:
    # Pack full decision rationale into the payload so the UI can show WHY, not just WHAT.
    rationale_payload = {
        "segment": decision.segment,
        "treatment": decision.treatment,
        "routing": decision.routing,
        "compliance_view": decision.compliance,
        "requires_ai_review": decision.requires_ai_review,
        "next_eval_hours": decision.next_eval_hours,
    }
    event = DecisionEvent(
        event_id=str(uuid.uuid4()),
        customer_id=customer_id,
        workflow_id=workflow_id,
        strategy_version=decision.strategy_version,
        policy_name="collections.treatment",
        actions=[],
        decision_type="strategy_evaluation",
        correlation_id=trace_id,
        occurred_at=datetime.now(timezone.utc),
        source_service="orchestrator",
    )
    # DecisionEvent doesn't have a free-form payload field; inject via model_dump override.
    raw = event.model_dump(mode="json")
    raw["rationale"] = rationale_payload
    import orjson as _orjson
    producer = AIOKafkaProducer(bootstrap_servers=get_settings().kafka_bootstrap_servers)
    await producer.start()
    try:
        key_bytes = customer_id.encode() if customer_id else None
        await producer.send_and_wait(Topics.DECISIONS, value=_orjson.dumps(raw), key=key_bytes)
    finally:
        await producer.stop()
    return event.event_id


@activity.defn
async def publish_lifecycle(
    customer_id: str,
    workflow_id: str,
    from_stage: str | None,
    to_stage: str,
    reason: str,
    triggered_by: str,
    trace_id: str | None = None,
) -> str:
    event = LifecycleEvent(
        event_id=str(uuid.uuid4()),
        customer_id=customer_id,
        workflow_id=workflow_id,
        from_stage=from_stage,
        to_stage=to_stage,
        reason=reason,
        triggered_by=triggered_by,
        correlation_id=trace_id,
        occurred_at=datetime.now(timezone.utc),
        source_service="orchestrator",
    )
    await _publish(Topics.LIFECYCLE, event)
    return event.event_id


@activity.defn
async def publish_compliance_event(
    customer_id: str,
    workflow_id: str,
    check_type: str,
    passed: bool,
    rule_name: str,
    details: dict,
    action_blocked: str | None,
    trace_id: str | None = None,
) -> str:
    event = ComplianceEvent(
        event_id=str(uuid.uuid4()),
        customer_id=customer_id,
        workflow_id=workflow_id,
        check_type=check_type,
        passed=passed,
        rule_name=rule_name,
        details=details,
        action_blocked=action_blocked,
        correlation_id=trace_id,
        occurred_at=datetime.now(timezone.utc),
        source_service="orchestrator",
    )
    await _publish(Topics.COMPLIANCE, event)
    return event.event_id


@activity.defn
async def publish_ai_reasoning(
    agent_result: AIAgentResult,
    customer_id: str,
    workflow_id: str,
) -> str:
    event = AIReasoningTraceEvent(
        event_id=str(uuid.uuid4()),
        agent_type=agent_result.agent_type,
        customer_id=customer_id,
        workflow_id=workflow_id,
        input_summary="",
        reasoning_steps=[],
        action_taken=agent_result.action_taken,
        confidence=agent_result.confidence,
        escalated=agent_result.escalated,
        tokens_used=agent_result.tokens_used,
        latency_ms=agent_result.latency_ms,
        model="claude-sonnet-4-6",
        occurred_at=datetime.now(timezone.utc),
        source_service=f"ai-agent-{agent_result.agent_type}",
    )
    await _publish(Topics.AI_REASONING, event)
    return event.event_id
