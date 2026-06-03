"""Collector factory — single place to map DeviceType → collector class."""

from app.models import DeviceConfig, DeviceType

from .base import BaseCollector
from .modbus_collector import ModbusCollector
from .s7_collector import S7Collector


def create_collector(device: DeviceConfig) -> BaseCollector:
    """Instantiate the appropriate collector for a device config."""
    if device.device_type == DeviceType.MODBUS_TCP:
        return ModbusCollector(device)
    if device.device_type == DeviceType.S7:
        return S7Collector(device)
    raise ValueError(f"Unknown device type: {device.device_type}")
