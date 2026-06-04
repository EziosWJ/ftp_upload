"""Siemens S7 PLC collector using python-snap7."""

import asyncio
import struct
from typing import Any

import snap7
import snap7.util
from snap7.type import Area

from app.collectors.base import BaseCollector, DataPoint
from app.models import DataType, DeviceConfig, S7AreaConfig


# Map string area codes from config to snap7 Area enum
_AREA_MAP: dict[str, Area] = {
    "DB": Area.DB,
    "I": Area.PE,   # Process Input
    "Q": Area.PA,   # Process Output
    "M": Area.MK,   # Merker / Marker
}


class S7Collector(BaseCollector):
    """Collector for Siemens S7 PLCs over ISO-on-TCP (port 102).

    Wraps the synchronous ``snap7.client.Client`` with ``asyncio.to_thread``
    so every I/O call is non-blocking.
    """

    def __init__(self, device_config: DeviceConfig) -> None:
        super().__init__(device_config)
        self._client: snap7.client.Client | None = None
        # Pre-resolve area configs for fast iteration during poll
        self._areas: list[S7AreaConfig] = device_config.areas

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Establish connection to the S7 PLC."""
        if self._connected and self._client is not None:
            return True

        try:
            client = snap7.client.Client()
            cfg = self.device_config
            self.logger.info(
                "Connecting to S7 PLC %s:%d (rack=%d, slot=%d)",
                cfg.host, cfg.port, cfg.rack, cfg.slot,
            )
            await asyncio.to_thread(
                client.connect, cfg.host, cfg.rack, cfg.slot, cfg.port
            )
            self._client = client
            self._connected = True
            self.logger.info("Connected to S7 PLC %s", cfg.name)
            return True
        except Exception:
            self.logger.exception("Failed to connect to S7 PLC %s", cfg.name)
            self._client = None
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the S7 PLC."""
        if self._client is not None:
            try:
                await asyncio.to_thread(self._client.disconnect)
            except Exception:
                self.logger.exception(
                    "Error disconnecting from S7 PLC %s", self.device_name
                )
            finally:
                self._client = None
                self._connected = False
                self.logger.info("Disconnected from S7 PLC %s", self.device_name)

    async def test_connection(self) -> bool:
        """Check whether the PLC is reachable by reading a small chunk.

        For DB areas the smallest meaningful read is attempted; otherwise
        a single-byte read from the M (Merker) area is used as a ping.
        """
        if not self._connected or self._client is None:
            return False

        try:
            # Try to get CPU info — lightweight, always available when connected
            await asyncio.to_thread(self._client.get_cpu_info)
            return True
        except Exception:
            self.logger.warning(
                "Connection test failed for S7 PLC %s", self.device_name
            )
            self._connected = False
            return False

    async def test_with_logs(self) -> tuple[bool, list[str]]:
        """Test connection with detailed logging.

        Returns (success, log_lines).
        """
        logs: list[str] = []
        cfg = self.device_config

        logs.append(f"=== S7 PLC 连接测试: {self.device_name} ===")
        logs.append(f"  目标: {cfg.host}:{cfg.port}")
        logs.append(f"  Rack={cfg.rack}  Slot={cfg.slot}")

        # Disconnect first to force a fresh connection
        await self.disconnect()

        connected = await self.connect()
        if not connected:
            logs.append("  ✗ TCP/ISO 连接失败")
            return False, logs

        logs.append("  ✓ TCP/ISO 连接成功")

        try:
            cpu_info = await asyncio.to_thread(self._client.get_cpu_info)
            logs.append(f"  ✓ CPU 信息: {cpu_info}")
        except Exception as e:
            logs.append(f"  ✗ 获取 CPU 信息失败: {e}")

        # Try reading configured areas
        for area_cfg in self._areas:
            try:
                area = self._resolve_area(area_cfg.area)
                logs.append(f"  → 读取区域: {area_cfg.name} ({area_cfg.area}"
                            f" DB={area_cfg.db_number}"
                            f" Start={area_cfg.start}"
                            f" Size={area_cfg.size})")
                data = await asyncio.to_thread(
                    self._client.read_area, area,
                    area_cfg.db_number, area_cfg.start, area_cfg.size,
                )
                raw = self._decode_value(data, area_cfg)
                value = self._apply_scale_offset(raw, area_cfg.scale, area_cfg.offset)
                unit = f" {area_cfg.unit}" if area_cfg.unit else ""
                logs.append(f"    ✓ {area_cfg.name} = {value}{unit}")
            except Exception as e:
                logs.append(f"    ✗ {area_cfg.name} 读取失败: {e}")

        ok = await self.test_connection()
        if ok:
            logs.append("  ✓ S7 PLC 通信正常")
        else:
            logs.append("  ✗ S7 PLC 通信失败")

        await self.disconnect()
        return ok, logs

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def poll(self) -> list[DataPoint]:
        """Read all configured areas and return a list of data points."""
        if not self._connected or self._client is None:
            self.logger.warning("Cannot poll: not connected to %s", self.device_name)
            return []

        points: list[DataPoint] = []
        for area_cfg in self._areas:
            try:
                value = await self._read_area(area_cfg)
                if value is not None:
                    points.append(
                        DataPoint(
                            name=area_cfg.name,
                            value=value,
                            unit=area_cfg.unit,
                            quality="good",
                        )
                    )
            except Exception:
                self.logger.exception(
                    "Error reading area '%s' from %s",
                    area_cfg.name, self.device_name,
                )
                points.append(
                    DataPoint(
                        name=area_cfg.name,
                        value=None,
                        unit=area_cfg.unit,
                        quality="bad",
                    )
                )
        return points

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    async def write_value(self, name: str, value: Any) -> bool:
        """Write *value* to the area whose ``name`` matches *name*.

        Only areas with ``writable=True`` can be written to.
        """
        if not self._connected or self._client is None:
            self.logger.warning("Cannot write: not connected to %s", self.device_name)
            return False

        area_cfg = self._find_area(name)
        if area_cfg is None:
            self.logger.error("Area '%s' not found in %s", name, self.device_name)
            return False

        if not area_cfg.writable:
            self.logger.error("Area '%s' is not writable on %s", name, self.device_name)
            return False

        try:
            await self._write_area(area_cfg, value)
            self.logger.info("Wrote %s=%s to %s/%s", name, value, self.device_name, name)
            return True
        except Exception:
            self.logger.exception(
                "Error writing '%s' to %s", name, self.device_name
            )
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_area(self, name: str) -> S7AreaConfig | None:
        for a in self._areas:
            if a.name == name:
                return a
        return None

    @staticmethod
    def _resolve_area(area_str: str) -> Area:
        """Translate a config area string to the snap7 ``Area`` enum."""
        area = _AREA_MAP.get(area_str.upper())
        if area is None:
            raise ValueError(
                f"Unknown S7 area '{area_str}'. Must be one of: {list(_AREA_MAP)}"
            )
        return area

    async def _read_area(self, cfg: S7AreaConfig) -> Any:
        """Read a single area from the PLC and return the converted value."""
        area = self._resolve_area(cfg.area)
        data: bytearray = await asyncio.to_thread(
            self._client.read_area,  # type: ignore[union-attr]
            area,
            cfg.db_number,
            cfg.start,
            cfg.size,
        )
        raw = self._decode_value(data, cfg)
        return self._apply_scale_offset(raw, cfg.scale, cfg.offset)

    async def _write_area(self, cfg: S7AreaConfig, value: Any) -> None:
        """Encode *value* and write it to the PLC."""
        area = self._resolve_area(cfg.area)

        # Reverse scale/offset: raw = (value - offset) / scale
        if cfg.scale != 0:
            raw_value = (float(value) - cfg.offset) / cfg.scale
        else:
            raw_value = float(value)

        data = self._encode_value(raw_value, cfg)
        await asyncio.to_thread(
            self._client.write_area,  # type: ignore[union-attr]
            area,
            cfg.db_number,
            cfg.start,
            data,
        )

    # ------------------------------------------------------------------
    # Decoding (bytearray → Python value)
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_value(data: bytearray, cfg: S7AreaConfig) -> Any:
        """Extract a typed value from the raw bytes read from the PLC."""
        dtype = cfg.data_type

        if dtype == DataType.BOOL:
            bit = cfg.bit_offset if cfg.bit_offset is not None else 0
            return snap7.util.get_bool(data, 0, bit)

        if dtype == DataType.INT16:
            return snap7.util.get_int(data, 0)

        if dtype == DataType.UINT16:
            return snap7.util.get_uint(data, 0)

        if dtype == DataType.INT32:
            return snap7.util.get_dint(data, 0)

        if dtype == DataType.UINT32:
            return snap7.util.get_udint(data, 0)

        if dtype == DataType.FLOAT32:
            return snap7.util.get_real(data, 0)

        if dtype == DataType.FLOAT64:
            # snap7 has no get_lreal util in 3.0.0; use struct (big-endian for S7)
            return struct.unpack_from(">d", data, 0)[0]

        if dtype == DataType.STRING:
            # S7 STRING: 前2字节是头部（最大长度、实际长度），后面是数据
            if len(data) >= 2:
                actual_len = data[1]
                return data[2:2 + actual_len].decode('ascii', errors='replace')
            return data.decode('ascii', errors='replace')

        raise ValueError(f"Unsupported data type for decoding: {dtype}")

    # ------------------------------------------------------------------
    # Encoding (Python value → bytearray)
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_value(value: Any, cfg: S7AreaConfig) -> bytearray:
        """Encode a Python value into a bytearray suitable for write_area."""
        dtype = cfg.data_type

        if dtype == DataType.BOOL:
            # We need a buffer to modify; size must cover the target byte.
            buf = bytearray(cfg.size)
            bit = cfg.bit_offset if cfg.bit_offset is not None else 0
            snap7.util.set_bool(buf, 0, bit, bool(value))
            return buf

        if dtype == DataType.INT16:
            buf = bytearray(2)
            snap7.util.set_int(buf, 0, int(value))
            return buf

        if dtype == DataType.UINT16:
            buf = bytearray(2)
            snap7.util.set_uint(buf, 0, int(value))
            return buf

        if dtype == DataType.INT32:
            buf = bytearray(4)
            snap7.util.set_dint(buf, 0, int(value))
            return buf

        if dtype == DataType.UINT32:
            buf = bytearray(4)
            snap7.util.set_udint(buf, 0, int(value))
            return buf

        if dtype == DataType.FLOAT32:
            buf = bytearray(4)
            snap7.util.set_real(buf, 0, float(value))
            return buf

        if dtype == DataType.FLOAT64:
            buf = bytearray(8)
            struct.pack_into(">d", buf, 0, float(value))
            return buf

        if dtype == DataType.STRING:
            # S7 STRING: 前2字节头部 + 数据
            s = str(value).encode('ascii', errors='replace')
            max_len = max(len(s), cfg.size - 2) if cfg.size > 2 else len(s)
            buf = bytearray(max_len + 2)
            buf[0] = max_len  # 最大长度
            buf[1] = len(s)   # 实际长度
            buf[2:2 + len(s)] = s
            return buf

        raise ValueError(f"Unsupported data type for encoding: {dtype}")

    # ------------------------------------------------------------------
    # Scale / offset
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_scale_offset(value: Any, scale: float, offset: float) -> Any:
        """Apply ``value * scale + offset`` when the result would differ."""
        if scale == 1.0 and offset == 0.0:
            return value
        return float(value) * scale + offset
