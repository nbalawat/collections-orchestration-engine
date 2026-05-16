"""Workflow state types and data classes for the collections orchestration engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


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

    def is_terminal(self) -> bool:
        return self in (
            JourneyStage.CURED,
            JourneyStage.CHARGED_OFF,
            JourneyStage.CLOSED,
        )


@dataclass
class ChannelEventSignal:
    event_id: str = ""
    customer_id: str = ""
    account_id: str | None = None
    channel: str = ""
    direction: str = ""
    event_type: str = ""
    intent: str | None = None
    payload: dict = field(default_factory=dict)
    occurred_at: str = ""
    correlation_id: str | None = None


@dataclass
class PaymentSignal:
    amount: float = 0.0
    payment_date: str = ""
    account_id: str = ""
    method: str = ""


@dataclass
class ComplianceFlagSignal:
    flag_type: str = ""
    reason: str = ""
    action: str = "activate"


@dataclass
class StrategyUpdateSignal:
    version: str = ""


@dataclass
class AccountInfo:
    account_id: str = ""
    customer_id: str = ""
    product_type: str = ""
    current_balance: float = 0.0
    days_past_due: int = 0
    delinquency_stage: str = ""
    total_past_due: float = 0.0
    minimum_payment: float = 0.0
    last_payment_date: str | None = None
    last_payment_amount: float | None = None
    risk_score: int | None = None
    behavioral_score: int | None = None
    relationship_value: str = "standard"
    relationship_tenure_years: int = 0
    prior_delinquencies: int = 0
    prior_cures: int = 0
    compliance_flags: list[str] = field(default_factory=list)
    preferred_channel: str | None = None
    timezone: str = "America/New_York"


@dataclass
class StrategyDecision:
    segment: dict = field(default_factory=dict)
    treatment: dict = field(default_factory=dict)
    routing: dict = field(default_factory=dict)
    compliance: dict = field(default_factory=dict)
    ai_guardrails: dict = field(default_factory=dict)
    requires_ai_review: bool = False
    strategy_version: str = "v1.0.0"
    next_eval_hours: float = 24.0


@dataclass
class ActionToDispatch:
    action_type: str = ""
    channel: str = ""
    payload: dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class ContactStats:
    """Real contact/attempt statistics computed from customer_events.

    Used to populate OPA inputs that were previously hardcoded — without these,
    compliance rules about time-of-day, attempt frequency, channel exhaustion, and
    conflicting signals cannot fire.
    """
    customer_local_hour: int = 14
    voice_attempts_7d: int = 0
    sms_attempts_7d: int = 0
    email_attempts_7d: int = 0
    dialer_attempts_7d: int = 0
    channel_attempts_7d: dict = field(default_factory=dict)
    total_attempts_7d: int = 0  # Reg F §1006.14(a) — total across all channels
    failed_channels: list[str] = field(default_factory=list)
    conflicting_signals: list[str] = field(default_factory=list)
    last_contact_at: str | None = None
    last_inbound_intent: str | None = None


@dataclass
class AIAgentResult:
    agent_type: str = ""
    action_taken: str | None = None
    response_text: str | None = None
    confidence: float = 0.0
    escalated: bool = False
    reasoning_steps: list[dict] = field(default_factory=list)
    tokens_used: int = 0
    latency_ms: int = 0


@dataclass
class JourneyState:
    customer_id: str = ""
    account_id: str = ""
    stage: JourneyStage = JourneyStage.IDLE
    previous_stage: JourneyStage | None = None
    dpd: int = 0
    balance: float = 0.0
    risk_score: int | None = None
    segment: dict = field(default_factory=dict)
    compliance_flags: list[str] = field(default_factory=list)
    suspended: bool = False
    suspension_reason: str | None = None
    strategy_version: str = "v1.0.0"
    actions_taken: list[dict] = field(default_factory=list)
    events_received: list[dict] = field(default_factory=list)
    active_ptp: dict | None = None
    channel_attempts: dict = field(default_factory=dict)
    failed_channels: list[str] = field(default_factory=list)
    last_contact_at: str | None = None
    last_action_at: str | None = None
    ai_interactions: list[dict] = field(default_factory=list)
    started_at: str = ""
    updated_at: str = ""
    evaluation_count: int = 0

    def is_terminal(self) -> bool:
        return self.stage.is_terminal()
