"""Pre-scripted demo scenarios that drive realistic collections journeys."""
from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client

from events.models import Direction, Intent
from services.channel_simulators.simulator import ChannelSimulator
from workflows.customer_journey import CustomerJourney
from workflows.types import ComplianceFlagSignal, PaymentSignal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class ScenarioRunner:
    def __init__(self):
        self.sim = ChannelSimulator()
        self.temporal: Client | None = None

    async def start(self):
        await self.sim.start()
        self.temporal = await Client.connect("localhost:7233")
        logger.info("Scenario runner ready")

    async def stop(self):
        await self.sim.stop()

    async def _ensure_workflow(self, customer_id: str) -> str:
        workflow_id = f"journey-{customer_id}"
        try:
            handle = self.temporal.get_workflow_handle(workflow_id)
            await handle.query(CustomerJourney.snapshot)
        except Exception:
            await self.temporal.start_workflow(
                CustomerJourney.run,
                customer_id,
                id=workflow_id,
                task_queue="collections",
            )
            await asyncio.sleep(2)
        return workflow_id

    async def _query(self, customer_id: str) -> dict:
        handle = self.temporal.get_workflow_handle(f"journey-{customer_id}")
        return await handle.query(CustomerJourney.snapshot)

    # ── Scenario 1: Cross-Channel Journey ────────────────────────────

    async def scenario_cross_channel(self, customer_id: str = "CUST-0032"):
        """Jane Doe: 45 DPD → SMS dunning → hardship reply → email → bounce → voice → resolution"""
        logger.info("=== SCENARIO 1: Cross-Channel Journey [%s] ===", customer_id)
        wf_id = await self._ensure_workflow(customer_id)
        handle = self.temporal.get_workflow_handle(wf_id)

        # Step 1: Outbound SMS dunning
        logger.info("Step 1: Outbound SMS dunning notice...")
        await self.sim.simulate_sms_outbound(customer_id, template="dunning_notice")
        await asyncio.sleep(2)

        # Step 2: Customer replies with hardship
        logger.info("Step 2: Customer replies indicating hardship...")
        await self.sim.simulate_sms_inbound(customer_id, intent=Intent.HARDSHIP)
        await asyncio.sleep(3)

        state = await self._query(customer_id)
        logger.info("  → Stage: %s", state["stage"])

        # Step 3: Email with hardship options
        logger.info("Step 3: Outbound email with payment plan options...")
        await self.sim.simulate_email_event(customer_id, "delivered")
        await asyncio.sleep(1)

        # Step 4: Email bounces
        logger.info("Step 4: Email bounces...")
        await self.sim.simulate_email_event(customer_id, "bounced")
        await asyncio.sleep(2)

        # Step 5: Voice outbound → connected
        logger.info("Step 5: Outbound voice call — connected...")
        await self.sim.simulate_voice_call(
            customer_id,
            direction=Direction.OUTBOUND,
            outcome="connected_rpc",
            intent=Intent.HARDSHIP,
            duration_seconds=320,
        )
        await asyncio.sleep(2)

        # Step 6: Agent applies arrangement
        logger.info("Step 6: Agent applies 6-month payment arrangement...")
        state = await self._query(customer_id)
        logger.info("  → Final stage: %s, Actions: %d, Events: %d",
                     state["stage"], state["actions_count"], state["events_count"])

        return state

    # ── Scenario 2: Bankruptcy Suppression ───────────────────────────

    async def scenario_bankruptcy(self, customer_id: str = "CUST-0095"):
        """Robert Chen: mid-journey → bankruptcy filed → all actions suppressed → dismissed → resumes"""
        logger.info("=== SCENARIO 2: Bankruptcy Suppression [%s] ===", customer_id)
        wf_id = await self._ensure_workflow(customer_id)
        handle = self.temporal.get_workflow_handle(wf_id)

        await asyncio.sleep(2)
        state = await self._query(customer_id)
        logger.info("  Pre-bankruptcy stage: %s", state["stage"])

        # File bankruptcy
        logger.info("Step 1: Bankruptcy filing notification...")
        await handle.signal(
            CustomerJourney.compliance_flag,
            ComplianceFlagSignal(flag_type="BANKRUPTCY", reason="Chapter 7 filing", action="activate"),
        )
        await asyncio.sleep(2)

        state = await self._query(customer_id)
        logger.info("  → Stage: %s, Suspended: %s, Flags: %s",
                     state["stage"], state["suspended"], state["compliance_flags"])

        # Try to send SMS — should be blocked
        logger.info("Step 2: Attempting SMS outbound (should be suppressed)...")
        await self.sim.simulate_sms_outbound(customer_id, template="settlement_offer")
        await asyncio.sleep(2)

        # Dismiss bankruptcy
        logger.info("Step 3: Bankruptcy dismissed...")
        await handle.signal(
            CustomerJourney.compliance_flag,
            ComplianceFlagSignal(flag_type="BANKRUPTCY", reason="Case dismissed", action="deactivate"),
        )
        await asyncio.sleep(2)

        state = await self._query(customer_id)
        logger.info("  → Resumed: stage=%s, suspended=%s", state["stage"], state["suspended"])

        return state

    # ── Scenario 3: PTP Lifecycle ────────────────────────────────────

    async def scenario_ptp(self, customer_id: str = "CUST-0055"):
        """Maria Garcia: voice call → PTP → timer → payment arrives → cure"""
        logger.info("=== SCENARIO 3: PTP Lifecycle [%s] ===", customer_id)
        wf_id = await self._ensure_workflow(customer_id)
        handle = self.temporal.get_workflow_handle(wf_id)

        await asyncio.sleep(2)

        # Voice call with PTP
        logger.info("Step 1: Outbound call — customer promises to pay...")
        await self.sim.simulate_voice_call(
            customer_id,
            direction=Direction.OUTBOUND,
            outcome="connected_rpc",
            intent=Intent.PTP,
            duration_seconds=180,
        )

        # Signal PTP via SMS
        await self.sim.simulate_sms_inbound(
            customer_id,
            intent=Intent.PTP,
            payload_override={"amount": 4100, "promised_date": "2026-05-20"},
        )
        await asyncio.sleep(3)

        state = await self._query(customer_id)
        logger.info("  → Stage: %s, Active PTP: %s", state["stage"], state["active_ptp"])

        # Payment arrives
        logger.info("Step 2: Payment arrives...")
        await handle.signal(
            CustomerJourney.payment_received,
            PaymentSignal(amount=4100, payment_date="2026-05-20", account_id=state["account_id"], method="ach"),
        )
        await asyncio.sleep(2)

        state = await self._query(customer_id)
        logger.info("  → After payment: stage=%s, balance=%s", state["stage"], state["balance"])

        return state

    # ── Scenario 4: Strategy Hot-Swap ────────────────────────────────

    async def scenario_strategy_swap(self, customer_ids: list[str] | None = None):
        """Multiple customers running → strategy version changes → journeys pick up new rules"""
        cids = customer_ids or ["CUST-0040", "CUST-0041", "CUST-0042"]
        logger.info("=== SCENARIO 4: Strategy Hot-Swap [%s] ===", cids)

        for cid in cids:
            await self._ensure_workflow(cid)

        await asyncio.sleep(3)

        # Show current states
        for cid in cids:
            state = await self._query(cid)
            logger.info("  %s: stage=%s strategy=%s", cid, state["stage"], state["strategy_version"])

        return {"customers": cids, "status": "strategy_swap_ready"}

    # ── Scenario 5: Complex Case (AI Reasoning) ────────────────────

    async def scenario_complex_case(self, customer_id: str = "CUST-0120"):
        """David Park: conflicting signals → AI reasoning agent → specialist review"""
        logger.info("=== SCENARIO 5: Complex Case [%s] ===", customer_id)
        wf_id = await self._ensure_workflow(customer_id)
        handle = self.temporal.get_workflow_handle(wf_id)

        await asyncio.sleep(2)
        state = await self._query(customer_id)
        logger.info("  Customer profile: dpd=%s, balance=%s, segment=%s",
                     state["dpd"], state["balance"], state.get("segment", {}))

        # Inbound call with mixed signals
        logger.info("Step 1: Inbound call — customer mentions new job + can't pay full amount...")
        await self.sim.simulate_voice_call(
            customer_id,
            direction=Direction.INBOUND,
            outcome="connected_rpc",
            intent=Intent.SETTLEMENT_INQUIRY,
            duration_seconds=420,
        )
        await asyncio.sleep(3)

        state = await self._query(customer_id)
        logger.info("  → Stage: %s", state["stage"])

        return state

    # ── Scenario 6: Portfolio Operations ─────────────────────────────

    async def scenario_portfolio(self, count: int = 20):
        """Spin up many customer journeys to show portfolio-level operations"""
        logger.info("=== SCENARIO 6: Portfolio Operations (%d customers) ===", count)

        started = []
        for i in range(1, count + 1):
            cid = f"CUST-{i:04d}"
            try:
                await self._ensure_workflow(cid)
                started.append(cid)
            except Exception as e:
                logger.warning("Failed to start %s: %s", cid, e)

        await asyncio.sleep(5)

        logger.info("  Started %d workflows", len(started))

        # Generate random activity across the portfolio
        for _ in range(count * 2):
            cid = f"CUST-{random.randint(1, count):04d}"
            channel_choice = random.choice(["sms", "email", "voice", "dialer"])

            if channel_choice == "sms":
                intent = random.choice(list(Intent))
                await self.sim.simulate_sms_inbound(cid, intent=intent)
            elif channel_choice == "email":
                event_type = random.choice(["delivered", "opened", "bounced"])
                await self.sim.simulate_email_event(cid, event_type)
            elif channel_choice == "voice":
                await self.sim.simulate_voice_call(cid, direction=Direction.OUTBOUND)
            else:
                await self.sim.simulate_dialer_campaign(cid)

            await asyncio.sleep(0.3)

        logger.info("  Generated %d random events across portfolio", count * 2)
        return {"started": len(started), "events_generated": count * 2}


import random


async def run_all_scenarios():
    runner = ScenarioRunner()
    await runner.start()

    try:
        await runner.scenario_cross_channel()
        await asyncio.sleep(2)
        await runner.scenario_bankruptcy()
        await asyncio.sleep(2)
        await runner.scenario_ptp()
        await asyncio.sleep(2)
        await runner.scenario_strategy_swap()
        await asyncio.sleep(2)
        await runner.scenario_complex_case()
        await asyncio.sleep(2)
        await runner.scenario_portfolio(count=20)

        logger.info("\n=== ALL SCENARIOS COMPLETE ===")
    finally:
        await runner.stop()


if __name__ == "__main__":
    asyncio.run(run_all_scenarios())
