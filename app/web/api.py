"""REST API endpoints."""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import load_config, save_config
from ..models import (
    AppConfig, DeviceConfig, DeviceType, ScheduleConfig,
    FtpConfig, ModbusRegisterConfig, S7AreaConfig, DataType, SystemInfo,
    DeviceBasicInfo, SafetyCertInfo
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/devices")
async def list_devices():
    """List all devices."""
    config = load_config()
    return {"devices": [d.model_dump() for d in config.devices]}


@router.post("/devices")
async def add_device(device: DeviceConfig):
    """Add a new device."""
    config = load_config()

    # Check for duplicate name
    if any(d.name == device.name for d in config.devices):
        raise HTTPException(status_code=400, detail="Device name already exists")

    config.devices.append(device)
    save_config(config)
    logger.info(f"Added device: {device.name}")
    return {"status": "success", "device": device.model_dump()}


@router.put("/devices/{name}")
async def update_device(name: str, device: DeviceConfig):
    """Update an existing device."""
    config = load_config()

    # Find device index
    idx = next((i for i, d in enumerate(config.devices) if d.name == name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Device not found")

    # Update device (keep original name if changed)
    config.devices[idx] = device
    save_config(config)
    logger.info(f"Updated device: {name}")
    return {"status": "success", "device": device.model_dump()}


@router.delete("/devices/{name}")
async def delete_device(name: str):
    """Delete a device."""
    config = load_config()

    # Find and remove device
    original_len = len(config.devices)
    config.devices = [d for d in config.devices if d.name != name]

    if len(config.devices) == original_len:
        raise HTTPException(status_code=404, detail="Device not found")

    # Also remove associated schedule
    config.schedules = [s for s in config.schedules if s.device_name != name]

    save_config(config)
    logger.info(f"Deleted device: {name}")
    return {"status": "success"}


@router.post("/devices/{name}/test")
async def test_device(name: str):
    """Test device connection with protocol logs."""
    config = load_config()
    device = next((d for d in config.devices if d.name == name), None)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    from ..collectors.modbus_collector import ModbusCollector
    from ..collectors.s7_collector import S7Collector

    collector: ModbusCollector | S7Collector
    if device.device_type == DeviceType.MODBUS_TCP:
        collector = ModbusCollector(device)
    else:
        collector = S7Collector(device)

    try:
        ok, logs = await collector.test_with_logs()
        log_text = "\n".join(logs)
        if ok:
            return {"status": "success", "message": f"设备 {name} 连接成功", "logs": log_text}
        return {"status": "error", "message": f"设备 {name} 连接失败", "logs": log_text}
    except Exception as e:
        return {"status": "error", "message": f"连接测试异常: {e}", "logs": ""}


@router.get("/schedules")
async def list_schedules():
    """List all schedules."""
    config = load_config()
    return {"schedules": [s.model_dump() for s in config.schedules]}


@router.post("/schedules")
async def add_or_update_schedule(schedule: ScheduleConfig):
    """Add or update a schedule."""
    config = load_config()

    # Find existing schedule for this device
    idx = next((i for i, s in enumerate(config.schedules)
                if s.device_name == schedule.device_name), None)

    if idx is not None:
        config.schedules[idx] = schedule
    else:
        config.schedules.append(schedule)

    save_config(config)

    # Activate the schedule in the scheduler
    from ..scheduler import add_device_job
    if schedule.enabled:
        await add_device_job(schedule.device_name)

    logger.info(f"Updated schedule for: {schedule.device_name}")
    return {"status": "success", "schedule": schedule.model_dump()}


@router.delete("/schedules/{device_name}")
async def delete_schedule(device_name: str):
    """Delete a schedule."""
    config = load_config()

    original_len = len(config.schedules)
    config.schedules = [s for s in config.schedules if s.device_name != device_name]

    if len(config.schedules) == original_len:
        raise HTTPException(status_code=404, detail="Schedule not found")

    save_config(config)

    # Remove the job from the scheduler
    from ..scheduler import remove_device_job
    remove_device_job(device_name)

    logger.info(f"Deleted schedule for: {device_name}")
    return {"status": "success"}


@router.get("/ftp")
async def get_ftp_config():
    """Get FTP configuration."""
    config = load_config()
    return {"ftp": config.ftp.model_dump()}


@router.post("/ftp")
async def update_ftp_config(ftp_config: FtpConfig):
    """Update FTP configuration and restart uploader if needed."""
    config = load_config()
    config.ftp = ftp_config
    save_config(config)

    # Restart uploader so changes take effect immediately
    from ..ftp_uploader import stop_ftp_uploader, start_ftp_uploader
    await stop_ftp_uploader()
    await start_ftp_uploader()

    logger.info("Updated FTP configuration and restarted uploader")
    return {"status": "success", "ftp": ftp_config.model_dump()}


@router.get("/ftp/status")
async def ftp_upload_status():
    """Get FTP upload runtime status."""
    from ..ftp_uploader import get_upload_status
    return get_upload_status()


@router.post("/ftp/upload-now")
async def ftp_upload_now():
    """Manually trigger an immediate upload of pending files."""
    config = load_config()
    if not config.ftp.host:
        return {"status": "error", "message": "FTP 服务器未配置"}

    from ..ftp_uploader import upload_pending_files
    uploaded = await upload_pending_files(config.ftp, config.data_dir)
    if uploaded:
        return {"status": "success", "message": f"已上传 {len(uploaded)} 个文件", "files": uploaded}


# Device Basic Info API
@router.get("/basic-devices")
async def list_basic_devices():
    """List all basic device info."""
    config = load_config()
    return {"basic_devices": [d.model_dump() for d in config.basic_devices]}


@router.post("/basic-devices")
async def add_basic_device(device: DeviceBasicInfo):
    """Add a new basic device info."""
    config = load_config()

    # Check for duplicate name
    if any(d.device_name == device.device_name for d in config.basic_devices):
        raise HTTPException(status_code=400, detail="设备名称已存在")

    config.basic_devices.append(device)
    save_config(config)
    logger.info(f"Added basic device: {device.device_name}")
    return {"status": "success", "device": device.model_dump()}


@router.put("/basic-devices/{device_name}")
async def update_basic_device(device_name: str, device: DeviceBasicInfo):
    """Update an existing basic device info."""
    config = load_config()

    idx = next((i for i, d in enumerate(config.basic_devices) if d.device_name == device_name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    config.basic_devices[idx] = device
    save_config(config)
    logger.info(f"Updated basic device: {device_name}")
    return {"status": "success", "device": device.model_dump()}


@router.delete("/basic-devices/{device_name}")
async def delete_basic_device(device_name: str):
    """Delete a basic device info."""
    config = load_config()

    original_len = len(config.basic_devices)
    config.basic_devices = [d for d in config.basic_devices if d.device_name != device_name]

    if len(config.basic_devices) == original_len:
        raise HTTPException(status_code=404, detail="设备不存在")

    save_config(config)
    logger.info(f"Deleted basic device: {device_name}")
    return {"status": "success"}


# Safety Certificate Info API
@router.get("/safety-certs")
async def list_safety_certs():
    """List all safety certificate info."""
    config = load_config()
    return {"safety_certs": [c.model_dump() for c in config.safety_cert_list]}


@router.post("/safety-certs")
async def add_safety_cert(cert: SafetyCertInfo):
    """Add a new safety certificate info."""
    config = load_config()

    # Check for duplicate device_name
    if any(c.device_name == cert.device_name for c in config.safety_cert_list):
        raise HTTPException(status_code=400, detail="该设备的安标信息已存在")

    config.safety_cert_list.append(cert)
    save_config(config)
    logger.info(f"Added safety cert for device: {cert.device_name}")
    return {"status": "success", "cert": cert.model_dump()}


@router.put("/safety-certs/{device_name}")
async def update_safety_cert(device_name: str, cert: SafetyCertInfo):
    """Update an existing safety certificate info."""
    config = load_config()

    idx = next((i for i, c in enumerate(config.safety_cert_list) if c.device_name == device_name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="安标信息不存在")

    config.safety_cert_list[idx] = cert
    save_config(config)
    logger.info(f"Updated safety cert for device: {device_name}")
    return {"status": "success", "cert": cert.model_dump()}


@router.delete("/safety-certs/{device_name}")
async def delete_safety_cert(device_name: str):
    """Delete a safety certificate info."""
    config = load_config()

    original_len = len(config.safety_cert_list)
    config.safety_cert_list = [c for c in config.safety_cert_list if c.device_name != device_name]

    if len(config.safety_cert_list) == original_len:
        raise HTTPException(status_code=404, detail="安标信息不存在")

    save_config(config)
    logger.info(f"Deleted safety cert for device: {device_name}")
    return {"status": "success"}


@router.get("/safety-certs/{device_name}")
async def get_safety_cert(device_name: str):
    """Get safety certificate info for a specific device."""
    config = load_config()

    cert = next((c for c in config.safety_cert_list if c.device_name == device_name), None)
    if cert is None:
        raise HTTPException(status_code=404, detail="安标信息不存在")

    return {"cert": cert.model_dump()}


@router.post("/ftp/test")
async def test_ftp_connection():
    """Test FTP connection."""
    config = load_config()
    from ..ftp_uploader import test_ftp_connection as _test
    ok, msg = await _test(config.ftp)
    if ok:
        return {"status": "success", "message": msg}
    return {"status": "error", "message": msg}


@router.get("/system-info")
async def get_system_info():
    """Get system information."""
    config = load_config()
    return {"system_info": config.system_info.model_dump()}


@router.post("/system-info")
async def update_system_info(system_info: SystemInfo):
    """Update system information."""
    config = load_config()
    config.system_info = system_info
    save_config(config)
    logger.info("Updated system information")
    return {"status": "success", "system_info": system_info.model_dump()}


@router.get("/status")
async def system_status():
    """Get system status."""
    from ..scheduler import get_device_statuses
    config = load_config()
    device_statuses = get_device_statuses()
    online_count = sum(1 for s in device_statuses.values() if s["online"])
    return {
        "devices": {
            "total": len(config.devices),
            "enabled": len([d for d in config.devices if d.enabled]),
            "online": online_count,
        },
        "schedules": {
            "total": len(config.schedules),
            "enabled": len([s for s in config.schedules if s.enabled])
        },
        "ftp": {
            "enabled": config.ftp.enabled,
            "host": config.ftp.host
        },
        "timestamp": datetime.now().isoformat()
    }


@router.get("/device-status")
async def device_statuses():
    """Get per-device online/offline status."""
    from ..scheduler import get_device_statuses
    return get_device_statuses()


@router.get("/logs")
async def get_logs(level: str = "INFO", limit: int = 100):
    """Get recent log entries from app.log."""
    log_lines = []
    log_file = Path(__file__).parent.parent.parent / "app.log"

    if log_file.exists():
        try:
            all_lines = log_file.read_text(encoding="utf-8").splitlines()
            # Filter by minimum level
            level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            min_idx = level_order.index(level) if level in level_order else 1

            filtered = []
            for line in all_lines:
                matched = False
                for lvl in level_order[min_idx:]:
                    if f"] {lvl}:" in line:
                        filtered.append(line)
                        matched = True
                        break
                if not matched:
                    # Lines without a level tag (e.g. stack traces) are included
                    filtered.append(line)

            log_lines = filtered[-limit:]
        except Exception:
            pass

    return {"logs": log_lines, "count": len(log_lines)}
