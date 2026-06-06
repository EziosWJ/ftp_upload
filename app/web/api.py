"""REST API endpoints."""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import load_config, save_config
from ..models import (
    AppConfig, DeviceConfig, ScheduleConfig,
    FtpConfig, ModbusRegisterConfig, S7AreaConfig, DataType, SystemInfo,
    DeviceBasicInfo, SafetyCertInfo, MeasurePointInfo, MeasurePointRealtimeInfo,
    ObsoleteDeviceInfo, DeviceTestInfo, AlarmData,
    UploadConfig, UploadTask, RegisterPoint, DeviceWithRegisters,
)
from ..repository import CrudRepository

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# Repository instances for pure CRUD resources
basic_device_repo = CrudRepository[DeviceBasicInfo](
    "basic_devices", "device_name", DeviceBasicInfo,
    not_found_msg="设备不存在", duplicate_msg="设备名称已存在",
)
safety_cert_repo = CrudRepository[SafetyCertInfo](
    "safety_cert_list", "device_name", SafetyCertInfo,
    not_found_msg="安标信息不存在", duplicate_msg="该设备的安标信息已存在",
)
measure_point_repo = CrudRepository[MeasurePointInfo](
    "measure_point_list", "point_code", MeasurePointInfo,
    not_found_msg="测点不存在", duplicate_msg="测点编码已存在",
)
measure_point_realtime_repo = CrudRepository[MeasurePointRealtimeInfo](
    "measure_point_realtime_list", "point_code", MeasurePointRealtimeInfo,
    not_found_msg="测点实时信息不存在", duplicate_msg="测点实时信息已存在",
)
obsolete_device_repo = CrudRepository[ObsoleteDeviceInfo](
    "obsolete_device_list", "product_name", ObsoleteDeviceInfo,
    not_found_msg="淘汰设备信息不存在", duplicate_msg="该产品名称已存在",
)
device_test_repo = CrudRepository[DeviceTestInfo](
    "device_test_list", "factory_code", DeviceTestInfo,
    not_found_msg="检测检验信息不存在", duplicate_msg="该出厂编码已存在",
)
alarm_data_repo = CrudRepository[AlarmData](
    "alarm_data_list", "point_code", AlarmData,
    not_found_msg="异常数据不存在", duplicate_msg="该测点异常数据已存在",
)


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

    from ..collectors import create_collector
    collector = create_collector(device)

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
    return {"basic_devices": [d.model_dump() for d in basic_device_repo.list()]}


@router.post("/basic-devices")
async def add_basic_device(device: DeviceBasicInfo):
    """Add a new basic device info."""
    basic_device_repo.add(device)
    return {"status": "success", "device": device.model_dump()}


@router.put("/basic-devices/{device_name}")
async def update_basic_device(device_name: str, device: DeviceBasicInfo):
    """Update an existing basic device info."""
    basic_device_repo.update(device_name, device)
    return {"status": "success", "device": device.model_dump()}


@router.delete("/basic-devices/{device_name}")
async def delete_basic_device(device_name: str):
    """Delete a basic device info."""
    basic_device_repo.delete(device_name)
    return {"status": "success"}


# Safety Certificate Info API
@router.get("/safety-certs")
async def list_safety_certs():
    """List all safety certificate info."""
    return {"safety_certs": [c.model_dump() for c in safety_cert_repo.list()]}


@router.post("/safety-certs")
async def add_safety_cert(cert: SafetyCertInfo):
    """Add a new safety certificate info."""
    safety_cert_repo.add(cert)
    return {"status": "success", "cert": cert.model_dump()}


@router.put("/safety-certs/{device_name}")
async def update_safety_cert(device_name: str, cert: SafetyCertInfo):
    """Update an existing safety certificate info."""
    safety_cert_repo.update(device_name, cert)
    return {"status": "success", "cert": cert.model_dump()}


@router.delete("/safety-certs/{device_name}")
async def delete_safety_cert(device_name: str):
    """Delete a safety certificate info."""
    safety_cert_repo.delete(device_name)
    return {"status": "success"}


@router.get("/safety-certs/{device_name}")
async def get_safety_cert(device_name: str):
    """Get safety certificate info for a specific device."""
    cert = safety_cert_repo.get(device_name)
    if cert is None:
        raise HTTPException(status_code=404, detail="安标信息不存在")
    return {"cert": cert.model_dump()}


# Measure Point Info API
@router.get("/measure-points")
async def list_measure_points():
    """List all measure point info."""
    return {"measure_points": [p.model_dump() for p in measure_point_repo.list()]}


@router.post("/measure-points")
async def add_measure_point(point: MeasurePointInfo):
    """Add a new measure point info."""
    measure_point_repo.add(point)
    return {"status": "success", "point": point.model_dump()}


@router.put("/measure-points/{point_code}")
async def update_measure_point(point_code: str, point: MeasurePointInfo):
    """Update an existing measure point info."""
    measure_point_repo.update(point_code, point)
    return {"status": "success", "point": point.model_dump()}


@router.delete("/measure-points/{point_code}")
async def delete_measure_point(point_code: str):
    """Delete a measure point info."""
    measure_point_repo.delete(point_code)
    return {"status": "success"}


@router.get("/measure-points/{point_code}")
async def get_measure_point(point_code: str):
    """Get measure point info for a specific point."""
    point = measure_point_repo.get(point_code)
    if point is None:
        raise HTTPException(status_code=404, detail="测点不存在")
    return {"point": point.model_dump()}


# Measure Point Realtime Info endpoints
@router.get("/measure-point-realtime")
async def get_measure_point_realtime_list():
    """Get all measure point realtime info."""
    return {"list": [p.model_dump() for p in measure_point_realtime_repo.list()]}


@router.post("/measure-point-realtime")
async def add_measure_point_realtime(realtime: MeasurePointRealtimeInfo):
    """Add a new measure point realtime info."""
    measure_point_realtime_repo.add(realtime)
    return {"status": "success", "realtime": realtime.model_dump()}


@router.put("/measure-point-realtime/{point_code}")
async def update_measure_point_realtime(point_code: str, realtime: MeasurePointRealtimeInfo):
    """Update an existing measure point realtime info."""
    measure_point_realtime_repo.update(point_code, realtime)
    return {"status": "success", "realtime": realtime.model_dump()}


@router.delete("/measure-point-realtime/{point_code}")
async def delete_measure_point_realtime(point_code: str):
    """Delete a measure point realtime info."""
    measure_point_realtime_repo.delete(point_code)
    return {"status": "success"}


@router.get("/measure-point-realtime/{point_code}")
async def get_measure_point_realtime(point_code: str):
    """Get measure point realtime info for a specific point."""
    realtime = measure_point_realtime_repo.get(point_code)
    if realtime is None:
        raise HTTPException(status_code=404, detail="测点实时信息不存在")
    return {"realtime": realtime.model_dump()}


# Obsolete Device Info API (JZTT)
@router.get("/obsolete-devices")
async def list_obsolete_devices():
    """List all obsolete device info."""
    return {"obsolete_devices": [d.model_dump() for d in obsolete_device_repo.list()]}


@router.post("/obsolete-devices")
async def add_obsolete_device(device: ObsoleteDeviceInfo):
    """Add a new obsolete device info."""
    obsolete_device_repo.add(device)
    return {"status": "success", "device": device.model_dump()}


@router.put("/obsolete-devices/{product_name}")
async def update_obsolete_device(product_name: str, device: ObsoleteDeviceInfo):
    """Update an existing obsolete device info."""
    obsolete_device_repo.update(product_name, device)
    return {"status": "success", "device": device.model_dump()}


@router.delete("/obsolete-devices/{product_name}")
async def delete_obsolete_device(product_name: str):
    """Delete an obsolete device info."""
    obsolete_device_repo.delete(product_name)
    return {"status": "success"}


# Device Test Info API (JCJY)
@router.get("/device-tests")
async def list_device_tests():
    """List all device test info."""
    return {"device_tests": [d.model_dump() for d in device_test_repo.list()]}


@router.post("/device-tests")
async def add_device_test(test: DeviceTestInfo):
    """Add a new device test info."""
    device_test_repo.add(test)
    return {"status": "success", "test": test.model_dump()}


@router.put("/device-tests/{factory_code}")
async def update_device_test(factory_code: str, test: DeviceTestInfo):
    """Update an existing device test info."""
    device_test_repo.update(factory_code, test)
    return {"status": "success", "test": test.model_dump()}


@router.delete("/device-tests/{factory_code}")
async def delete_device_test(factory_code: str):
    """Delete a device test info."""
    device_test_repo.delete(factory_code)
    return {"status": "success"}


# Alarm Data API (YC)
@router.get("/alarm-data")
async def list_alarm_data():
    """List all alarm data."""
    return {"alarm_data": [d.model_dump() for d in alarm_data_repo.list()]}


@router.post("/alarm-data")
async def add_alarm_data(alarm: AlarmData):
    """Add a new alarm data entry."""
    alarm_data_repo.add(alarm)
    return {"status": "success", "alarm": alarm.model_dump()}


@router.put("/alarm-data/{point_code}")
async def update_alarm_data(point_code: str, alarm: AlarmData):
    """Update an existing alarm data entry."""
    alarm_data_repo.update(point_code, alarm)
    return {"status": "success", "alarm": alarm.model_dump()}


@router.delete("/alarm-data/{point_code}")
async def delete_alarm_data(point_code: str):
    """Delete an alarm data entry."""
    alarm_data_repo.delete(point_code)
    return {"status": "success"}


# ──────────── 标准报文生成 (MT/T 1201.2-2023) ────────────

@router.get("/reports/generate/{data_type}")
async def generate_report(data_type: str):
    """生成标准格式报文文件并返回内容。

    data_type: jbsj | absj | jztt | jcjy | tfjc | tfss | tfyc | psjc | psss | psyc ...
    """
    from ..formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        write_report_file, SYSTEM_MAP,
    )

    config = load_config()
    system_info = config.system_info

    formatter_map = {
        "jbsj": lambda si=system_info: format_jbsj(config.basic_devices, si),
        "absj": lambda si=system_info: format_absj(config.safety_cert_list, si),
        "jztt": lambda si=system_info: format_jztt(config.obsolete_device_list, si),
        "jcjy": lambda si=system_info: format_jcjy(config.device_test_list, si),
    }

    # 六大系统 JC/SS/YC
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        formatter_map[f"{prefix}jc"] = lambda sk=sys_key, si=system_info: format_system_jc(
            config.measure_point_list, sk, si
        )
        formatter_map[f"{prefix}ss"] = lambda sk=sys_key, si=system_info: format_system_ss(
            config.measure_point_realtime_list, sk, si
        )
        formatter_map[f"{prefix}yc"] = lambda sk=sys_key, si=system_info: format_system_yc(
            config.alarm_data_list, sk, si
        )

    if data_type not in formatter_map:
        raise HTTPException(status_code=400, detail=f"不支持的数据类型: {data_type}")

    content = formatter_map[data_type]()
    file_name = write_report_file(data_type.upper(), content, config.data_dir, system_info.mine_code or "000000000000")
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / config.data_dir
    file_path = data_dir / file_name
    file_path.write_text(content, encoding="utf-8")

    return {
        "status": "success",
        "file": str(file_path),
        "content": content,
    }


@router.post("/reports/generate-all")
async def generate_all_reports():
    """批量生成所有标准报文文件。"""
    from ..formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        write_report_file, SYSTEM_MAP,
    )

    config = load_config()
    system_info = config.system_info
    files = []

    # 静态数据
    static_generators = [
        ("JBSJ", lambda si=system_info: format_jbsj(config.basic_devices, si)),
        ("ABSJ", lambda si=system_info: format_absj(config.safety_cert_list, si)),
        ("JZTT", lambda si=system_info: format_jztt(config.obsolete_device_list, si)),
        ("JCJY", lambda si=system_info: format_jcjy(config.device_test_list, si)),
    ]
    for name, gen in static_generators:
        content = gen()
        file_name = write_report_file(name, content, config.data_dir, system_info.mine_code or "000000000000")
        project_root = Path(__file__).parent.parent.parent
        data_dir = project_root / config.data_dir
        fp = data_dir / file_name
        fp.write_text(content, encoding="utf-8")
        files.append(str(fp))

    # 六大系统动态数据
    for sys_key, (code, sys_name, short) in SYSTEM_MAP.items():
        for suffix, gen in [
            ("JC", lambda sk=sys_key, si=system_info: format_system_jc(config.measure_point_list, sk, si)),
            ("SS", lambda sk=sys_key, si=system_info: format_system_ss(config.measure_point_realtime_list, sk, si)),
            ("YC", lambda sk=sys_key, si=system_info: format_system_yc(config.alarm_data_list, sk, si)),
        ]:
            content = gen()
            file_name = write_report_file(f"{short}{suffix}", content, config.data_dir, system_info.mine_code or "000000000000")
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / config.data_dir
            fp = data_dir / file_name
            fp.write_text(content, encoding="utf-8")
            files.append(str(fp))

    return {"status": "success", "files": files, "count": len(files)}


# ──────────── 消息队列上传 (MQ) ────────────

@router.post("/mq/publish/{data_type}")
async def mq_publish(data_type: str, backend: str = "log"):
    """通过消息队列发布单个报文。

    backend: log (默认，写入本地文件) | rabbitmq
    """
    from ..formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        SYSTEM_MAP,
    )
    from ..mq_uploader import create_mq_uploader

    config = load_config()
    system_info = config.system_info

    formatter_map = {
        "jbsj": lambda si=system_info: format_jbsj(config.basic_devices, si),
        "absj": lambda si=system_info: format_absj(config.safety_cert_list, si),
        "jztt": lambda si=system_info: format_jztt(config.obsolete_device_list, si),
        "jcjy": lambda si=system_info: format_jcjy(config.device_test_list, si),
    }
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        formatter_map[f"{prefix}jc"] = lambda sk=sys_key, si=system_info: format_system_jc(config.measure_point_list, sk, si)
        formatter_map[f"{prefix}ss"] = lambda sk=sys_key, si=system_info: format_system_ss(config.measure_point_realtime_list, sk, si)
        formatter_map[f"{prefix}yc"] = lambda sk=sys_key, si=system_info: format_system_yc(config.alarm_data_list, sk, si)

    if data_type not in formatter_map:
        raise HTTPException(status_code=400, detail=f"不支持的数据类型: {data_type}")

    content = formatter_map[data_type]()
    uploader = create_mq_uploader(backend)
    await uploader.connect()
    success = await uploader.publish_report(data_type, content)
    await uploader.disconnect()

    if success:
        from ..mq_uploader import QUEUE_MAP
        return {"status": "success", "queue": QUEUE_MAP.get(data_type.lower(), ""), "data_type": data_type}
    return {"status": "error", "message": "发布失败"}


@router.post("/mq/publish-all")
async def mq_publish_all(backend: str = "log"):
    """批量发布所有报文到消息队列。"""
    from ..formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        SYSTEM_MAP,
    )
    from ..mq_uploader import create_mq_uploader

    config = load_config()
    system_info = config.system_info
    uploader = create_mq_uploader(backend)
    await uploader.connect()

    reports = {
        "jbsj": format_jbsj(config.basic_devices, system_info),
        "absj": format_absj(config.safety_cert_list, system_info),
        "jztt": format_jztt(config.obsolete_device_list, system_info),
        "jcjy": format_jcjy(config.device_test_list, system_info),
    }
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        reports[f"{prefix}jc"] = format_system_jc(config.measure_point_list, sys_key, system_info)
        reports[f"{prefix}ss"] = format_system_ss(config.measure_point_realtime_list, sys_key, system_info)
        reports[f"{prefix}yc"] = format_system_yc(config.alarm_data_list, sys_key, system_info)

    results = await uploader.publish_all(reports)
    await uploader.disconnect()

    success_count = sum(1 for v in results.values() if v)
    return {"status": "success", "published": success_count, "total": len(results), "results": results}


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
    from ..server import get_pipeline
    config = load_config()
    device_statuses = get_pipeline().get_device_statuses()
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
    from ..server import get_pipeline
    return get_pipeline().get_device_statuses()


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


@router.delete("/logs")
async def clear_logs():
    """Clear all log entries from app.log."""
    log_file = Path(__file__).parent.parent.parent / "app.log"
    try:
        log_file.write_text("", encoding="utf-8")
        logger.info("Logs cleared")
        return {"status": "success", "message": "日志已清空"}
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        return {"status": "error", "message": str(e)}


# ──────────── 上传配置 API ────────────

@router.get("/upload-config")
async def get_upload_config():
    """获取上传配置"""
    from ..upload_config import load_upload_config
    config = load_upload_config()
    return {"upload_config": config.model_dump()}


@router.post("/upload-config")
async def save_upload_config(config: UploadConfig):
    """保存上传配置并重新加载调度任务"""
    from ..upload_config import save_upload_config as _save
    _save(config)

    # 同步采集启用状态到 DeviceConfig
    await _sync_collect_enabled(config)

    # 重新加载上传调度任务
    from ..upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()

    logger.info("Upload config saved and jobs reloaded")
    return {"status": "success", "upload_config": config.model_dump()}


async def _sync_collect_enabled(config: UploadConfig) -> None:
    """将寄存器的采集启用状态同步到 DeviceConfig.registers"""
    from ..config import load_config, save_config
    from ..models import ModbusRegisterConfig

    app_config = load_config()
    synced_count = 0

    for system_code, devices in config.system_devices.items():
        for dev in devices:
            plc_name = dev.plc_device
            if not plc_name:
                continue

            # 找到对应的 DeviceConfig
            device_cfg = next(
                (d for d in app_config.devices if d.name == plc_name), None
            )
            if device_cfg is None:
                continue

            # 收集需要采集启用的寄存器
            for reg in dev.registers:
                existing_idx = next(
                    (i for i, r in enumerate(device_cfg.registers)
                     if r.name == reg.point_code),
                    None,
                )

                if reg.collect_enabled:
                    # 需要采集：添加或更新
                    new_reg = ModbusRegisterConfig(
                        name=reg.point_code,
                        address=int(reg.register_address) if reg.register_address.isdigit() else 0,
                        count=1,
                        data_type=reg.data_type,
                        scale=1.0,
                        offset=0.0,
                        unit=reg.unit,
                    )
                    if existing_idx is not None:
                        device_cfg.registers[existing_idx] = new_reg
                    else:
                        device_cfg.registers.append(new_reg)
                    synced_count += 1
                else:
                    # 不需要采集：移除
                    if existing_idx is not None:
                        device_cfg.registers.pop(existing_idx)

    save_config(app_config)
    if synced_count > 0:
        logger.info("Synced %d register(s) to DeviceConfig", synced_count)


# 上传任务 API
@router.get("/upload-config/tasks")
async def list_upload_tasks():
    """获取所有上传任务"""
    from ..upload_config import load_upload_config
    config = load_upload_config()
    return {"tasks": [t.model_dump() for t in config.tasks]}


@router.post("/upload-config/tasks")
async def add_upload_task(task: UploadTask):
    """添加上传任务"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    # 检查重复
    if any(t.task_id == task.task_id for t in config.tasks):
        raise HTTPException(status_code=400, detail="任务ID已存在")

    config.tasks.append(task)
    save_upload_config(config)

    # 重新加载调度
    from ..upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()

    return {"status": "success", "task": task.model_dump()}


@router.put("/upload-config/tasks/{task_id}")
async def update_upload_task(task_id: str, task: UploadTask):
    """更新上传任务"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    idx = next((i for i, t in enumerate(config.tasks) if t.task_id == task_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    config.tasks[idx] = task
    save_upload_config(config)

    from ..upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()

    return {"status": "success", "task": task.model_dump()}


@router.delete("/upload-config/tasks/{task_id}")
async def delete_upload_task(task_id: str):
    """删除上传任务"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    original_len = len(config.tasks)
    config.tasks = [t for t in config.tasks if t.task_id != task_id]

    if len(config.tasks) == original_len:
        raise HTTPException(status_code=404, detail="任务不存在")

    save_upload_config(config)

    from ..upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()

    return {"status": "success"}


# 系统设备与寄存器 API
@router.get("/upload-config/systems")
async def list_system_devices():
    """获取所有系统的设备配置"""
    from ..upload_config import load_upload_config
    config = load_upload_config()
    return {"system_devices": config.system_devices}


@router.get("/upload-config/systems/{system_code}")
async def get_system_devices(system_code: str):
    """获取指定系统的设备列表"""
    from ..upload_config import load_upload_config
    config = load_upload_config()
    devices = config.system_devices.get(system_code, [])
    return {"devices": [d.model_dump() for d in devices]}


@router.post("/upload-config/systems/{system_code}/devices")
async def add_system_device(system_code: str, device: DeviceWithRegisters):
    """为系统添加设备"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    if system_code not in config.system_devices:
        config.system_devices[system_code] = []

    # 检查重复
    devices = config.system_devices[system_code]
    if any(d.device_name == device.device_name for d in devices):
        raise HTTPException(status_code=400, detail="设备名称已存在")

    devices.append(device)
    save_upload_config(config)

    return {"status": "success", "device": device.model_dump()}


@router.put("/upload-config/systems/{system_code}/devices/{device_name}")
async def update_system_device(system_code: str, device_name: str, device: DeviceWithRegisters):
    """更新系统设备"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    idx = next((i for i, d in enumerate(devices) if d.device_name == device_name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    devices[idx] = device
    save_upload_config(config)

    return {"status": "success", "device": device.model_dump()}


@router.delete("/upload-config/systems/{system_code}/devices/{device_name}")
async def delete_system_device(system_code: str, device_name: str):
    """删除系统设备"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    original_len = len(devices)
    config.system_devices[system_code] = [
        d for d in devices if d.device_name != device_name
    ]

    if len(config.system_devices[system_code]) == original_len:
        raise HTTPException(status_code=404, detail="设备不存在")

    save_upload_config(config)
    return {"status": "success"}


# 寄存器 API
@router.get("/upload-config/systems/{system_code}/devices/{device_name}/registers")
async def list_registers(system_code: str, device_name: str):
    """获取设备的寄存器列表"""
    from ..upload_config import load_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    return {"registers": [r.model_dump() for r in device.registers]}


@router.post("/upload-config/systems/{system_code}/devices/{device_name}/registers")
async def add_register(system_code: str, device_name: str, register: RegisterPoint):
    """为设备添加寄存器"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 检查重复
    if any(r.point_code == register.point_code for r in device.registers):
        raise HTTPException(status_code=400, detail="测点编码已存在")

    device.registers.append(register)
    save_upload_config(config)

    return {"status": "success", "register": register.model_dump()}


@router.put("/upload-config/systems/{system_code}/devices/{device_name}/registers/{point_code}")
async def update_register(system_code: str, device_name: str, point_code: str, register: RegisterPoint):
    """更新寄存器"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    idx = next((i for i, r in enumerate(device.registers) if r.point_code == point_code), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="测点不存在")

    device.registers[idx] = register
    save_upload_config(config)

    return {"status": "success", "register": register.model_dump()}


@router.delete("/upload-config/systems/{system_code}/devices/{device_name}/registers/{point_code}")
async def delete_register(system_code: str, device_name: str, point_code: str):
    """删除寄存器"""
    from ..upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    original_len = len(device.registers)
    device.registers = [r for r in device.registers if r.point_code != point_code]

    if len(device.registers) == original_len:
        raise HTTPException(status_code=404, detail="测点不存在")

    save_upload_config(config)
    return {"status": "success"}


# 手动触发上传任务
@router.post("/upload-config/execute/{task_id}")
async def execute_upload_task(task_id: str):
    """手动触发执行上传任务"""
    from ..upload_config import load_upload_config
    from ..upload_scheduler import execute_upload_task as _execute

    config = load_upload_config()
    task = next((t for t in config.tasks if t.task_id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    await _execute(task)
    return {"status": "success", "message": f"任务 {task_id} 已执行"}
