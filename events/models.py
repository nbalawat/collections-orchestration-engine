from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ─── Enums ────────────────────────────────────────────────────────────

class Channel(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    VOICE = "voice"
    DIALER = "dialer"
    DIGITAL = "digital"
    SYSTEM = "system"


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SYSTEM = "system"


class DelinquencyStage(str, Enum):
    CURRENT = "CURRENT"
    PRE_DELINQUENT = "PRE_DELINQUENT"
    EARLY = "EARLY"
    MID = "MID"
    LATE = "LATE"
    SEVERE = "SEVERE"
    PRE_CHARGE_OFF = "PRE_CHARGE_OFF"
    CHARGE_OFF = "CHARGE_OFF"


class JourneyStage(str, Enum):
    IDLE = "IDLE"
    DUNNING = "DUNNING"
    PTP_ACTIVE = "PTP_ACTIVE"
    PTP_BROKEN = "PTP_BROKEN"
    HARDSHIP_REVIEW = "HARDSHIP_REVIEW"
    ARRANGEMENT_OFFERED = "ARRANGEMENT_OFFERED"
    ARRANGEMENT_ACTIVE = "ARRANGEMENT_ACTIVE"
    SETTLEMENT_OFFERED = "SETTLEMENT_OFFERED"
    SETTLEMENT_NEGOTIATION = "SETTLEMENT_NEGOTIATION"
    SETTLEMENT_ACTIVE = "SETTLEMENT_ACTIVE"
    MODIFICATION_ACTIVE = "MODIFICATION_ACTIVE"
    SUSPENDED = "SUSPENDED"
    CURED = "CURED"
    CHARGED_OFF = "CHARGED_OFF"
    CLOSED = "CLOSED"


class ComplianceFlagType(str, Enum):
    BANKRUPTCY = "BANKRUPTCY"
    CEASE_AND_DESIST = "CEASE_AND_DESIST"
    ATTORNEY_REPRESENTED = "ATTORNEY_REPRESENTED"
    FRAUD = "FRAUD"
    DECEASED = "DECEASED"
    SCRA_MILITARY = "SCRA_MILITARY"
    DISPUTE = "DISPUTE"
    DISASTER = "DISASTER"
    IDENTITY_THEFT = "IDENTITY_THEFT"


class Intent(str, Enum):
    PTP = "PTP"
    HARDSHIP = "HARDSHIP"
    DISPUTE = "DISPUTE"
    COMPLAINT = "COMPLAINT"
    PAYMENT_QUESTION = "PAYMENT_QUESTION"
    BALANCE_INQUIRY = "BALANCE_INQUIRY"
    SETTLEMENT_INQUIRY = "SETTLEMENT_INQUIRY"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    GENERAL_INQUIRY = "GENERAL_INQUIRY"
    PAYMENT_CONFIRMATION = "PAYMENT_CONFIRMATION"
    REFUSAL_TO_PAY = "REFUSAL_TO_PAY"
    THREAT_LEGAL = "THREAT_LEGAL"
    DISTRESS = "DISTRESS"


class AgentType(str, Enum):
    DIGITAL_CHANNEL = "digital_channel"
    COPILOT = "copilot"
    CASE_REASONING = "case_reasoning"
    PORTFOLIO_INTELLIGENCE = "portfolio_intelligence"
    QUALITY_COMPLIANCE = "quality_compliance"


# ─── Base Event ───────────────────────────────────────────────────────

class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=_uuid)
    occurred_at: datetime = Field(default_factory=_now)
    correlation_id: str | None = None
    source_service: str | None = None

    def to_kafka_value(self) -> bytes:
        import orjson
        return orjson.dumps(self.model_dump(mode="json"))

    @classmethod
    def from_kafka_value(cls, data: bytes):
        import orjson
        return cls.model_validate(orjson.loads(data))


# ─── Channel Events ──────────────────────────────────────────────────

class ChannelEvent(BaseEvent):
    customer_id: str
    account_id: str | None = None
    channel: Channel
    direction: Direction
    event_type: str
    intent: Intent | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None


# ─── Decision Events (from orchestrator) ─────────────────────────────

class StrategyInput(BaseModel):
    customer_id: str
    account_id: str | None = None
    dpd: int
    balance: float
    risk_score: int | None = None
    segment: str | None = None
    journey_stage: str | None = None
    channel_history: list[str] = Field(default_factory=list)
    compliance_flags: list[str] = Field(default_factory=list)
    prior_treatments: list[str] = Field(default_factory=list)


class StrategyAction(BaseModel):
    action_type: str
    channel: Channel | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    reason: str | None = None


class DecisionEvent(BaseEvent):
    customer_id: str
    account_id: str | None = None
    workflow_id: str | None = None
    strategy_version: str | None = None
    policy_name: str | None = None
    input_context: StrategyInput | None = None
    actions: list[StrategyAction] = Field(default_factory=list)
    decision_type: str = "strategy_evaluation"


# ─── Action Events (dispatched by orchestrator) ──────────────────────

class ActionEvent(BaseEvent):
    customer_id: str
    account_id: str | None = None
    workflow_id: str | None = None
    channel: Channel
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "dispatched"


# ─── Lifecycle Events (journey state changes) ────────────────────────

class LifecycleEvent(BaseEvent):
    customer_id: str
    account_id: str | None = None
    workflow_id: str | None = None
    from_stage: JourneyStage | None = None
    to_stage: JourneyStage
    reason: str | None = None
    triggered_by: str | None = None


# ─── Compliance Events ───────────────────────────────────────────────

class ComplianceEvent(BaseEvent):
    customer_id: str
    account_id: str | None = None
    workflow_id: str | None = None
    check_type: str
    passed: bool
    rule_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    action_blocked: str | None = None


# ─── AI Reasoning Trace Events ───────────────────────────────────────

class ReasoningStep(BaseModel):
    step: str
    result: str
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIReasoningTraceEvent(BaseEvent):
    agent_type: AgentType
    customer_id: str | None = None
    workflow_id: str | None = None
    input_summary: str
    reasoning_steps: list[ReasoningStep] = Field(default_factory=list)
    action_taken: str | None = None
    confidence: float | None = None
    escalated: bool = False
    tokens_used: int | None = None
    latency_ms: int | None = None
    model: str | None = None


# ─── Quality Review Events ───────────────────────────────────────────

class QualityReviewEvent(BaseEvent):
    interaction_id: str
    customer_id: str
    agent_type: str | None = None
    channel: Channel | None = None
    compliance_score: float | None = None
    tone_score: float | None = None
    accuracy_score: float | None = None
    completeness_score: float | None = None
    overall_score: float | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    coaching_notes: str | None = None


# ─── Customer 360 (read model, assembled from multiple sources) ──────

class Customer360(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    email: str | None = None
    phone_primary: str | None = None
    timezone: str = "America/New_York"
    preferred_channel: str | None = None
    relationship_start: str | None = None
    relationship_value: str = "standard"
    risk_score: int | None = None
    behavioral_score: int | None = None
    segment: str | None = None
    accounts: list[AccountSummary] = Field(default_factory=list)
    compliance_flags: list[str] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    active_ptps: list[dict[str, Any]] = Field(default_factory=list)
    journey_state: dict[str, Any] = Field(default_factory=dict)
    ai_recommendations: list[dict[str, Any]] = Field(default_factory=list)


class AccountSummary(BaseModel):
    account_id: str
    product_type: str
    current_balance: float
    days_past_due: int
    delinquency_stage: str
    total_past_due: float
    last_payment_date: str | None = None
    last_payment_amount: float | None = None
