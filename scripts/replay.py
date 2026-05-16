"""Event replay tool — re-publish events from the Postgres event store through Kafka.

Use for demo replays, debugging, or testing downstream consumers.

Run: uv run python -m scripts.replay [options]

Examples:
  python -m scripts.replay --customer CUST-0032          # Replay all events for a customer
  python -m scripts.replay --category interaction --limit 50  # Replay last 50 interactions
  python -m scripts.replay --since 2026-05-16T00:00:00   # Replay events since timestamp
  python -m scripts.replay --speed 2.0                    # 2x speed replay
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from services.shared.db import execute_query
from services.shared.kafka_client import KafkaProducer
from events.topics import Topics

logging.basicConfig(level=logging.WARNING)
console = Console()

CATEGORY_TOPIC_MAP = {
    "channel": Topics.CHANNEL_EVENTS_RAW,
    "interaction": Topics.INTERACTIONS_NORMALIZED,
    "decision": Topics.DECISIONS,
    "action": Topics.ACTIONS,
    "lifecycle": Topics.LIFECYCLE,
    "compliance": Topics.COMPLIANCE,
    "ai_reasoning": Topics.AI_REASONING,
    "ai_quality": Topics.AI_QUALITY,
}


async def fetch_events(
    customer_id: str = "",
    category: str = "",
    since: str = "",
    limit: int = 100,
) -> list[dict]:
    conditions = []
    params = {"limit": limit}

    if customer_id:
        conditions.append("customer_id = :cid")
        params["cid"] = customer_id
    if category:
        conditions.append("event_category = :cat")
        params["cat"] = category
    if since:
        conditions.append("occurred_at >= :since")
        params["since"] = since

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = await execute_query(f"""
        SELECT event_id, customer_id, account_id, workflow_id,
               channel, direction, event_type, event_category,
               intent, payload, source_service, occurred_at
        FROM customer_events
        {where}
        ORDER BY occurred_at ASC LIMIT :limit
    """, params)

    return rows


async def replay_events(
    events: list[dict],
    speed: float = 1.0,
    dry_run: bool = False,
):
    if not events:
        console.print("[yellow]No events to replay[/]")
        return

    console.print(f"\n[bold]Replaying {len(events)} events[/] (speed: {speed}x, dry_run: {dry_run})")
    console.print()

    producer = None
    if not dry_run:
        producer = KafkaProducer()
        await producer.start()

    try:
        prev_time = None

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Replaying...", total=len(events))

            for i, event in enumerate(events):
                occurred = event.get("occurred_at", "")
                if prev_time and occurred and speed > 0:
                    try:
                        from datetime import datetime
                        if isinstance(occurred, str):
                            curr = datetime.fromisoformat(occurred)
                        else:
                            curr = occurred
                        if isinstance(prev_time, str):
                            prev = datetime.fromisoformat(prev_time)
                        else:
                            prev = prev_time
                        delay = (curr - prev).total_seconds() / speed
                        if 0 < delay < 10:
                            await asyncio.sleep(delay)
                    except (ValueError, TypeError):
                        pass

                category = event.get("event_category", "interaction")
                topic = CATEGORY_TOPIC_MAP.get(category, Topics.INTERACTIONS_NORMALIZED)
                customer_id = event.get("customer_id", "")

                payload = event.get("payload", {})
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        payload = {}

                kafka_event = {
                    "event_id": str(event.get("event_id", "")),
                    "customer_id": customer_id,
                    "account_id": event.get("account_id"),
                    "workflow_id": event.get("workflow_id"),
                    "channel": event.get("channel"),
                    "direction": event.get("direction"),
                    "event_type": event.get("event_type", ""),
                    "intent": event.get("intent"),
                    "payload": payload,
                    "source_service": f"replay:{event.get('source_service', '')}",
                    "occurred_at": str(occurred),
                }

                if dry_run:
                    if i < 5 or i == len(events) - 1:
                        console.print(f"  [dim]{i+1}.[/] [{category}] {event.get('event_type', '')} → {customer_id}")
                else:
                    key = customer_id.encode() if customer_id else None
                    import orjson
                    await producer.send(topic, orjson.dumps(kafka_event), key=key)

                prev_time = occurred
                progress.update(task, advance=1, description=f"[{category}] {event.get('event_type', '')[:30]}")

        console.print(f"\n[bold green]Replay complete:[/] {len(events)} events published")

    finally:
        if producer:
            await producer.stop()


async def main():
    parser = argparse.ArgumentParser(description="Replay events from the event store through Kafka")
    parser.add_argument("--customer", default="", help="Filter by customer_id")
    parser.add_argument("--category", default="", help="Filter by event_category")
    parser.add_argument("--since", default="", help="Replay events since timestamp (ISO format)")
    parser.add_argument("--limit", type=int, default=100, help="Max events to replay")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier (0=instant)")
    parser.add_argument("--dry-run", action="store_true", help="Print events without publishing")
    parser.add_argument("--list", action="store_true", help="Just list events, don't replay")

    args = parser.parse_args()

    console.print("[bold]Collections Event Replay Tool[/]")

    events = await fetch_events(
        customer_id=args.customer,
        category=args.category,
        since=args.since,
        limit=args.limit,
    )

    if args.list:
        console.print(f"\n[bold]{len(events)} events found:[/]\n")
        for e in events[:50]:
            console.print(f"  {e.get('occurred_at', '')} [{e.get('event_category', '')}] "
                          f"{e.get('event_type', '')} → {e.get('customer_id', '')}")
        if len(events) > 50:
            console.print(f"  ... and {len(events) - 50} more")
        return

    await replay_events(events, speed=args.speed, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
