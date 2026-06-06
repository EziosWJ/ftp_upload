"""Basic info API routes (JBSJ/ABSJ/JZTT/JCJY/YC)."""

import logging

from fastapi import APIRouter, HTTPException

from app.config import load_config
from .repos import (
    basic_device_repo, safety_cert_repo, obsolete_device_repo,
    device_test_repo, alarm_data_repo,
)

router = APIRouter(tags=["basic-info"])
logger = logging.getLogger(__name__)


@router.get("/api/basic-devices")
async def list_basic_devices():
    """List all basic devices (JBSJ)."""
    items = basic_device_repo.list()
    return {"items": [i.model_dump() for i in items]}


@router.post("/api/basic-devices")
async def add_basic_device(item: basic_device_repo.model_cls):
    """Add a basic device."""
    result = basic_device_repo.add(item)
    return {"status": "success", "item": result.model_dump()}


@router.put("/api/basic-devices/{device_name}")
async def update_basic_device(device_name: str, item: basic_device_repo.model_cls):
    """Update a basic device."""
    result = basic_device_repo.update(device_name, item)
    return {"status": "success", "item": result.model_dump()}


@router.delete("/api/basic-devices/{device_name}")
async def delete_basic_device(device_name: str):
    """Delete a basic device."""
    basic_device_repo.delete(device_name)
    return {"status": "success"}


@router.get("/api/safety-certs")
async def list_safety_certs():
    """List all safety certificates (ABSJ)."""
    items = safety_cert_repo.list()
    return {"items": [i.model_dump() for i in items]}


@router.post("/api/safety-certs")
async def add_safety_cert(item: safety_cert_repo.model_cls):
    """Add a safety certificate."""
    result = safety_cert_repo.add(item)
    return {"status": "success", "item": result.model_dump()}


@router.put("/api/safety-certs/{device_name}")
async def update_safety_cert(device_name: str, item: safety_cert_repo.model_cls):
    """Update a safety certificate."""
    result = safety_cert_repo.update(device_name, item)
    return {"status": "success", "item": result.model_dump()}


@router.delete("/api/safety-certs/{device_name}")
async def delete_safety_cert(device_name: str):
    """Delete a safety certificate."""
    safety_cert_repo.delete(device_name)
    return {"status": "success"}


@router.get("/api/safety-certs/{device_name}")
async def get_safety_cert(device_name: str):
    """Get a safety certificate by device name."""
    item = safety_cert_repo.get(device_name)
    if not item:
        raise HTTPException(status_code=404, detail="Safety cert not found")
    return {"item": item.model_dump()}


@router.get("/api/obsolete-devices")
async def list_obsolete_devices():
    """List all obsolete devices (JZTT)."""
    items = obsolete_device_repo.list()
    return {"items": [i.model_dump() for i in items]}


@router.post("/api/obsolete-devices")
async def add_obsolete_device(item: obsolete_device_repo.model_cls):
    """Add an obsolete device."""
    result = obsolete_device_repo.add(item)
    return {"status": "success", "item": result.model_dump()}


@router.put("/api/obsolete-devices/{product_name}")
async def update_obsolete_device(product_name: str, item: obsolete_device_repo.model_cls):
    """Update an obsolete device."""
    result = obsolete_device_repo.update(product_name, item)
    return {"status": "success", "item": result.model_dump()}


@router.delete("/api/obsolete-devices/{product_name}")
async def delete_obsolete_device(product_name: str):
    """Delete an obsolete device."""
    obsolete_device_repo.delete(product_name)
    return {"status": "success"}


@router.get("/api/device-tests")
async def list_device_tests():
    """List all device tests (JCJY)."""
    items = device_test_repo.list()
    return {"items": [i.model_dump() for i in items]}


@router.post("/api/device-tests")
async def add_device_test(item: device_test_repo.model_cls):
    """Add a device test."""
    result = device_test_repo.add(item)
    return {"status": "success", "item": result.model_dump()}


@router.put("/api/device-tests/{factory_code}")
async def update_device_test(factory_code: str, item: device_test_repo.model_cls):
    """Update a device test."""
    result = device_test_repo.update(factory_code, item)
    return {"status": "success", "item": result.model_dump()}


@router.delete("/api/device-tests/{factory_code}")
async def delete_device_test(factory_code: str):
    """Delete a device test."""
    device_test_repo.delete(factory_code)
    return {"status": "success"}


@router.get("/api/alarm-data")
async def list_alarm_data():
    """List all alarm data (YC)."""
    items = alarm_data_repo.list()
    return {"items": [i.model_dump() for i in items]}


@router.post("/api/alarm-data")
async def add_alarm_data(item: alarm_data_repo.model_cls):
    """Add alarm data."""
    result = alarm_data_repo.add(item)
    return {"status": "success", "item": result.model_dump()}


@router.put("/api/alarm-data/{point_code}")
async def update_alarm_data(point_code: str, item: alarm_data_repo.model_cls):
    """Update alarm data."""
    result = alarm_data_repo.update(point_code, item)
    return {"status": "success", "item": result.model_dump()}


@router.delete("/api/alarm-data/{point_code}")
async def delete_alarm_data(point_code: str):
    """Delete alarm data."""
    alarm_data_repo.delete(point_code)
    return {"status": "success"}