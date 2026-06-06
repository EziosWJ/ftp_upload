"""Upload execution module — deep module for the upload task pipeline.

Responsibilities (previously spread across upload_scheduler, formatter, and config):
- Collector lifecycle and reuse (pool of connected collectors)
- Config loading (one place)
- Message formatting (SystemInfo injected, not pulled from global config)
- File writing

Adapters:
- ConfigReader: reads AppConfig and UploadConfig (JsonFileAdapter in prod)
- CollectorPool: manages per-device collector connections
- SystemInfoProvider: provides SystemInfo for message header
"""

import asyncio
import copy
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.collectors import create_collector
from app.collectors.base import BaseCollector, DataPoint
from app.config import load_config as _load_config
from app.models import (
    AppConfig, DeviceConfig, DeviceType, DeviceWithRegisters, ModbusRegisterConfig,
    RegisterPoint, S7AreaConfig, SystemInfo, UploadConfig, UploadTask,
)
from app.upload_config import load_upload_config as _load_upload_config


logger = logging.getLogger(__name__)


class ConfigReader(Protocol):
    """Interface for reading app and upload config."""

    def get_app_config(self) -> AppConfig:
        ...

    def get_upload_config(self) -> UploadConfig:
        ...


class JsonFileConfigReader:
    """Production adapter: reads config from JSON files."""

    def get_app_config(self) -> AppConfig:
        return _load_config()

    def get_upload_config(self) -> UploadConfig:
        return _load_upload_config()


class CollectorPool:
    """Manages connected collectors per device, reusing connections across calls.

    Before: every _collect_from_plc call created a new collector,
            connected, polled, disconnected (TCP handshake per call).

    After: collectors are created once and kept connected per plc_device_name.
           Disconnected collectors are evicted on errors.
    """

    def __init__(self) -> None:
        self._collectors: dict[str, BaseCollector] = {}

    async def collect(
        self,
        plc_device_name: str,
        registers: list[RegisterPoint],
        config_reader: ConfigReader,
    ) -> dict[str, tuple[float, datetime]]:
        """Collect values from a PLC device, reusing connected collector if available."""
        app_config = config_reader.get_app_config()
        device = next((d for d in app_config.devices if d.name == plc_device_name), None)
        if device is None:
            logger.error("PLC device '%s' not found", plc_device_name)
            return {}

        existing = self._collectors.get(plc_device_name)
        if existing is not None and existing.is_connected:
            collector = existing
        else:
            collector = create_collector(self._build_temp_device(device, registers))
            try:
                connected = await collector.connect()
                if not connected:
                    logger.error("Failed to connect to PLC '%s'", plc_device_name)
                    return {}
                self._collectors[plc_device_name] = collector
            except Exception:
                logger.exception("Error connecting to PLC '%s'", plc_device_name)
                return {}

        try:
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
            logger.exception("Error polling PLC '%s', evicting collector", plc_device_name)
            self._collectors.pop(plc_device_name, None)
            try:
                await collector.disconnect()
            except Exception:
                pass
            return {}

    def _build_temp_device(
        self,
        device: DeviceConfig,
        registers: list[RegisterPoint],
    ) -> DeviceConfig:
        """Build a temporary DeviceConfig with only the registers needed for this call."""
        temp_device = copy.deepcopy(device)
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

        return temp_device

    async def disconnect_all(self) -> None:
        """Disconnect and remove all collectors."""
        for name, collector in list(self._collectors.items()):
            try:
                await collector.disconnect()
            except Exception:
                logger.warning("Error disconnecting collector '%s'", name)
        self._collectors.clear()


def _parse_s7_address(address: str, reg: RegisterPoint) -> S7AreaConfig | None:
    """Parse S7 address string into S7AreaConfig.

    Supports:
      - DB1.DBW0   (DB area, word address)
      - DB1.DBX0.0 (DB area, bit address)
      - M10        (M area, byte address)
      - M10.0      (M area, bit address)
      - I0         (input area)
      - Q0         (output area)
    """
    if not address:
        return None

    address = address.strip().upper()

    db_match = re.match(r'DB(\d+)\.DB([XWDL])(\d+)(?:\.(\d+))?', address)
    if db_match:
        db_num = int(db_match.group(1))
        area_type = db_match.group(2)
        byte_addr = int(db_match.group(3))
        bit_off = int(db_match.group(4)) if db_match.group(4) is not None else None
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
            size=2,
            data_type=reg.data_type,
            bit_offset=bit_off,
            scale=1.0,
            offset=0.0,
            unit=reg.unit,
        )

    return None


# ──────────────── SystemInfo provider ────────────────


class ConfigSystemInfoProvider:
    """Reads SystemInfo from AppConfig via ConfigReader."""

    def __init__(self, config_reader: ConfigReader) -> None:
        self._config_reader = config_reader

    def get_system_info(self) -> SystemInfo:
        return self._config_reader.get_app_config().system_info


# ──────────────── File writer ────────────────


class LocalFileWriter:
    """Writes content to a file in the data directory."""

    def __init__(self, config_reader: ConfigReader) -> None:
        self._config_reader = config_reader

    def write(self, file_name: str, content: str) -> Path:
        app_config = self._config_reader.get_app_config()
        project_root = Path(__file__).parent.parent
        data_dir = project_root / app_config.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        file_path = data_dir / file_name
        file_path.write_text(content, encoding="utf-8")
        logger.info("Report file written: %s", file_path)
        return file_path


# ──────────────── UploadExecutor ────────────────


class UploadExecutor:
    """Deep module for upload task execution.

    Encapsulates the full pipeline: collect → format → write.
    Accepts adapters for config reading, collector pooling, system info, and file writing.

    Before (upload_scheduler.py):
        execute_upload_task → load_config() x4 + load_upload_config()
                              → _collect_from_plc (new collector each call)
                              → formatter._header (calls load_config())

    After:
        UploadExecutor.execute(task)
          ├── config_reader.get_app_config()        (once)
          ├── config_reader.get_upload_config()     (once)
          ├── collector_pool.collect()              (reuses connected collectors)
          ├── system_info_provider.get_system_info()(for header, not global call)
          └── file_writer.write()                   (one place to write)
    """

    SYSTEM_MAP = {
        "tfjk": ("30", "主要通风机监控系统", "TF"),
        "psjk": ("31", "主排水监控系统", "PS"),
        "lijk": ("32", "立井提升监控系统", "LJ"),
        "xjjk": ("33", "斜井提升监控系统", "XJ"),
        "kyjk": ("34", "空气压缩机监控系统", "KY"),
        "jcjk": ("35", "绞车监控系统", "JC"),
    }

    def __init__(
        self,
        config_reader: ConfigReader,
        collector_pool: CollectorPool,
        system_info_provider,
        file_writer,
        format_header_fn,
    ) -> None:
        self._config_reader = config_reader
        self._collector_pool = collector_pool
        self._system_info = system_info_provider
        self._file_writer = file_writer
        self._format_header = format_header_fn

    async def execute(self, task: UploadTask) -> None:
        """Execute a single upload task: collect → format → write."""
        logger.info("Executing upload task: %s (%s)", task.task_id, task.data_type)

        try:
            app_config = self._config_reader.get_app_config()
            upload_config = self._config_reader.get_upload_config()

            if task.system_code:
                await self._execute_dynamic(task, app_config, upload_config)
            else:
                await self._execute_static(task, app_config)

            logger.info("Upload task completed: %s", task.task_id)
        except Exception:
            logger.exception("Upload task failed: %s", task.task_id)

    async def _execute_static(self, task: UploadTask, app_config: AppConfig) -> None:
        """Execute static data upload task (JBSJ/ABSJ/JZTT/JCJY)."""
        from app.formatter import format_absj, format_jbsj, format_jcjy, format_jztt

        data_type = task.data_type.upper()
        system_info = self._system_info.get_system_info()

        if data_type == "JBSJ":
            content = format_jbsj(app_config.basic_devices, system_info)
            label = "JBSJ"
        elif data_type == "ABSJ":
            content = format_absj(app_config.safety_cert_list, system_info)
            label = "ABSJ"
        elif data_type == "JZTT":
            content = format_jztt(app_config.obsolete_device_list, system_info)
            label = "JZTT"
        elif data_type == "JCJY":
            content = format_jcjy(app_config.device_test_list, system_info)
            label = "JCJY"
        else:
            logger.error("Unknown static data type: %s", data_type)
            return

        file_name = self._generate_file_name(task, label, "")
        self._file_writer.write(file_name, content)

    async def _execute_dynamic(
        self,
        task: UploadTask,
        app_config: AppConfig,
        upload_config: UploadConfig,
    ) -> None:
        """Execute dynamic data upload task (JC/SS/YC for a monitoring system)."""
        from app.formatter import format_system_jc, format_system_ss, format_system_yc
        from app.models import MeasurePointInfo, MeasurePointRealtimeInfo

        system_code = task.system_code
        suffix = task.data_type.split("_")[-1].upper() if "_" in task.data_type else ""

        devices = upload_config.system_devices.get(system_code, [])
        if not devices:
            logger.warning("No devices configured for system '%s'", system_code)
            return

        system_info = self.SYSTEM_MAP.get(system_code)
        if not system_info:
            logger.error("Unknown system code: %s", system_code)
            return

        code, name, short = system_info
        system_info_obj = self._system_info.get_system_info()

        if suffix == "JC":
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
            content = format_system_jc(all_points, system_code, system_info_obj)

        elif suffix == "SS":
            all_points = []
            for dev in devices:
                enabled_regs = [r for r in dev.registers if r.report_enabled]
                if not enabled_regs:
                    continue
                values = await self._collector_pool.collect(
                    dev.plc_device, enabled_regs, self._config_reader
                )
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
            content = format_system_ss(all_points, system_code, system_info_obj)

        elif suffix == "YC":
            alarm_points = [
                a for a in app_config.alarm_data_list
                if any(
                    r.point_code == a.point_code
                    for dev in devices
                    for r in dev.registers
                    if r.report_enabled
                )
            ]
            content = format_system_yc(alarm_points, system_code, system_info_obj)

        else:
            logger.error("Unknown dynamic data suffix: %s", suffix)
            return

        file_name = self._generate_file_name(task, task.data_type.upper(), name)
        self._file_writer.write(file_name, content)

    def _generate_file_name(self, task: UploadTask, data_type_label: str, system_name: str = "") -> str:
        """Generate file name from task config."""
        now = datetime.now()
        mine_code = self._system_info.get_system_info().mine_code or "000000000000"

        if task.file_name_template:
            name = task.file_name_template.format(
                mine_code=mine_code,
                type=data_type_label,
                timestamp=now.strftime("%Y%m%d%H%M%S"),
                system_name=system_name,
                date=now.strftime("%Y%m%d"),
            )
            return f"{name}.txt"

        parts = []
        for field in task.file_name_fields:
            if field == "type":
                parts.append(data_type_label)
            elif field == "system_name":
                if system_name:
                    parts.append(system_name)
            elif field == "mine_code":
                parts.append(mine_code)
            elif field == "timestamp":
                parts.append(now.strftime("%Y%m%d%H%M%S"))
            elif field == "date":
                parts.append(now.strftime("%Y%m%d"))

        return f"{'_'.join(parts)}.txt"

    async def shutdown(self) -> None:
        """Disconnect all collectors managed by this executor."""
        await self._collector_pool.disconnect_all()