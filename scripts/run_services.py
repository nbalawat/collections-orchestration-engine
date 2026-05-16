"""Start all Python services for the collections orchestration engine.

Run: uv run python -m scripts.run_services
Requires: Docker Compose services running (postgres, redis, kafka, temporal, opa)
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-7s %(message)s",
)
logger = logging.getLogger("run_services")

SERVICES = [
    ("API Server", "services.api.main", ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]),
    ("Temporal Worker", "workflows.worker", [sys.executable, "-m", "workflows.worker"]),
    ("Signal Bridge", "services.signal_bridge", [sys.executable, "-m", "services.signal_bridge"]),
    ("Event Projector", "services.event_projector", [sys.executable, "-m", "services.event_projector"]),
]


async def run_service(name: str, cmd: list[str]) -> asyncio.subprocess.Process:
    logger.info("Starting %s: %s", name, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def stream_output():
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode().rstrip()
            if text:
                logger.info("[%s] %s", name[:12], text)

    asyncio.create_task(stream_output())
    return proc


async def main():
    logger.info("=" * 60)
    logger.info("Collections Orchestration Engine — Starting All Services")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Prerequisites: docker compose up -d")
    logger.info("")

    processes = []
    for name, module, cmd in SERVICES:
        proc = await run_service(name, cmd)
        processes.append((name, proc))
        await asyncio.sleep(2)

    logger.info("")
    logger.info("All services started:")
    for name, proc in processes:
        logger.info("  %s (PID %d)", name, proc.pid)
    logger.info("")
    logger.info("API:       http://localhost:8000")
    logger.info("API Docs:  http://localhost:8000/docs")
    logger.info("Frontend:  cd web && pnpm dev  (http://localhost:5173)")
    logger.info("")
    logger.info("Press Ctrl+C to stop all services")

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    logger.info("\nStopping all services...")
    for name, proc in reversed(processes):
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
            logger.info("  %s stopped", name)
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning("  %s killed", name)


if __name__ == "__main__":
    asyncio.run(main())
