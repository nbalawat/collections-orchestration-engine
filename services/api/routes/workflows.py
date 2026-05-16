"""Workflow endpoints — Temporal journey state, signals, and management."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from temporalio.client import Client

from services.shared.config import get_settings
from workflows.customer_journey import CustomerJourney
from workflows.types import ChannelEventSignal, PaymentSignal, ComplianceFlagSignal

router = APIRouter()
logger = logging.getLogger(__name__)

settings = get_settings()


async def _get_temporal() -> Client:
    return await Client.connect(settings.temporal_host)


@router.get("/{customer_id}")
async def get_journey_state(customer_id: str):
    try:
        client = await _get_temporal()
        handle = client.get_workflow_handle(f"journey-{customer_id}")
        state = await handle.query(CustomerJourney.snapshot)
        return state
    except Exception as e:
        raise HTTPException(404, f"No active journey for {customer_id}: {e}")


@router.post("/{customer_id}/start")
async def start_journey(customer_id: str):
    try:
        client = await _get_temporal()
        workflow_id = f"journey-{customer_id}"
        await client.start_workflow(
            CustomerJourney.run,
            customer_id,
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )
        return {"workflow_id": workflow_id, "status": "started"}
    except Exception as e:
        raise HTTPException(400, f"Failed to start journey: {e}")


@router.get("/{customer_id}/events")
async def get_journey_events(customer_id: str):
    try:
        client = await _get_temporal()
        handle = client.get_workflow_handle(f"journey-{customer_id}")
        events = await handle.query(CustomerJourney.recent_events)
        return {"events": events}
    except Exception as e:
        raise HTTPException(404, str(e))


@router.get("/{customer_id}/actions")
async def get_journey_actions(customer_id: str):
    try:
        client = await _get_temporal()
        handle = client.get_workflow_handle(f"journey-{customer_id}")
        actions = await handle.query(CustomerJourney.actions_taken)
        return {"actions": actions}
    except Exception as e:
        raise HTTPException(404, str(e))


class ChannelEventInput(BaseModel):
    channel: str = "digital"
    direction: str = "inbound"
    event_type: str = "message"
    intent: str | None = None
    payload: dict = {}


@router.post("/{customer_id}/signal/channel-event")
async def signal_channel_event(customer_id: str, body: ChannelEventInput):
    try:
        client = await _get_temporal()
        handle = client.get_workflow_handle(f"journey-{customer_id}")
        await handle.signal(
            CustomerJourney.channel_event,
            ChannelEventSignal(
                customer_id=customer_id,
                channel=body.channel,
                direction=body.direction,
                event_type=body.event_type,
                intent=body.intent,
                payload=body.payload,
            ),
        )
        return {"status": "signaled", "signal": "channel_event"}
    except Exception as e:
        raise HTTPException(400, str(e))


class PaymentInput(BaseModel):
    amount: float
    payment_date: str
    account_id: str
    method: str = "ach"


@router.post("/{customer_id}/signal/payment")
async def signal_payment(customer_id: str, body: PaymentInput):
    try:
        client = await _get_temporal()
        handle = client.get_workflow_handle(f"journey-{customer_id}")
        await handle.signal(
            CustomerJourney.payment_received,
            PaymentSignal(
                amount=body.amount,
                payment_date=body.payment_date,
                account_id=body.account_id,
                method=body.method,
            ),
        )
        return {"status": "signaled", "signal": "payment_received"}
    except Exception as e:
        raise HTTPException(400, str(e))


class ComplianceFlagInput(BaseModel):
    flag_type: str
    reason: str
    action: str = "activate"


@router.post("/{customer_id}/signal/compliance-flag")
async def signal_compliance_flag(customer_id: str, body: ComplianceFlagInput):
    try:
        client = await _get_temporal()
        handle = client.get_workflow_handle(f"journey-{customer_id}")
        await handle.signal(
            CustomerJourney.compliance_flag,
            ComplianceFlagSignal(
                flag_type=body.flag_type,
                reason=body.reason,
                action=body.action,
            ),
        )
        return {"status": "signaled", "signal": "compliance_flag"}
    except Exception as e:
        raise HTTPException(400, str(e))
