"""AI Agent endpoints — invoke any of the 5 agents and get reasoning traces."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.ai_agents import (
    DigitalChannelAgent,
    CopilotAgent,
    CaseReasoningAgent,
    PortfolioIntelligenceAgent,
    QualityComplianceAgent,
)
from services.shared.db import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)

AGENTS = {
    "digital_channel": DigitalChannelAgent,
    "copilot": CopilotAgent,
    "case_reasoning": CaseReasoningAgent,
    "portfolio_intelligence": PortfolioIntelligenceAgent,
    "quality_compliance": QualityComplianceAgent,
}


@router.get("")
async def list_agents():
    return {
        "agents": [
            {
                "id": key,
                "name": cls.__doc__.split("\n")[0].strip() if cls.__doc__ else key,
                "agent_type": cls.agent_type.value,
                "model": cls.model,
                "tool_count": len(cls().get_tools()),
            }
            for key, cls in AGENTS.items()
        ]
    }


class DigitalChannelInput(BaseModel):
    customer_id: str
    message: str
    channel: str = "sms"


@router.post("/digital-channel/invoke")
async def invoke_digital_channel(body: DigitalChannelInput):
    agent = DigitalChannelAgent()
    result = await agent.invoke({
        "customer_id": body.customer_id,
        "message": body.message,
        "channel": body.channel,
    })
    return result


class CopilotInput(BaseModel):
    customer_id: str
    request_type: str = "nba"
    channel: str = "voice"
    interaction_context: str = ""
    form_type: str = ""
    duration_seconds: int = 0


@router.post("/copilot/invoke")
async def invoke_copilot(body: CopilotInput):
    agent = CopilotAgent()
    result = await agent.invoke(body.model_dump())
    return result


class CaseReasoningInput(BaseModel):
    customer_id: str
    reason: str = "complex case requiring analysis"
    trigger: str = ""
    prior_actions: list[str] = []


@router.post("/case-reasoning/invoke")
async def invoke_case_reasoning(body: CaseReasoningInput):
    agent = CaseReasoningAgent()
    result = await agent.invoke(body.model_dump())
    return result


class PortfolioInput(BaseModel):
    analysis_type: str = "portfolio_health"
    question: str = ""
    segment: str = ""
    cohort_a: str = ""
    cohort_b: str = ""
    time_range: str = "30 days"


@router.post("/portfolio/invoke")
async def invoke_portfolio(body: PortfolioInput):
    agent = PortfolioIntelligenceAgent()
    result = await agent.invoke(body.model_dump())
    return result


class QualityInput(BaseModel):
    customer_id: str = ""
    interaction_id: str = ""
    agent_id: str = ""
    channel: str = "voice"
    review_type: str = "full"


@router.post("/quality/invoke")
async def invoke_quality(body: QualityInput):
    agent = QualityComplianceAgent()
    result = await agent.invoke(body.model_dump())
    return result


@router.get("/reasoning-traces")
async def list_reasoning_traces(
    limit: int = 20,
    agent_type: str = "",
    customer_id: str = "",
):
    conditions = ["event_category = 'ai_reasoning'"]
    params = {"limit": limit}

    if agent_type:
        conditions.append("payload->>'agent_type' = :agent_type")
        params["agent_type"] = agent_type
    if customer_id:
        conditions.append("customer_id = :customer_id")
        params["customer_id"] = customer_id

    where = "WHERE " + " AND ".join(conditions)

    rows = await execute_query(f"""
        SELECT event_id, customer_id, event_type, payload, source_service, occurred_at
        FROM customer_events
        {where}
        ORDER BY occurred_at DESC LIMIT :limit
    """, params)
    return {"traces": rows}
