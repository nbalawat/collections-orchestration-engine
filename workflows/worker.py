"""Temporal worker — registers workflows and activities, then polls for tasks."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env early so activities that call Anthropic see ANTHROPIC_API_KEY.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from temporalio.client import Client
from temporalio.worker import Worker

from workflows.customer_journey import CustomerJourney
from workflows.activities.account import lookup_account
from workflows.activities.history import compute_contact_stats
from workflows.activities.ai_invoke import invoke_digital_channel_agent, invoke_quality_compliance_review
from workflows.activities.validation import ensure_validation_notice_scheduled, dispatch_validation_notice
from workflows.activities.strategy import evaluate_strategy
from workflows.activities.compliance import check_compliance
from workflows.activities.dispatch import (
    dispatch_action,
    publish_decision,
    publish_lifecycle,
    publish_compliance_event,
    publish_ai_reasoning,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TEMPORAL_HOST = "localhost:7233"
TASK_QUEUE = "collections"


async def main():
    client = await Client.connect(TEMPORAL_HOST)
    logger.info("Connected to Temporal at %s", TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CustomerJourney],
        activities=[
            lookup_account,
            compute_contact_stats,
            evaluate_strategy,
            check_compliance,
            dispatch_action,
            publish_decision,
            publish_lifecycle,
            publish_compliance_event,
            publish_ai_reasoning,
            invoke_digital_channel_agent,
            invoke_quality_compliance_review,
            ensure_validation_notice_scheduled,
            dispatch_validation_notice,
        ],
    )

    logger.info("Starting worker on queue '%s'...", TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
