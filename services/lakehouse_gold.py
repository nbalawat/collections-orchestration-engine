"""Gold marts — business-facing aggregates built from silver via DuckDB.

Reads silver Parquet, produces curated marts that downstream BI / ML / dashboards
consume:

  gold/customer_360/               per-customer rollup
  gold/portfolio_daily/            daily portfolio KPIs
  gold/strategy_performance/       champion vs challenger over time
  gold/compliance_audit_daily/     daily compliance enforcement summary
  gold/_manifest/last_run.json     timestamp of last successful build

Runs on a schedule (default every 5 min). Each mart is a single, rewriteable
Parquet — gold is "current snapshot" not append-only.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

import aioboto3
import duckdb
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from services.shared.config import get_settings
from services.shared.heartbeat import HeartbeatEmitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GOLD_INTERVAL_S = int(os.environ.get("LAKEHOUSE_GOLD_INTERVAL_S", "300"))


MART_DEFINITIONS = {
    "customer_360": """
        WITH
        decisions AS (
            SELECT customer_id,
                   COUNT(*) AS strategy_evaluations,
                   MAX(strategy_version) AS latest_strategy_version,
                   MAX(occurred_at) AS last_decision_at
            FROM read_parquet('s3://{silver}/topic=events.decisions/date=*/part-*.parquet')
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        ),
        actions AS (
            SELECT customer_id,
                   COUNT(*) AS actions_dispatched,
                   MAX(occurred_at) AS last_action_at
            FROM read_parquet('s3://{silver}/topic=events.actions/date=*/part-*.parquet')
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        ),
        compliance AS (
            SELECT customer_id,
                   COUNT(*) AS compliance_evaluations,
                   COUNT(*) FILTER (WHERE JSON_EXTRACT_STRING(payload_json,'$.passed')='true') AS allowed,
                   COUNT(*) FILTER (WHERE JSON_EXTRACT_STRING(payload_json,'$.passed')='false') AS blocked
            FROM read_parquet('s3://{silver}/topic=events.compliance/date=*/part-*.parquet')
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        ),
        interactions AS (
            SELECT customer_id,
                   COUNT(*) AS interactions,
                   COUNT(*) FILTER (WHERE direction='inbound') AS inbound,
                   COUNT(*) FILTER (WHERE direction='outbound') AS outbound,
                   COUNT(DISTINCT channel) AS distinct_channels,
                   MAX(occurred_at) AS last_interaction_at
            FROM read_parquet('s3://{silver}/topic=interactions.normalized/date=*/part-*.parquet')
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        ),
        lifecycle AS (
            SELECT customer_id,
                   COUNT(*) AS stage_transitions,
                   MAX(occurred_at) AS last_transition_at
            FROM read_parquet('s3://{silver}/topic=events.lifecycle/date=*/part-*.parquet')
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        )
        SELECT
            COALESCE(d.customer_id, a.customer_id, c.customer_id, i.customer_id, l.customer_id) AS customer_id,
            COALESCE(i.interactions, 0) AS interactions,
            COALESCE(i.inbound, 0) AS inbound,
            COALESCE(i.outbound, 0) AS outbound,
            COALESCE(i.distinct_channels, 0) AS distinct_channels,
            COALESCE(d.strategy_evaluations, 0) AS strategy_evaluations,
            d.latest_strategy_version AS latest_strategy_version,
            COALESCE(a.actions_dispatched, 0) AS actions_dispatched,
            COALESCE(c.compliance_evaluations, 0) AS compliance_evaluations,
            COALESCE(c.allowed, 0) AS compliance_allowed,
            COALESCE(c.blocked, 0) AS compliance_blocked,
            COALESCE(l.stage_transitions, 0) AS stage_transitions,
            GREATEST(i.last_interaction_at, d.last_decision_at, a.last_action_at, l.last_transition_at) AS last_activity_at
        FROM decisions d
        FULL OUTER JOIN actions a ON a.customer_id = d.customer_id
        FULL OUTER JOIN compliance c ON c.customer_id = COALESCE(d.customer_id, a.customer_id)
        FULL OUTER JOIN interactions i ON i.customer_id = COALESCE(d.customer_id, a.customer_id, c.customer_id)
        FULL OUTER JOIN lifecycle l ON l.customer_id = COALESCE(d.customer_id, a.customer_id, c.customer_id, i.customer_id)
    """,

    "portfolio_daily": """
        SELECT
            DATE_TRUNC('day', occurred_at) AS day,
            COUNT(*) FILTER (WHERE topic='events.decisions') AS strategy_evaluations,
            COUNT(*) FILTER (WHERE topic='events.actions') AS actions_dispatched,
            COUNT(*) FILTER (WHERE topic='events.compliance') AS compliance_evaluations,
            COUNT(*) FILTER (WHERE topic='events.compliance' AND JSON_EXTRACT_STRING(payload_json,'$.passed')='false') AS compliance_blocked,
            COUNT(*) FILTER (WHERE topic='events.lifecycle') AS stage_transitions,
            COUNT(*) FILTER (WHERE topic='interactions.normalized') AS interactions,
            COUNT(*) FILTER (WHERE topic='interactions.normalized' AND direction='inbound') AS inbound_interactions,
            COUNT(*) FILTER (WHERE topic='interactions.normalized' AND direction='outbound') AS outbound_interactions,
            COUNT(DISTINCT customer_id) AS active_customers
        FROM (
            SELECT * FROM read_parquet('s3://{silver}/topic=*/date=*/part-*.parquet')
        )
        WHERE occurred_at IS NOT NULL
        GROUP BY day
        ORDER BY day DESC
    """,

    "strategy_performance": """
        WITH per_version AS (
            SELECT strategy_version,
                   COUNT(*) AS evaluations,
                   COUNT(DISTINCT customer_id) AS unique_customers,
                   COUNT(DISTINCT DATE_TRUNC('day', occurred_at)) AS active_days,
                   MIN(occurred_at) AS first_seen,
                   MAX(occurred_at) AS last_seen
            FROM read_parquet('s3://{silver}/topic=events.decisions/date=*/part-*.parquet')
            WHERE strategy_version IS NOT NULL
            GROUP BY strategy_version
        ),
        actions_per_version AS (
            SELECT d.strategy_version,
                   COUNT(a.event_id) AS actions_dispatched
            FROM read_parquet('s3://{silver}/topic=events.actions/date=*/part-*.parquet') a
            JOIN read_parquet('s3://{silver}/topic=events.decisions/date=*/part-*.parquet') d
              ON a.customer_id = d.customer_id
             AND a.occurred_at >= d.occurred_at
             AND a.occurred_at < d.occurred_at + INTERVAL 1 HOUR
            GROUP BY d.strategy_version
        )
        SELECT pv.strategy_version,
               pv.evaluations,
               pv.unique_customers,
               pv.active_days,
               COALESCE(av.actions_dispatched, 0) AS actions_dispatched,
               pv.first_seen, pv.last_seen
        FROM per_version pv
        LEFT JOIN actions_per_version av ON av.strategy_version = pv.strategy_version
        ORDER BY pv.evaluations DESC
    """,

    "compliance_audit_daily": """
        SELECT
            DATE_TRUNC('day', occurred_at) AS day,
            JSON_EXTRACT_STRING(payload_json,'$.check_type') AS check_type,
            JSON_EXTRACT_STRING(payload_json,'$.rule_name') AS rule_name,
            COUNT(*) FILTER (WHERE JSON_EXTRACT_STRING(payload_json,'$.passed')='true') AS allowed,
            COUNT(*) FILTER (WHERE JSON_EXTRACT_STRING(payload_json,'$.passed')='false') AS blocked,
            COUNT(*) AS total
        FROM read_parquet('s3://{silver}/topic=events.compliance/date=*/part-*.parquet')
        GROUP BY day, check_type, rule_name
        ORDER BY day DESC, total DESC
    """,
}


class GoldBuilder:
    def __init__(self):
        self.settings = get_settings()
        self.silver = self.settings.lakehouse_silver_bucket
        self.gold = self.settings.lakehouse_gold_bucket
        self.region = self.settings.lakehouse_s3_region
        if not (self.silver and self.gold):
            raise RuntimeError("LAKEHOUSE_SILVER_BUCKET and LAKEHOUSE_GOLD_BUCKET must be configured")
        self.session = aioboto3.Session()
        self.heartbeat = HeartbeatEmitter("lakehouse-gold", extra={
            "silver": self.silver, "gold": self.gold, "interval_s": GOLD_INTERVAL_S,
            "marts": list(MART_DEFINITIONS.keys()),
        })
        self._stop = asyncio.Event()
        self._builds = 0

    def _new_con(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(f"SET s3_region='{self.region}';")
        con.execute("CREATE SECRET IF NOT EXISTS aws_creds (TYPE s3, PROVIDER credential_chain);")
        return con

    async def start(self):
        await self.heartbeat.start()
        logger.info(
            "GoldBuilder started — silver=s3://%s gold=s3://%s region=%s interval=%ds marts=%s",
            self.silver, self.gold, self.region, GOLD_INTERVAL_S, list(MART_DEFINITIONS.keys()),
        )
        try:
            await self._build_once()
        except Exception:
            logger.exception("Initial gold build failed")
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=GOLD_INTERVAL_S)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            try:
                await self._build_once()
            except Exception:
                logger.exception("Gold build failed")

    async def stop(self):
        self._stop.set()
        await self.heartbeat.stop()

    async def _build_once(self):
        async with self.session.client("s3", region_name=self.region) as s3:
            con = self._new_con()
            try:
                for mart_name, sql_template in MART_DEFINITIONS.items():
                    sql = sql_template.format(silver=self.silver)
                    try:
                        table = con.execute(sql).fetch_arrow_table()
                    except Exception:
                        logger.exception("Mart query failed for %s; skipping", mart_name)
                        continue

                    buf = io.BytesIO()
                    import pyarrow.parquet as pq
                    pq.write_table(table, buf, compression="snappy")
                    body = buf.getvalue()

                    key = f"{mart_name}/snapshot.parquet"
                    await s3.put_object(
                        Bucket=self.gold,
                        Key=key,
                        Body=body,
                        ContentType="application/octet-stream",
                        Metadata={
                            "mart": mart_name,
                            "rows": str(table.num_rows),
                            "built_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    logger.info("Built gold mart %s: %d rows, %d bytes",
                                mart_name, table.num_rows, len(body))

                self._builds += 1
                manifest = {
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                    "marts": list(MART_DEFINITIONS.keys()),
                    "build_number": self._builds,
                }
                await s3.put_object(
                    Bucket=self.gold,
                    Key="_manifest/last_run.json",
                    Body=json.dumps(manifest, indent=2).encode("utf-8"),
                    ContentType="application/json",
                )
                self.heartbeat.extra["builds"] = self._builds
            finally:
                con.close()


async def main():
    builder = GoldBuilder()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(builder.stop()))
    try:
        await builder.start()
    except KeyboardInterrupt:
        await builder.stop()


if __name__ == "__main__":
    asyncio.run(main())
