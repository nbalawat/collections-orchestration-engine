"""Strategy endpoints — OPA policy evaluation, audit log, and configuration."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.shared.config import get_settings
from services.shared.db import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


@router.post("/evaluate/segmentation")
async def evaluate_segmentation(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/segmentation",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/treatment")
async def evaluate_treatment(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/treatment",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/routing")
async def evaluate_routing(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/channel_routing",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/compliance")
async def evaluate_compliance(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/compliance",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/guardrails")
async def evaluate_guardrails(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/ai_guardrails/guardrail_check",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/full")
async def evaluate_full_strategy(body: dict):
    results = {}
    async with httpx.AsyncClient() as client:
        for policy in ["segmentation", "treatment", "channel_routing", "compliance"]:
            url = f"{settings.opa_url}/v1/data/collections/{policy}"
            resp = await client.post(url, json={"input": body})
            results[policy] = resp.json().get("result", {})
    return results


@router.get("/audit-log")
async def get_audit_log(limit: int = 50):
    rows = await execute_query("""
        SELECT * FROM strategy_audit_log
        ORDER BY created_at DESC LIMIT :limit
    """, {"limit": limit})
    return {"audit_log": rows}


@router.get("/config")
async def get_strategy_config():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.opa_url}/v1/data/collections/strategy_config")
        return resp.json().get("result", {})
