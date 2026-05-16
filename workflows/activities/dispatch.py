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
from workflows.types import ActionToDispatch, StrategyDecision, JourneyState, AIAgentResult

logger = logging.getLogger(__name__)
KAFKA_BOOTSTRAP = "localhost:9094"


async def _publish(topic: str, event):
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    await producer.start()
    try:
        key = getattr(event, "customer_id", None)
        key_bytes = key.encode() if key else None
        await producer.send_and_wait(topic, value=event.to_kafka_value(), key=key_bytes)
    finally:
        await producer.stop()


@activity.defn
async def dispatch_action(action: ActionToDispatch, customer_id: str, workflow_id: str) -> dict:
    event = ActionEvent(
        event_id=str(uuid.uuid4()),
        customer_id=customer_id,
        workflow_id=workflow_id,
        channel=action.channel,
        action_type=action.action_type,
        payload=action.payload,
        status="dispatched",
        occurred_at=datetime.now(timezone.utc),
        source_service="orchestrator",
    )
    await _publish(Topics.ACTIONS, event)
    logger.info("Dispatched action: %s on %s for %s", action.action_type, action.channel, customer_id)
    return {"dispatched": True, "event_id": event.event_id}


@activity.defn
async def publish_decision(decision: StrategyDecision, customer_id: str, workflow_id: str) -> str:
    event = DecisionEvent(
        event_id=str(uuid.uuid4()),
        customer_id=customer_id,
        workflow_id=workflow_id,
        strategy_version=decision.strategy_version,
        policy_name="collections.treatment",
        actions=[],
        decision_type="strategy_evaluation",
        occurred_at=datetime.now(timezone.utc),
        source_service="orchestrator",
    )
    await _publish(Topics.DECISIONS, event)
    return event.event_id


@activity.defn
async def publish_lifecycle(
    customer_id: str,
    workflow_id: str,
    from_stage: str | None,
    to_stage: str,
    reason: str,
    triggered_by: str,
) -> str:
    event = LifecycleEvent(
        event_id=str(uuid.uuid4()),
        customer_id=customer_id,
        workflow_id=workflow_id,
        from_stage=from_stage,
        to_stage=to_stage,
        reason=reason,
        triggered_by=triggered_by,
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
