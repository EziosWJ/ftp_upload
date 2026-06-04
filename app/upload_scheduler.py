"""上传任务调度器 — 管理定时报文生成任务

职责：
- 根据 UploadConfig.tasks 注册/注销 APScheduler 定时任务
- 任务触发时执行：采集数据 → 格式化报文 → 写入本地文件
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.collectors import create_collector
from app.collectors.base import BaseCollector, DataPoint
from app.config import load_config
from app.formatter import (
    SYSTEM_MAP, format_absj, format_jbsj, format_jcjy, format_jztt,
    format_system_jc, format_system_ss, format_system_yc,
    write_report_file,
)
from app.models import (
    AlarmData, DeviceConfig, DeviceWithRegisters, MeasurePointInfo,
    MeasurePointRealtimeInfo, RegisterPoint, ScheduleType, UploadTask,
)
from app.upload_config import load_upload_config

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


# ──────────────── 文件名生成 ────────────────

FILE_NAME_FIELD_MAP = {
    "mine_code": lambda cfg: cfg.system_info.mine_code or "000000000000",
    "type": lambda _: "",  # 由调用方传入
    "timestamp": lambda _: datetime.now().strftime("%Y%m%d%H%M%S"),
    "system_name": lambda _: "",  # 由调用方传入
    "date": lambda _: datetime.now().strftime("%Y%m%d"),
}


def generate_file_name(task: UploadTask, data_type_label: str, system_name: str = "") -> str:
    """根据任务配置生成文件名"""
    config = load_config()

    # 优先使用自定义模板
    if task.file_name_template:
        name = task.file_name_template.format(
            mine_code=config.system_info.mine_code or "000000000000",
            type=data_type_label,
            timestamp=datetime.now().strftime("%Y%m%d%H%M%S"),
            system_name=system_name,
            date=datetime.now().strftime("%Y%m%d"),
        )
        return f"{name}.txt"

    # 使用字段列表拼接
    parts = []
    for field in task.file_name_fields:
        if field == "type":
            parts.append(data_type_label)
        elif field == "system_name":
            if system_name:
                parts.append(system_name)
        else:
            resolver = FILE_NAME_FIELD_MAP.get(field)
            if resolver:
                val = resolver(config)
                if val:
                    parts.append(val)

    return f"{'_'.join(parts)}.txt"


# ──────────────── 数据采集 ────────────────

async def _collect_from_plc(
    plc_device_name: str,
    registers: list[RegisterPoint],
) -> dict[str, tuple[float, datetime]]:
    """从 PLC 采集指定寄存器的值，返回 {point_code: (value, timestamp)}"""
    import copy

    config = load_config()
    device = next((d for d in config.devices if d.name == plc_device_name), None)
    if device is None:
        logger.error("PLC device '%s' not found", plc_device_name)
        return {}

    # 深拷贝设备配置，避免污染原始配置
    temp_device = copy.deepcopy(device)

    # 根据设备类型构造临时寄存器列表
    from .models import DeviceType, ModbusRegisterConfig, S7AreaConfig

    if device.device_type == DeviceType.MODBUS_TCP:
        temp_registers = []
        for reg in registers:
            try:
                addr = int(reg.register_address)
            except (ValueError, TypeError):
                logger.warning("Invalid Modbus address '%s' for '%s', skipping",
                               reg.register_address, reg.point_code)
                continue
            temp_registers.append(ModbusRegisterConfig(
                name=reg.point_code,
                address=addr,
                count=1,
                data_type=reg.data_type,
                scale=1.0,
                offset=0.0,
                unit=reg.unit,
            ))
        temp_device.registers = temp_registers

    elif device.device_type == DeviceType.S7:
        temp_areas = []
        for reg in registers:
            area_cfg = _parse_s7_address(reg.register_address, reg)
            if area_cfg:
                temp_areas.append(area_cfg)
            else:
                logger.warning("Invalid S7 address '%s' for '%s', skipping",
                               reg.register_address, reg.point_code)
        temp_device.areas = temp_areas

    # 使用临时配置创建采集器
    collector = create_collector(temp_device)
    try:
        connected = await collector.connect()
        if not connected:
            logger.error("Failed to connect to PLC '%s'", plc_device_name)
            return {}

        datapoints = await collector.poll()
        result = {}
        for dp in datapoints:
            if dp.quality == "good":
                result[dp.name] = (dp.value, dp.timestamp)
            else:
                for reg in registers:
                    if reg.point_code == dp.name:
                        result[dp.name] = (reg.fault_default, datetime.now())
                        break
        return result
    except Exception:
        logger.exception("Error collecting from PLC '%s'", plc_device_name)
        return {}
    finally:
        await collector.disconnect()


def _parse_s7_address(address: str, reg: RegisterPoint) -> S7AreaConfig | None:
    """解析 S7 地址字符串，返回 S7AreaConfig

    支持格式：
      - DB1.DBW0   (DB 区域，字地址)
      - DB1.DBX0.0 (DB 区域，位地址)
      - M10        (M 区域，字节地址)
      - M10.0      (M 区域，位地址)
      - I0         (输入区域)
      - Q0         (输出区域)
    """
    import re
    from .models import S7AreaConfig, DataType

    if not address:
        return None

    address = address.strip().upper()

    # DB 格式：DB1.DBW0 或 DB1.DBD0 或 DB1.DBX0.0
    db_match = re.match(r'DB(\d+)\.DB([XWDL])(\d+)(?:\.(\d+))?', address)
    if db_match:
        db_num = int(db_match.group(1))
        area_type = db_match.group(2)
        byte_addr = int(db_match.group(3))
        bit_off = int(db_match.group(4)) if db_match.group(4) is not None else None

        # 根据类型确定大小
        size_map = {'X': 1, 'W': 2, 'D': 4, 'L': 8}
        size = size_map.get(area_type, 2)

        return S7AreaConfig(
            name=reg.point_code,
            area='DB',
            db_number=db_num,
            start=byte_addr,
            size=size,
            data_type=reg.data_type,
            bit_offset=bit_off,
            scale=1.0,
            offset=0.0,
            unit=reg.unit,
        )

    # M/I/Q 格式：M10 或 M10.0 或 I0.0
    io_match = re.match(r'([MIQ])(\d+)(?:\.(\d+))?', address)
    if io_match:
        area_letter = io_match.group(1)
        byte_addr = int(io_match.group(2))
        bit_off = int(io_match.group(3)) if io_match.group(3) is not None else None

        area_map = {'M': 'M', 'I': 'I', 'Q': 'Q'}

        return S7AreaConfig(
            name=reg.point_code,
            area=area_map[area_letter],
            db_number=0,
            start=byte_addr,
            size=2,  # 默认读 2 字节
            data_type=reg.data_type,
            bit_offset=bit_off,
            scale=1.0,
            offset=0.0,
            unit=reg.unit,
        )

    return None


# ──────────────── 报文生成执行 ────────────────

async def execute_upload_task(task: UploadTask) -> None:
    """执行单个上传任务：采集数据 → 格式化 → 写文件"""
    logger.info("Executing upload task: %s (%s)", task.task_id, task.data_type)

    try:
        config = load_config()
        upload_cfg = load_upload_config()

        if task.system_code:
            # 动态数据：从 PLC 采集
            await _execute_dynamic_task(task, config, upload_cfg)
        else:
            # 静态数据：从 AppConfig 读取
            await _execute_static_task(task, config)

        logger.info("Upload task completed: %s", task.task_id)
    except Exception:
        logger.exception("Upload task failed: %s", task.task_id)


async def _execute_static_task(task: UploadTask, config) -> None:
    """执行静态数据上传任务"""
    data_type = task.data_type.upper()

    if data_type == "JBSJ":
        content = format_jbsj(config.basic_devices)
        label = "JBSJ"
    elif data_type == "ABSJ":
        content = format_absj(config.safety_cert_list)
        label = "ABSJ"
    elif data_type == "JZTT":
        content = format_jztt(config.obsolete_device_list)
        label = "JZTT"
    elif data_type == "JCJY":
        content = format_jcjy(config.device_test_list)
        label = "JCJY"
    else:
        logger.error("Unknown static data type: %s", data_type)
        return

    file_name = generate_file_name(task, label)
    _write_file(file_name, content)


async def _execute_dynamic_task(task: UploadTask, config, upload_cfg) -> None:
    """执行动态数据上传任务"""
    system_code = task.system_code
    suffix = task.data_type.split("_")[-1].upper() if "_" in task.data_type else ""

    devices = upload_cfg.system_devices.get(system_code, [])
    if not devices:
        logger.warning("No devices configured for system '%s'", system_code)
        return

    system_info = SYSTEM_MAP.get(system_code)
    if not system_info:
        logger.error("Unknown system code: %s", system_code)
        return

    code, name, short = system_info

    if suffix == "JC":
        # 测点基础信息 — 从配置中读取，不需要 PLC 采集
        all_points = []
        for dev in devices:
            for reg in dev.registers:
                if reg.report_enabled:
                    all_points.append(MeasurePointInfo(
                        point_code=reg.point_code,
                        point_type_code=reg.point_type_code,
                        point_type_name=reg.point_name,
                        device_code=dev.device_code,
                        unit=reg.unit,
                        range_upper=reg.range_upper,
                        range_lower=reg.range_lower,
                        alarm_upper=reg.alarm_upper,
                        alarm_lower=reg.alarm_lower,
                    ))
        content = format_system_jc(all_points, system_code)

    elif suffix == "SS":
        # 实时数据 — 需要 PLC 采集
        all_points = []
        for dev in devices:
            enabled_regs = [r for r in dev.registers if r.report_enabled]
            if not enabled_regs:
                continue
            values = await _collect_from_plc(dev.plc_device, enabled_regs)
            for reg in enabled_regs:
                if reg.point_code in values:
                    val, ts = values[reg.point_code]
                    status = "good"
                else:
                    val = reg.fault_default
                    ts = datetime.now()
                    status = "fault"
                all_points.append(MeasurePointRealtimeInfo(
                    point_code=reg.point_code,
                    point_type_code=reg.point_type_code,
                    point_type_name=reg.point_name,
                    device_code=dev.device_code,
                    point_value=val,
                    point_unit=reg.unit,
                    point_status=status,
                    data_time=ts.strftime("%Y-%m-%d %H:%M:%S"),
                ))
        content = format_system_ss(all_points, system_code)

    elif suffix == "YC":
        # 异常数据 — 从现有 AppConfig.alarm_data_list 中筛选
        alarm_points = [
            a for a in config.alarm_data_list
            if any(
                r.point_code == a.point_code
                for dev in devices
                for r in dev.registers
                if r.report_enabled
            )
        ]
        content = format_system_yc(alarm_points, system_code)

    else:
        logger.error("Unknown dynamic data suffix: %s", suffix)
        return

    file_name = generate_file_name(task, task.data_type.upper(), name)
    _write_file(file_name, content)


def _write_file(file_name: str, content: str) -> None:
    """写入文件到 data/ 目录"""
    config = load_config()
    project_root = Path(__file__).parent.parent
    data_dir = project_root / config.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    file_path = data_dir / file_name
    file_path.write_text(content, encoding="utf-8")
    logger.info("Report file written: %s", file_path)


# ──────────────── 调度器管理 ────────────────

def _build_trigger(task: UploadTask):
    """根据任务配置构建 APScheduler trigger"""
    if task.schedule_type == ScheduleType.INTERVAL_MINUTES:
        return IntervalTrigger(minutes=max(1, task.interval_value))
    elif task.schedule_type == ScheduleType.INTERVAL_HOURS:
        return IntervalTrigger(hours=max(1, task.interval_value))
    elif task.schedule_type == ScheduleType.DAILY:
        return CronTrigger(hour=task.hour, minute=task.minute)
    elif task.schedule_type == ScheduleType.WEEKLY:
        return CronTrigger(
            day_of_week=task.weekday if task.weekday is not None else 0,
            hour=task.hour,
            minute=task.minute,
        )
    else:
        logger.error("Unknown schedule type: %s", task.schedule_type)
        return None


async def reload_upload_jobs() -> None:
    """重新加载所有上传任务"""
    if _scheduler is None:
        logger.error("Upload scheduler not running")
        return

    upload_cfg = load_upload_config()

    # 移除所有现有任务
    existing_jobs = [j.id for j in _scheduler.get_jobs() if j.id.startswith("upload_")]
    for job_id in existing_jobs:
        _scheduler.remove_job(job_id)

    # 注册新任务
    count = 0
    for task in upload_cfg.tasks:
        if not task.enabled:
            continue

        trigger = _build_trigger(task)
        if trigger is None:
            continue

        job_id = f"upload_{task.task_id}"
        _scheduler.add_job(
            execute_upload_task,
            trigger=trigger,
            args=[task],
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )
        count += 1
        logger.info("Scheduled upload job: %s", task.task_id)

    logger.info("Reloaded %d upload job(s)", count)


async def start_upload_scheduler() -> None:
    """启动上传调度器"""
    global _scheduler

    if _scheduler is not None:
        logger.warning("Upload scheduler already running")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    logger.info("Upload scheduler started")

    await reload_upload_jobs()


async def stop_upload_scheduler() -> None:
    """停止上传调度器"""
    global _scheduler

    if _scheduler is None:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("Upload scheduler stopped")
