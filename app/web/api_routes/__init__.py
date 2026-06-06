"""Aggregated API routes from modular structure.

This module provides a unified router by combining routes from:
- devices: Device management (Modbus TCP / S7 PLC)
- schedules: Schedule/polling configuration
- basic_info: JBSJ/ABSJ/JZTT/JCJY/YC data management
- measure_points: JC/SS measure point configuration
- system: FTP, reports, status, logs
- mq: MQTT message queue publishing
- upload_config: Upload task and system device configuration
"""

from fastapi import APIRouter

from .devices import router as devices_router
from .schedules import router as schedules_router
from .basic_info import router as basic_info_router
from .measure_points import router as measure_points_router
from .system import router as system_router
from .mq import router as mq_router
from .upload_config import router as upload_config_router

router = APIRouter()

router.include_router(devices_router, prefix="/api")
router.include_router(schedules_router, prefix="/api")
router.include_router(basic_info_router)
router.include_router(measure_points_router)
router.include_router(system_router)
router.include_router(mq_router, prefix="/api")
router.include_router(upload_config_router)