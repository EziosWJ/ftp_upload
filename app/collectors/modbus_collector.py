"""Modbus TCP collector for reading holding and input registers."""

import logging
import struct
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ModbusPDU

from app.collectors.base import BaseCollector, DataPoint
from app.models import DataType, DeviceConfig, ModbusRegisterConfig

logger = logging.getLogger(__name__)


# Data type -> (struct format, number of registers)
_DATA_TYPE_MAP: dict[DataType, tuple[str, int]] = {
    DataType.INT16:   (">h",  1),
    DataType.UINT16:  (">H",  1),
    DataType.INT32:   (">i",  2),
    DataType.UINT32:  (">I",  2),
    DataType.FLOAT32: (">f",  2),
    DataType.FLOAT64: (">d",  4),
}


def _make_trace_callbacks() -> tuple:
    """Create a fresh log list and return (logs, trace_packet, trace_pdu).

    Each call produces an independent set of callbacks so concurrent
    test_connection calls don't corrupt each other's logs.
    """
    logs: list[str] = []

    def trace_packet(is_request: bool, data: bytes) -> bytes:
        direction = "TX →" if is_request else "RX ←"
        logs.append(
            f"  {direction} Packet ({len(data)} bytes): {data.hex(' ')}"
        )
        return data

    def trace_pdu(is_request: bool, pdu: ModbusPDU) -> ModbusPDU:
        direction = "TX →" if is_request else "RX ←"
        fc = pdu.function_code if hasattr(pdu, 'function_code') else '?'
        if is_request:
            addr = getattr(pdu, 'address', '?')
            count = getattr(pdu, 'count', '?')
            logs.append(
                f"  {direction} Request  FC={fc}  Addr={addr}  Count={count}"
            )
        else:
            if hasattr(pdu, 'registers'):
                logs.append(
                    f"  {direction} Response FC={fc}  Registers={pdu.registers}"
                )
            elif hasattr(pdu, 'bits'):
                logs.append(
                    f"  {direction} Response FC={fc}  Bits={pdu.bits}"
                )
            elif hasattr(pdu, 'exception_code'):
                logs.append(
                    f"  {direction} Response FC={fc}  Exception={pdu.exception_code}"
                )
            else:
                logs.append(f"  {direction} Response FC={fc}  {pdu}")
        return pdu

    return logs, trace_packet, trace_pdu


class ModbusCollector(BaseCollector):
    """Async Modbus TCP collector.

    Reads holding registers (FC 3) and input registers (FC 4),
    converts raw register words to typed values, applies scale/offset,
    and returns ``DataPoint`` objects.
    """

    def __init__(self, device_config: DeviceConfig) -> None:
        super().__init__(device_config)
        self._client: AsyncModbusTcpClient | None = None
        self._register_map: dict[str, ModbusRegisterConfig] = {
            reg.name: reg for reg in self.device_config.registers
        }

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self, trace_packet=None, trace_pdu=None) -> bool:
        """Open an async TCP connection to the Modbus device."""
        if self._connected and self._client is not None:
            return True

        try:
            kwargs: dict[str, Any] = {
                "host": self.device_config.host,
                "port": self.device_config.port,
                "retries": 1,
                "timeout": 3,
            }
            if trace_packet:
                kwargs["trace_packet"] = trace_packet
            if trace_pdu:
                kwargs["trace_pdu"] = trace_pdu
            self._client = AsyncModbusTcpClient(**kwargs)
            await self._client.connect()
            self._connected = self._client.connected
            if self._connected:
                self.logger.info(
                    "Connected to %s at %s:%s",
                    self.device_name,
                    self.device_config.host,
                    self.device_config.port,
                )
            else:
                self.logger.error(
                    "Failed to connect to %s at %s:%s",
                    self.device_name,
                    self.device_config.host,
                    self.device_config.port,
                )
            return self._connected
        except (OSError, ModbusException) as exc:
            self.logger.error(
                "Connection error for %s: %s", self.device_name, exc
            )
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close the Modbus TCP connection."""
        if self._client is not None:
            self._client.close()
            self.logger.info("Disconnected from %s", self.device_name)
        self._client = None
        self._connected = False

    async def test_connection(self) -> bool:
        """Verify the device is reachable by reading all configured registers.

        Returns True if any register reads successfully.
        """
        if self._client is None or not self._connected:
            connected = await self.connect()
            if not connected:
                return False

        if self.device_config.registers:
            # Test by reading the first configured register
            reg = self.device_config.registers[0]
            try:
                result = await self._client.read_holding_registers(
                    address=reg.address,
                    count=max(reg.count, 1),
                    device_id=self.device_config.slave_id,
                )
                return not result.isError()
            except (ModbusException, OSError) as exc:
                self.logger.warning(
                    "Connection test failed for %s: %s", self.device_name, exc
                )
                self._connected = False
                return False
        else:
            # No registers configured, just try a basic read
            try:
                result = await self._client.read_holding_registers(
                    address=0, count=1,
                    device_id=self.device_config.slave_id,
                )
                return not result.isError()
            except (ModbusException, OSError) as exc:
                self.logger.warning(
                    "Connection test failed for %s: %s", self.device_name, exc
                )
                self._connected = False
                return False

    async def test_with_logs(self) -> tuple[bool, list[str]]:
        """Test connection with protocol logging enabled.

        Returns (success, protocol_log_lines).
        """
        logs, trace_packet, trace_pdu = _make_trace_callbacks()

        logs.append(f"=== Modbus TCP 连接测试: {self.device_name} ===")
        logs.append(f"  目标: {self.device_config.host}:{self.device_config.port}")
        logs.append(f"  从站ID: {self.device_config.slave_id}")

        # Disconnect first to force a new connection with tracing
        await self.disconnect()

        connected = await self.connect(trace_packet=trace_packet, trace_pdu=trace_pdu)
        if not connected:
            logs.append("  ✗ TCP 连接失败")
            return False, logs

        logs.append("  ✓ TCP 连接成功")

        ok = await self.test_connection()
        if ok:
            logs.append("  ✓ Modbus 通信正常")
        else:
            logs.append("  ✗ Modbus 通信失败")

        await self.disconnect()
        return ok, logs

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def poll(self) -> list[DataPoint]:
        """Read all configured registers and return a list of data points."""
        if self._client is None or not self._connected:
            self.logger.warning("Cannot poll %s: not connected", self.device_name)
            return []

        results: list[DataPoint] = []
        slave = self.device_config.slave_id

        for reg in self.device_config.registers:
            try:
                datapoint = await self._read_register(reg, slave)
                results.append(datapoint)
            except Exception as exc:  # noqa: BLE001
                self.logger.error(
                    "Error reading register '%s' (addr %d) on %s: %s",
                    reg.name, reg.address, self.device_name, exc,
                )
                results.append(
                    DataPoint(
                        name=reg.name, value=None,
                        unit=reg.unit, quality="bad",
                    )
                )

        return results

    async def _read_register(
        self, reg: ModbusRegisterConfig, slave: int
    ) -> DataPoint:
        """Read a single register configuration and return a DataPoint."""
        dtype_info = _DATA_TYPE_MAP.get(reg.data_type)

        if reg.data_type == DataType.BOOL:
            count = 1
        elif reg.data_type == DataType.STRING:
            count = reg.count
        elif dtype_info is not None:
            _, required_regs = dtype_info
            count = max(reg.count, required_regs)
        else:
            raise ValueError(
                f"Unsupported data type '{reg.data_type.value}' for register "
                f"'{reg.name}'"
            )

        # FC 3 = holding registers, FC 4 = input registers
        # Convention: addresses >= 10000 are input registers (adjustable).
        # Default: use holding registers.
        response = await self._client.read_holding_registers(
            address=reg.address,
            count=count,
            device_id=slave,
        )

        if response.isError():
            raise ModbusException(
                f"Modbus error reading '{reg.name}': {response}"
            )

        raw_value = self._decode_registers(
            response.registers, reg.data_type, dtype_info[0] if dtype_info else ""
        )

        # Apply scale and offset
        if isinstance(raw_value, (int, float)):
            scaled_value = raw_value * reg.scale + reg.offset
        else:
            scaled_value = raw_value

        return DataPoint(
            name=reg.name,
            value=scaled_value,
            unit=reg.unit,
            quality="good",
        )

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    async def write_value(self, name: str, value: Any) -> bool:
        """Write *value* to the register identified by *name*.

        Returns ``True`` on success, ``False`` on failure.
        """
        reg = self._register_map.get(name)
        if reg is None:
            self.logger.error(
                "Register '%s' not found on %s", name, self.device_name
            )
            return False

        if not reg.writable:
            self.logger.error(
                "Register '%s' on %s is not writable", name, self.device_name
            )
            return False

        if not self._connected or self._client is None:
            self.logger.error(
                "Cannot write to '%s': not connected to %s",
                name,
                self.device_name,
            )
            return False

        try:
            # Reverse the scale/offset transformation
            if reg.scale != 0 and isinstance(value, (int, float)):
                raw_value = (value - reg.offset) / reg.scale
            else:
                raw_value = value

            registers = self._encode_value(raw_value, reg.data_type)
            slave = self.device_config.slave_id

            if len(registers) == 1:
                response = await self._client.write_register(
                    address=reg.address,
                    value=registers[0],
                    device_id=slave,
                )
            else:
                response = await self._client.write_registers(
                    address=reg.address,
                    values=registers,
                    device_id=slave,
                )

            if response.isError():
                self.logger.error(
                    "Modbus write error for '%s' on %s: %s",
                    name,
                    self.device_name,
                    response,
                )
                return False

            self.logger.info(
                "Wrote %s = %s to %s (raw %s)",
                name,
                value,
                self.device_name,
                registers,
            )
            return True

        except (ModbusException, OSError) as exc:
            self.logger.error(
                "Write failed for '%s' on %s: %s",
                name,
                self.device_name,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Register encoding / decoding helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_registers(
        registers: list[int],
        data_type: DataType,
        fmt: str,
    ) -> int | float:
        """Convert raw Modbus register words into a typed Python value."""
        if data_type == DataType.BOOL:
            return bool(registers[0] & 0x01)

        if data_type == DataType.STRING:
            raw_bytes = b"".join(r.to_bytes(2, byteorder="big") for r in registers)
            return raw_bytes.decode("ascii", errors="replace").rstrip("\x00")

        # Pack register words as big-endian unsigned shorts, then unpack as
        # the target type.
        raw_bytes = b"".join(
            struct.pack(">H", reg) for reg in registers
        )
        return struct.unpack(fmt, raw_bytes)[0]

    @staticmethod
    def _encode_value(
        value: Any, data_type: DataType
    ) -> list[int]:
        """Encode a Python value into a list of Modbus register words."""
        if data_type == DataType.BOOL:
            return [1 if value else 0]

        if data_type == DataType.STRING:
            if not isinstance(value, str):
                value = str(value)
            # Pad to even length for register alignment
            if len(value) % 2:
                value += "\x00"
            encoded = value.encode("ascii", errors="replace")
            return [
                int.from_bytes(encoded[i : i + 2], byteorder="big")
                for i in range(0, len(encoded), 2)
            ]

        fmt = _DATA_TYPE_MAP[data_type][0]
        raw_bytes = struct.pack(fmt, value)
        return [
            int.from_bytes(raw_bytes[i : i + 2], byteorder="big")
            for i in range(0, len(raw_bytes), 2)
        ]
