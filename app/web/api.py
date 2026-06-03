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
    ObsoleteDeviceInfo, DeviceTestInfo, AlarmData
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

    formatter_map = {
        "jbsj": lambda: format_jbsj(config.basic_devices),
        "absj": lambda: format_absj(config.safety_cert_list),
        "jztt": lambda: format_jztt(config.obsolete_device_list),
        "jcjy": lambda: format_jcjy(config.device_test_list),
    }

    # 六大系统 JC/SS/YC
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        formatter_map[f"{prefix}jc"] = lambda sk=sys_key: format_system_jc(
            config.measure_point_list, sk
        )
        formatter_map[f"{prefix}ss"] = lambda sk=sys_key: format_system_ss(
            config.measure_point_realtime_list, sk
        )
        formatter_map[f"{prefix}yc"] = lambda sk=sys_key: format_system_yc(
            config.alarm_data_list, sk
        )

    if data_type not in formatter_map:
        raise HTTPException(status_code=400, detail=f"不支持的数据类型: {data_type}")

    content = formatter_map[data_type]()
    file_path = write_report_file(data_type.upper(), content, config.data_dir)

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
    files = []

    # 静态数据
    static_generators = [
        ("JBSJ", lambda: format_jbsj(config.basic_devices)),
        ("ABSJ", lambda: format_absj(config.safety_cert_list)),
        ("JZTT", lambda: format_jztt(config.obsolete_device_list)),
        ("JCJY", lambda: format_jcjy(config.device_test_list)),
    ]
    for name, gen in static_generators:
        content = gen()
        fp = write_report_file(name, content, config.data_dir)
        files.append(str(fp))

    # 六大系统动态数据
    for sys_key, (code, sys_name, short) in SYSTEM_MAP.items():
        for suffix, gen in [
            ("JC", lambda sk=sys_key: format_system_jc(config.measure_point_list, sk)),
            ("SS", lambda sk=sys_key: format_system_ss(config.measure_point_realtime_list, sk)),
            ("YC", lambda sk=sys_key: format_system_yc(config.alarm_data_list, sk)),
        ]:
            content = gen()
            fp = write_report_file(f"{short}{suffix}", content, config.data_dir)
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

    formatter_map = {
        "jbsj": lambda: format_jbsj(config.basic_devices),
        "absj": lambda: format_absj(config.safety_cert_list),
        "jztt": lambda: format_jztt(config.obsolete_device_list),
        "jcjy": lambda: format_jcjy(config.device_test_list),
    }
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        formatter_map[f"{prefix}jc"] = lambda sk=sys_key: format_system_jc(config.measure_point_list, sk)
        formatter_map[f"{prefix}ss"] = lambda sk=sys_key: format_system_ss(config.measure_point_realtime_list, sk)
        formatter_map[f"{prefix}yc"] = lambda sk=sys_key: format_system_yc(config.alarm_data_list, sk)

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
    uploader = create_mq_uploader(backend)
    await uploader.connect()

    reports = {
        "jbsj": format_jbsj(config.basic_devices),
        "absj": format_absj(config.safety_cert_list),
        "jztt": format_jztt(config.obsolete_device_list),
        "jcjy": format_jcjy(config.device_test_list),
    }
    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        reports[f"{prefix}jc"] = format_system_jc(config.measure_point_list, sys_key)
        reports[f"{prefix}ss"] = format_system_ss(config.measure_point_realtime_list, sys_key)
        reports[f"{prefix}yc"] = format_system_yc(config.alarm_data_list, sys_key)

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
