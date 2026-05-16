"""FastAPI BFF — REST + WebSocket API for the collections orchestration engine.

Run: uv run python -m services.api.main
"""
from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

import logging
from contextlib import asynccontextmanager

import decimal
import datetime
import uuid

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from services.api.routes.customers import router as customers_router
from services.api.routes.workflows import router as workflows_router
from services.api.routes.agents import router as agents_router
from services.api.routes.portfolio import router as portfolio_router
from services.api.routes.events import router as events_router
from services.api.routes.strategies import router as strategies_router
from services.api.routes.scenarios import router as scenarios_router
from services.api.routes.platform import router as platform_router
from services.api.ws.handler import router as ws_router
from services.shared.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Collections API starting on %s:%d", settings.api_host, settings.api_port)

    from services.shared.db import get_db_pool
    get_db_pool()
    logger.info("Database pool initialized")

    yield

    logger.info("Collections API shutting down")


app = FastAPI(
    title="Collections Orchestration Engine",
    description="Real-time collections orchestration with AI agents",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers_router, prefix="/api/customers", tags=["customers"])
app.include_router(workflows_router, prefix="/api/workflows", tags=["workflows"])
app.include_router(agents_router, prefix="/api/agents", tags=["ai-agents"])
app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(events_router, prefix="/api/events", tags=["events"])
app.include_router(strategies_router, prefix="/api/strategies", tags=["strategies"])
app.include_router(scenarios_router, prefix="/api/scenarios", tags=["scenarios"])
app.include_router(platform_router, prefix="/api/platform", tags=["platform-ops"])
app.include_router(ws_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "collections-api"}


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "services.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
