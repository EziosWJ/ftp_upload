"""Schedule management API routes."""

import logging

from fastapi import APIRouter, HTTPException

from app.config import load_config, save_config
from app.models import ScheduleConfig

router = APIRouter(prefix="/schedules", tags=["schedules"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_schedules():
    """List all schedules."""
    config = load_config()
    return {"schedules": [s.model_dump() for s in config.schedules]}


@router.post("")
async def add_schedule(schedule: ScheduleConfig):
    """Add a new schedule."""
    config = load_config()

    if any(s.device_name == schedule.device_name for s in config.schedules):
        raise HTTPException(status_code=400, detail="Schedule for this device already exists")

    config.schedules.append(schedule)
    save_config(config)
    logger.info(f"Added schedule for device: {schedule.device_name}")
    return {"status": "success", "schedule": schedule.model_dump()}


@router.delete("/{device_name}")
async def delete_schedule(device_name: str):
    """Delete a schedule by device name."""
    config = load_config()

    original_len = len(config.schedules)
    config.schedules = [s for s in config.schedules if s.device_name != device_name]

    if len(config.schedules) == original_len:
        raise HTTPException(status_code=404, detail="Schedule not found")

    save_config(config)
    logger.info(f"Deleted schedule for device: {device_name}")
    return {"status": "success"}