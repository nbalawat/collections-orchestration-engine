"""CustomerJourney — the main per-customer Temporal workflow.

One instance per delinquent account. Starts when an account goes past due,
ends on cure, settlement completion, or charge-off. Reacts to channel events,
payments, compliance signals, and strategy updates.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from workflows.types import (
        AccountInfo,
        ActionToDispatch,
        AIAgentResult,
        ChannelEventSignal,
        ComplianceFlagSignal,
        JourneyStage,
        JourneyState,
        PaymentSignal,
        StrategyDecision,
        StrategyUpdateSignal,
    )
    from workflows.activities import account, strategy, compliance, dispatch


ACTIVITY_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))


@workflow.defn
class CustomerJourney:

    def __init__(self) -> None:
        self.state = JourneyState()
        self.inbox: list[ChannelEventSignal] = []
        self.payment_inbox: list[PaymentSignal] = []
        self.pending_tick = False

    # ── Main workflow loop ───────────────────────────────────────────

    @workflow.run
    async def run(self, customer_id: str) -> dict:
        self.state.customer_id = customer_id
        self.state.started_at = str(workflow.now())
        self.state.updated_at = str(workflow.now())

        info: AccountInfo = await workflow.execute_activity(
            account.lookup_account,
            customer_id,
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=ACTIVITY_RETRY,
        )
        self.state.account_id = info.account_id
        self.state.dpd = info.days_past_due
        self.state.balance = info.current_balance
        self.state.risk_score = info.risk_score
        self.state.compliance_flags = info.compliance_flags

        await self._transition(JourneyStage.DUNNING, "journey_started", "system")

        while not self.state.is_terminal():
            await workflow.wait_condition(
                lambda: bool(self.inbox) or bool(self.payment_inbox) or self.pending_tick or self.state.suspended
            )

            if self.state.suspended:
                await workflow.wait_condition(lambda: not self.state.suspended)
                continue

            while self.payment_inbox:
                pmt = self.payment_inbox.pop(0)
                await self._handle_payment(pmt)
                if self.state.is_terminal():
                    break

            if self.state.is_terminal():
                break

            while self.inbox:
                evt = self.inbox.pop(0)
                await self._handle_channel_event(evt)

            self.pending_tick = False
            if not self.state.is_terminal():
                decision = await self._evaluate_strategy()
                await self._apply_decision(decision)

                wait_hours = max(decision.next_eval_hours, 1.0)
                try:
                    await workflow.wait_condition(
                        lambda: bool(self.inbox) or bool(self.payment_inbox) or self.state.suspended,
                        timeout=timedelta(hours=wait_hours),
                    )
                except asyncio.TimeoutError:
                    self.pending_tick = True

        return {
            "customer_id": self.state.customer_id,
            "final_stage": self.state.stage.value,
            "actions_taken": len(self.state.actions_taken),
            "events_received": len(self.state.events_received),
        }

    # ── Signals ──────────────────────────────────────────────────────

    @workflow.signal
    def channel_event(self, evt: ChannelEventSignal) -> None:
        self.inbox.append(evt)
        self.state.events_received.append({
            "event_id": evt.event_id,
            "channel": evt.channel,
            "direction": evt.direction,
            "event_type": evt.event_type,
            "intent": evt.intent,
            "at": str(workflow.now()),
        })

    @workflow.signal
    def payment_received(self, pmt: PaymentSignal) -> None:
        self.payment_inbox.append(pmt)

    @workflow.signal
    def compliance_flag(self, flag: ComplianceFlagSignal) -> None:
        if flag.action == "activate":
            if flag.flag_type not in self.state.compliance_flags:
                self.state.compliance_flags.append(flag.flag_type)

            if flag.flag_type in ("BANKRUPTCY", "DECEASED", "IDENTITY_THEFT"):
                self.state.suspended = True
                self.state.suspension_reason = flag.flag_type
                self.state.previous_stage = self.state.stage
                self.state.stage = JourneyStage.SUSPENDED
                self.state.updated_at = str(workflow.now())

        elif flag.action == "deactivate":
            if flag.flag_type in self.state.compliance_flags:
                self.state.compliance_flags.remove(flag.flag_type)

            if self.state.suspended and self.state.suspension_reason == flag.flag_type:
                self.state.suspended = False
                self.state.suspension_reason = None
                if self.state.previous_stage:
                    self.state.stage = self.state.previous_stage

    @workflow.signal
    def strategy_updated(self, update: StrategyUpdateSignal) -> None:
        self.state.strategy_version = update.version
        self.pending_tick = True

    # ── Queries ──────────────────────────────────────────────────────

    @workflow.query
    def snapshot(self) -> dict:
        return {
            "customer_id": self.state.customer_id,
            "account_id": self.state.account_id,
            "stage": self.state.stage.value,
            "dpd": self.state.dpd,
            "balance": self.state.balance,
            "risk_score": self.state.risk_score,
            "compliance_flags": self.state.compliance_flags,
            "suspended": self.state.suspended,
            "suspension_reason": self.state.suspension_reason,
            "strategy_version": self.state.strategy_version,
            "segment": self.state.segment,
            "actions_count": len(self.state.actions_taken),
            "events_count": len(self.state.events_received),
            "active_ptp": self.state.active_ptp,
            "last_contact_at": self.state.last_contact_at,
            "last_action_at": self.state.last_action_at,
            "started_at": self.state.started_at,
            "updated_at": self.state.updated_at,
            "evaluation_count": self.state.evaluation_count,
        }

    @workflow.query
    def recent_events(self) -> list[dict]:
        return self.state.events_received[-20:]

    @workflow.query
    def actions_taken(self) -> list[dict]:
        return self.state.actions_taken[-20:]

    # ── Internal handlers ────────────────────────────────────────────

    async def _handle_channel_event(self, evt: ChannelEventSignal) -> None:
        self.state.last_contact_at = evt.occurred_at

        if evt.intent == "PTP":
            amount = evt.payload.get("amount", self.state.balance * 0.5)
            promised_date = evt.payload.get("promised_date", "")
            self.state.active_ptp = {
                "amount": amount,
                "promised_date": promised_date,
                "captured_at": str(workflow.now()),
                "channel": evt.channel,
                "status": "PENDING",
            }
            await self._transition(JourneyStage.PTP_ACTIVE, f"PTP captured: ${amount}", evt.channel)

        elif evt.intent == "HARDSHIP":
            await self._transition(JourneyStage.HARDSHIP_REVIEW, "customer indicated hardship", evt.channel)

        elif evt.intent == "DISPUTE":
            if "DISPUTE" not in self.state.compliance_flags:
                self.state.compliance_flags.append("DISPUTE")
            self.state.suspended = True
            self.state.suspension_reason = "DISPUTE"
            await self._transition(JourneyStage.SUSPENDED, "dispute filed", evt.channel)

        elif evt.intent == "SETTLEMENT_INQUIRY":
            await self._transition(
                JourneyStage.SETTLEMENT_NEGOTIATION,
                "customer inquired about settlement",
                evt.channel,
            )

    async def _handle_payment(self, pmt: PaymentSignal) -> None:
        self.state.balance = max(0, self.state.balance - pmt.amount)

        if self.state.active_ptp and self.state.stage == JourneyStage.PTP_ACTIVE:
            self.state.active_ptp["status"] = "KEPT"
            self.state.active_ptp = None

        if self.state.balance <= 0 or self.state.dpd <= 0:
            await self._transition(JourneyStage.CURED, f"payment received: ${pmt.amount}", "payment_processor")
        else:
            self.state.dpd = max(0, self.state.dpd - 30)

    async def _evaluate_strategy(self) -> StrategyDecision:
        info = AccountInfo(
            account_id=self.state.account_id,
            customer_id=self.state.customer_id,
            current_balance=self.state.balance,
            days_past_due=self.state.dpd,
            risk_score=self.state.risk_score,
            compliance_flags=self.state.compliance_flags,
        )

        decision: StrategyDecision = await workflow.execute_activity(
            strategy.evaluate_strategy,
            info,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=ACTIVITY_RETRY,
        )

        self.state.segment = decision.segment
        self.state.evaluation_count += 1
        self.state.updated_at = str(workflow.now())

        await workflow.execute_activity(
            dispatch.publish_decision,
            args=[decision, self.state.customer_id, workflow.info().workflow_id],
            start_to_close_timeout=timedelta(seconds=10),
        )

        return decision

    async def _apply_decision(self, decision: StrategyDecision) -> None:
        if not decision.compliance.get("can_contact", True):
            return

        treatment = decision.treatment
        if not treatment:
            return

        channels = decision.routing.get("recommended_channels", [])
        if not channels:
            return

        channel = channels[0] if channels else "sms"
        action = ActionToDispatch(
            action_type=treatment.get("action", "reminder"),
            channel=channel,
            payload={
                "treatment": treatment,
                "message_tone": treatment.get("message_tone", "neutral"),
                "template": treatment.get("details", {}).get("template", "generic"),
            },
            reason=f"strategy evaluation #{self.state.evaluation_count}",
        )

        comp_result = await workflow.execute_activity(
            compliance.check_compliance,
            args=[action, self.state.compliance_flags, 14, 0],
            start_to_close_timeout=timedelta(seconds=5),
        )

        if not comp_result.get("allowed", False):
            await workflow.execute_activity(
                dispatch.publish_compliance_event,
                args=[
                    self.state.customer_id,
                    workflow.info().workflow_id,
                    "action_gate",
                    False,
                    comp_result.get("reason", ""),
                    comp_result,
                    action.action_type,
                ],
                start_to_close_timeout=timedelta(seconds=5),
            )
            return

        result = await workflow.execute_activity(
            dispatch.dispatch_action,
            args=[action, self.state.customer_id, workflow.info().workflow_id],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=ACTIVITY_RETRY,
        )

        self.state.actions_taken.append({
            "action_type": action.action_type,
            "channel": action.channel,
            "at": str(workflow.now()),
            "event_id": result.get("event_id"),
        })
        self.state.last_action_at = str(workflow.now())

    async def _transition(self, to_stage: JourneyStage, reason: str, triggered_by: str) -> None:
        from_stage = self.state.stage
        self.state.previous_stage = from_stage
        self.state.stage = to_stage
        self.state.updated_at = str(workflow.now())

        await workflow.execute_activity(
            dispatch.publish_lifecycle,
            args=[
                self.state.customer_id,
                workflow.info().workflow_id,
                from_stage.value if from_stage else None,
                to_stage.value,
                reason,
                triggered_by,
            ],
            start_to_close_timeout=timedelta(seconds=5),
        )


import asyncio
