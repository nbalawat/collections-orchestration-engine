"""Signal Bridge — routes Kafka events to Temporal workflows.

Consumes from interactions.normalized, resolves the target workflow by customer_id,
and signals it. Starts a new workflow if one doesn't exist.
"""
from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.service import RPCError

import time

from events.topics import Topics
from services.shared.config import get_settings
from services.shared.heartbeat import HeartbeatEmitter
from services.shared.kafka_client import KafkaConsumer
from workflows.customer_journey import CustomerJourney
from workflows.types import ChannelEventSignal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class SignalBridge:
    def __init__(self):
        self.temporal: Client | None = None
        self.consumer: KafkaConsumer | None = None
        self.heartbeat = HeartbeatEmitter("signal-bridge")

    async def start(self):
        self.temporal = await Client.connect(get_settings().temporal_host)
        logger.info("Connected to Temporal")
        await self.heartbeat.start()

        self.consumer = KafkaConsumer(
            topics=[Topics.INTERACTIONS_NORMALIZED],
            group_id="signal-bridge",
        )
        await self.consumer.start()
        logger.info("Consuming from %s", Topics.INTERACTIONS_NORMALIZED)

        await self.consumer.consume(self._handle)

    async def _handle(self, topic: str, key: bytes | None, value: dict):
        start = time.monotonic()
        customer_id = value.get("customer_id")
        if not customer_id:
            logger.warning("Event missing customer_id, skipping")
            return

        workflow_id = f"journey-{customer_id}"

        signal = ChannelEventSignal(
            event_id=value.get("event_id", ""),
            customer_id=customer_id,
            account_id=value.get("account_id"),
            channel=value.get("channel", ""),
            direction=value.get("direction", ""),
            event_type=value.get("event_type", ""),
            intent=value.get("intent"),
            payload=value.get("payload", {}),
            occurred_at=value.get("occurred_at", ""),
            correlation_id=value.get("correlation_id"),
        )

        try:
            handle = self.temporal.get_workflow_handle(workflow_id)
            await handle.signal(CustomerJourney.channel_event, signal)
            logger.info("Signaled workflow %s: %s/%s", workflow_id, signal.channel, signal.event_type)
        except RPCError:
            handle = await self.temporal.start_workflow(
                CustomerJourney.run,
                customer_id,
                id=workflow_id,
                task_queue="collections",
            )
            await asyncio.sleep(0.5)
            await handle.signal(CustomerJourney.channel_event, signal)
            logger.info("Started new workflow %s and signaled: %s/%s", workflow_id, signal.channel, signal.event_type)
        except Exception:
            self.heartbeat.record_error()
            raise
        finally:
            self.heartbeat.record_event(latency_ms=int((time.monotonic() - start) * 1000))

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
        await self.heartbeat.stop()


async def main():
    bridge = SignalBridge()
    try:
        await bridge.start()
    except KeyboardInterrupt:
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
