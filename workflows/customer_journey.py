"""CustomerJourney — the main per-customer Temporal workflow.

One instance per delinquent account. Starts when an account goes past due,
ends on cure, settlement completion, or charge-off. Reacts to channel events,
payments, compliance signals, and strategy updates.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

# Disable auto-fired agent calls when running on a rate-limited Claude Code OAuth
# token. Manual invocations from the UI + narrative + digest still work.
_AUTO_INVOKE = os.environ.get("AI_AUTO_INVOKE_ENABLED", "true").lower() in ("1", "true", "yes", "on")

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from workflows.types import (
        AccountInfo,
        ActionToDispatch,
        AIAgentResult,
        ChannelEventSignal,
        ComplianceFlagSignal,
        ContactStats,
        JourneyStage,
        JourneyState,
        PaymentSignal,
        StrategyDecision,
        StrategyUpdateSignal,
    )
    from workflows.activities import account, strategy, compliance, dispatch, history, ai_invoke, validation


ACTIVITY_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=1))


@workflow.defn
class CustomerJourney:

    def __init__(self) -> None:
        self.state = JourneyState()
        self.inbox: list[ChannelEventSignal] = []
        self.payment_inbox: list[PaymentSignal] = []
        self.pending_tick = False
        self._latest_stats: ContactStats | None = None
        self._current_trace_id: str | None = None
        self._validation_notice_id: str | None = None
        self._validation_notice_sent: bool = False

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
                # PTP lifecycle check before any other action
                await self._check_ptp_status()
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
        # Inbound event seeds the trace; subsequent decisions/actions reuse it.
        if evt.correlation_id:
            self._current_trace_id = evt.correlation_id

        # If an inbound customer message has an actionable intent, auto-invoke
        # the digital channel agent. The agent persists its decision to
        # agent_actions and emits a reasoning trace.
        if (
            _AUTO_INVOKE
            and evt.direction == "inbound"
            and evt.intent in {"HARDSHIP", "DISPUTE", "DISTRESS", "PTP",
                               "SETTLEMENT_INQUIRY", "REFUSAL_TO_PAY", "COMPLAINT"}
        ):
            message_text = ""
            if isinstance(evt.payload, dict):
                message_text = str(evt.payload.get("text") or evt.payload.get("transcript") or "")
            try:
                await workflow.execute_activity(
                    ai_invoke.invoke_digital_channel_agent,
                    args=[
                        self.state.customer_id,
                        workflow.info().workflow_id,
                        message_text,
                        evt.channel,
                        evt.intent,
                    ],
                    start_to_close_timeout=timedelta(seconds=90),
                    retry_policy=ACTIVITY_RETRY,
                )
            except Exception:
                pass  # AI failure shouldn't block the rest of the workflow

        # Auto-trigger quality/compliance review on completed voice calls.
        if _AUTO_INVOKE and evt.channel == "voice" and evt.event_type in ("call_connected_rpc", "call_completed"):
            transcript = ""
            if isinstance(evt.payload, dict):
                transcript = str(evt.payload.get("transcript") or evt.payload.get("text") or "")
            try:
                await workflow.execute_activity(
                    ai_invoke.invoke_quality_compliance_review,
                    args=[
                        self.state.customer_id,
                        workflow.info().workflow_id,
                        evt.event_id or str(workflow.now()),
                        evt.channel,
                        transcript,
                    ],
                    start_to_close_timeout=timedelta(seconds=120),
                    retry_policy=ACTIVITY_RETRY,
                )
            except Exception:
                pass  # QC failure shouldn't block; we'll see it in metrics

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

    async def _check_ptp_status(self) -> None:
        """PTP lifecycle check, called each main-loop tick.

        - If active PTP is past promised_date+1 with no payment received,
          mark it BROKEN and transition the workflow.
        - If active PTP is 1 day from due and no payment yet, schedule a
          courtesy reminder on the next decision pass.
        """
        ptp = self.state.active_ptp
        if not ptp or self.state.stage != JourneyStage.PTP_ACTIVE:
            return
        promised = ptp.get("promised_date") or ""
        if not promised:
            return
        try:
            promised_dt = datetime.fromisoformat(promised)
        except ValueError:
            return
        now = workflow.now()
        if now.date() > promised_dt.date() + timedelta(days=1):
            ptp["status"] = "BROKEN"
            self.state.active_ptp = None
            await self._transition(
                JourneyStage.PTP_BROKEN,
                f"PTP broken: promised ${ptp.get('amount')} by {promised}, no payment",
                "ptp_monitor",
            )
        elif now.date() == promised_dt.date() - timedelta(days=1):
            ptp["reminder_pending"] = True

    async def _handle_payment(self, pmt: PaymentSignal) -> None:
        self.state.balance = max(0, self.state.balance - pmt.amount)

        if self.state.active_ptp and self.state.stage == JourneyStage.PTP_ACTIVE:
            self.state.active_ptp["status"] = "KEPT"
            self.state.active_ptp = None

        # Re-read DPD from the ledger rather than guessing — the payment processor
        # owns delinquency status; we just reflect it.
        try:
            refreshed: AccountInfo = await workflow.execute_activity(
                account.lookup_account,
                self.state.customer_id,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=ACTIVITY_RETRY,
            )
            self.state.dpd = refreshed.days_past_due
            self.state.balance = refreshed.current_balance
        except Exception:
            pass

        if self.state.balance <= 0 or self.state.dpd <= 0:
            await self._transition(JourneyStage.CURED, f"payment received: ${pmt.amount}", "payment_processor")

    async def _evaluate_strategy(self) -> StrategyDecision:
        info = AccountInfo(
            account_id=self.state.account_id,
            customer_id=self.state.customer_id,
            current_balance=self.state.balance,
            days_past_due=self.state.dpd,
            risk_score=self.state.risk_score,
            compliance_flags=self.state.compliance_flags,
        )

        stats: ContactStats = await workflow.execute_activity(
            history.compute_contact_stats,
            self.state.customer_id,
            start_to_close_timeout=timedelta(seconds=8),
            retry_policy=ACTIVITY_RETRY,
        )

        decision: StrategyDecision = await workflow.execute_activity(
            strategy.evaluate_strategy,
            args=[info, stats],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=ACTIVITY_RETRY,
        )
        self._latest_stats = stats

        self.state.segment = decision.segment
        self.state.evaluation_count += 1
        self.state.updated_at = str(workflow.now())

        await workflow.execute_activity(
            dispatch.publish_decision,
            args=[decision, self.state.customer_id, workflow.info().workflow_id, self._current_trace_id],
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

        s = self._latest_stats
        local_hour = s.customer_local_hour if s else 14
        voice_7d = s.voice_attempts_7d if s else 0
        channel_7d = s.channel_attempts_7d if s else {}
        total_7d = s.total_attempts_7d if s else 0
        comp_result = await workflow.execute_activity(
            compliance.check_compliance,
            args=[action, self.state.compliance_flags, local_hour, voice_7d, channel_7d, total_7d],
            start_to_close_timeout=timedelta(seconds=5),
        )

        # Emit every compliance evaluation — pass AND fail — so we have full audit
        # of action gating. Auditors require an affirmative record per attempt.
        await workflow.execute_activity(
            dispatch.publish_compliance_event,
            args=[
                self.state.customer_id,
                workflow.info().workflow_id,
                "action_gate",
                bool(comp_result.get("allowed", False)),
                comp_result.get("reason", ""),
                comp_result,
                None if comp_result.get("allowed") else action.action_type,
                self._current_trace_id,
            ],
            start_to_close_timeout=timedelta(seconds=5),
        )

        if not comp_result.get("allowed", False):
            return

        # Reg F §1006.34: ensure validation notice is scheduled on first outbound
        # action and dispatch it if we're approaching the 5-day deadline.
        if not self._validation_notice_sent:
            try:
                notice = await workflow.execute_activity(
                    validation.ensure_validation_notice_scheduled,
                    args=[
                        self.state.customer_id,
                        workflow.info().workflow_id,
                        self.state.account_id,
                        str(workflow.now()),
                        action.channel,
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                self._validation_notice_id = notice["notice_id"]
                if notice["status"] == "sent":
                    self._validation_notice_sent = True
                else:
                    # Dispatch immediately on first outbound — defensible posture.
                    await workflow.execute_activity(
                        validation.dispatch_validation_notice,
                        args=[
                            self.state.customer_id,
                            workflow.info().workflow_id,
                            notice["notice_id"],
                            "email",
                            self._current_trace_id,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=ACTIVITY_RETRY,
                    )
                    self._validation_notice_sent = True
            except Exception:
                pass  # don't let validation hiccup block the rest of the workflow

        result = await workflow.execute_activity(
            dispatch.dispatch_action,
            args=[action, self.state.customer_id, workflow.info().workflow_id, self._current_trace_id],
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
                self._current_trace_id,
            ],
            start_to_close_timeout=timedelta(seconds=5),
        )


import asyncio
