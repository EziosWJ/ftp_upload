"""Measure point API routes."""

import logging

from fastapi import APIRouter, HTTPException

from .repos import measure_point_repo, measure_point_realtime_repo

router = APIRouter(tags=["measure-points"])
logger = logging.getLogger(__name__)


@router.get("/api/measure-points")
async def list_measure_points():
    """List all measure points (JC)."""
    items = measure_point_repo.list()
    return {"items": [i.model_dump() for i in items]}


@router.post("/api/measure-points")
async def add_measure_point(item: measure_point_repo.model_cls):
    """Add a measure point."""
    result = measure_point_repo.add(item)
    return {"status": "success", "item": result.model_dump()}


@router.put("/api/measure-points/{point_code}")
async def update_measure_point(point_code: str, item: measure_point_repo.model_cls):
    """Update a measure point."""
    result = measure_point_repo.update(point_code, item)
    return {"status": "success", "item": result.model_dump()}


@router.delete("/api/measure-points/{point_code}")
async def delete_measure_point(point_code: str):
    """Delete a measure point."""
    measure_point_repo.delete(point_code)
    return {"status": "success"}


@router.get("/api/measure-points/{point_code}")
async def get_measure_point(point_code: str):
    """Get a measure point by code."""
    item = measure_point_repo.get(point_code)
    if not item:
        raise HTTPException(status_code=404, detail="Measure point not found")
    return {"item": item.model_dump()}


@router.get("/api/measure-point-realtime")
async def list_measure_point_realtime():
    """List all measure point realtime data (SS)."""
    items = measure_point_realtime_repo.list()
    return {"items": [i.model_dump() for i in items]}


@router.post("/api/measure-point-realtime")
async def add_measure_point_realtime(item: measure_point_realtime_repo.model_cls):
    """Add measure point realtime data."""
    result = measure_point_realtime_repo.add(item)
    return {"status": "success", "item": result.model_dump()}


@router.put("/api/measure-point-realtime/{point_code}")
async def update_measure_point_realtime(point_code: str, item: measure_point_realtime_repo.model_cls):
    """Update measure point realtime data."""
    result = measure_point_realtime_repo.update(point_code, item)
    return {"status": "success", "item": result.model_dump()}


@router.delete("/api/measure-point-realtime/{point_code}")
async def delete_measure_point_realtime(point_code: str):
    """Delete measure point realtime data."""
    measure_point_realtime_repo.delete(point_code)
    return {"status": "success"}


@router.get("/api/measure-point-realtime/{point_code}")
async def get_measure_point_realtime(point_code: str):
    """Get measure point realtime data by code."""
    item = measure_point_realtime_repo.get(point_code)
    if not item:
        raise HTTPException(status_code=404, detail="Measure point realtime not found")
    return {"item": item.model_dump()}