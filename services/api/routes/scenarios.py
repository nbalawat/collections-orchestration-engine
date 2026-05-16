"""Scenario endpoints — trigger pre-scripted demo scenarios."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

_runner = None


async def _get_runner():
    global _runner
    if _runner is None:
        from services.channel_simulators.scenarios import ScenarioRunner
        _runner = ScenarioRunner()
        await _runner.start()
    return _runner


class ScenarioRequest(BaseModel):
    customer_id: str = ""
    count: int = 20


@router.get("")
async def list_scenarios():
    return {
        "scenarios": [
            {
                "id": "cross_channel",
                "name": "Cross-Channel Journey",
                "description": "Jane Doe: 45 DPD -> SMS dunning -> hardship reply -> email -> bounce -> voice -> resolution",
                "default_customer": "CUST-0032",
            },
            {
                "id": "bankruptcy",
                "name": "Bankruptcy Suppression",
                "description": "Robert Chen: mid-journey -> bankruptcy filed -> all actions suppressed -> dismissed -> resumes",
                "default_customer": "CUST-0095",
            },
            {
                "id": "ptp",
                "name": "PTP Lifecycle",
                "description": "Maria Garcia: voice call -> PTP -> timer -> payment arrives -> cure",
                "default_customer": "CUST-0055",
            },
            {
                "id": "strategy_swap",
                "name": "Strategy Hot-Swap",
                "description": "Multiple customers running -> strategy version changes -> journeys pick up new rules",
                "default_customer": "",
            },
            {
                "id": "complex_case",
                "name": "Complex Case (AI Reasoning)",
                "description": "David Park: conflicting signals -> AI reasoning agent -> specialist review",
                "default_customer": "CUST-0120",
            },
            {
                "id": "portfolio",
                "name": "Portfolio Operations",
                "description": "Spin up many customer journeys to show portfolio-level operations",
                "default_customer": "",
            },
        ]
    }


@router.post("/{scenario_id}/run")
async def run_scenario(scenario_id: str, body: ScenarioRequest):
    try:
        runner = await _get_runner()
        scenario_map = {
            "cross_channel": lambda: runner.scenario_cross_channel(body.customer_id or "CUST-0032"),
            "bankruptcy": lambda: runner.scenario_bankruptcy(body.customer_id or "CUST-0095"),
            "ptp": lambda: runner.scenario_ptp(body.customer_id or "CUST-0055"),
            "strategy_swap": lambda: runner.scenario_strategy_swap(),
            "complex_case": lambda: runner.scenario_complex_case(body.customer_id or "CUST-0120"),
            "portfolio": lambda: runner.scenario_portfolio(count=body.count),
        }

        if scenario_id not in scenario_map:
            raise HTTPException(404, f"Unknown scenario: {scenario_id}")

        result = await scenario_map[scenario_id]()
        return {"scenario": scenario_id, "status": "completed", "result": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Scenario %s failed", scenario_id)
        raise HTTPException(500, f"Scenario failed: {e}")
