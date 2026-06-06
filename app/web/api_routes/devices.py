"""Device management API routes."""

import logging

from fastapi import APIRouter, HTTPException

from app.config import load_config, save_config
from app.models import DeviceConfig

router = APIRouter(prefix="/devices", tags=["devices"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_devices():
    """List all devices."""
    config = load_config()
    return {"devices": [d.model_dump() for d in config.devices]}


@router.post("")
async def add_device(device: DeviceConfig):
    """Add a new device."""
    config = load_config()

    if any(d.name == device.name for d in config.devices):
        raise HTTPException(status_code=400, detail="Device name already exists")

    config.devices.append(device)
    save_config(config)
    logger.info(f"Added device: {device.name}")
    return {"status": "success", "device": device.model_dump()}


@router.put("/{name}")
async def update_device(name: str, device: DeviceConfig):
    """Update an existing device."""
    config = load_config()

    idx = next((i for i, d in enumerate(config.devices) if d.name == name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Device not found")

    config.devices[idx] = device
    save_config(config)
    logger.info(f"Updated device: {name}")
    return {"status": "success", "device": device.model_dump()}


@router.delete("/{name}")
async def delete_device(name: str):
    """Delete a device."""
    config = load_config()

    original_len = len(config.devices)
    config.devices = [d for d in config.devices if d.name != name]

    if len(config.devices) == original_len:
        raise HTTPException(status_code=404, detail="Device not found")

    save_config(config)
    logger.info(f"Deleted device: {name}")
    return {"status": "success"}


@router.post("/{name}/test")
async def test_device(name: str):
    """Test connection to a device."""
    from app.collectors import create_collector

    config = load_config()
    device = next((d for d in config.devices if d.name == name), None)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    collector = create_collector(device)
    try:
        connected = await collector.connect()
        if connected:
            await collector.disconnect()
            return {"status": "success", "message": f"Connection to {name} successful"}
        return {"status": "error", "message": f"Failed to connect to {name}"}
    except Exception as e:
        logger.exception(f"Error testing device {name}")
        return {"status": "error", "message": str(e)}