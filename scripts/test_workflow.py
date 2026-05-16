"""Quick smoke test: start a CustomerJourney workflow and query its state."""
from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client

from workflows.customer_journey import CustomerJourney
from workflows.types import ChannelEventSignal, PaymentSignal, ComplianceFlagSignal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    client = await Client.connect("localhost:7233")

    customer_id = "CUST-0001"
    workflow_id = f"journey-{customer_id}"

    logger.info("Starting workflow for %s...", customer_id)
    handle = await client.start_workflow(
        CustomerJourney.run,
        customer_id,
        id=workflow_id,
        task_queue="collections",
    )

    await asyncio.sleep(3)

    state = await handle.query(CustomerJourney.snapshot)
    logger.info("Journey state: stage=%s dpd=%s balance=%s flags=%s",
                state["stage"], state["dpd"], state["balance"], state["compliance_flags"])
    logger.info("Actions taken: %s, Events: %s", state["actions_count"], state["events_count"])

    logger.info("Sending inbound SMS with hardship intent...")
    await handle.signal(
        CustomerJourney.channel_event,
        ChannelEventSignal(
            event_id="test-evt-001",
            customer_id=customer_id,
            channel="sms",
            direction="inbound",
            event_type="message_received",
            intent="HARDSHIP",
            payload={"text": "I lost my job, can we work something out?"},
            occurred_at="2026-05-16T10:00:00",
        ),
    )

    await asyncio.sleep(2)

    state2 = await handle.query(CustomerJourney.snapshot)
    logger.info("After hardship signal: stage=%s", state2["stage"])

    events = await handle.query(CustomerJourney.recent_events)
    logger.info("Recent events: %s", events)

    actions = await handle.query(CustomerJourney.actions_taken)
    logger.info("Actions taken: %s", actions)

    logger.info("\nSending payment to cure...")
    await handle.signal(
        CustomerJourney.payment_received,
        PaymentSignal(
            amount=state2["balance"],
            payment_date="2026-05-16",
            account_id=state2["account_id"],
            method="ach",
        ),
    )

    await asyncio.sleep(2)

    state3 = await handle.query(CustomerJourney.snapshot)
    logger.info("After payment: stage=%s balance=%s", state3["stage"], state3["balance"])

    logger.info("\nSmoke test complete!")


if __name__ == "__main__":
    asyncio.run(main())
