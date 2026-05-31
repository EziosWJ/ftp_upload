"""Pydantic data models for device configuration, schedules, and FTP settings."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    MODBUS_TCP = "modbus_tcp"
    S7 = "s7"


class DataType(str, Enum):
    """Modbus register / S7 area data types."""
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    BOOL = "bool"
    STRING = "string"


class ModbusRegisterConfig(BaseModel):
    """Configuration for a single Modbus register or register range."""
    name: str = Field(..., description="Display name, e.g. 'temperature_1'")
    address: int = Field(..., description="Register start address (0-based)")
    count: int = Field(1, description="Number of registers to read")
    data_type: DataType = DataType.UINT16
    scale: float = Field(1.0, description="Multiply raw value by this factor")
    offset: float = Field(0.0, description="Add this after scaling")
    unit: str = Field("", description="Engineering unit, e.g. '°C', '%'")
    writable: bool = False


class S7AreaConfig(BaseModel):
    """Configuration for an S7 data area to read/write."""
    name: str = Field(..., description="Display name, e.g. 'motor_speed'")
    area: str = Field(..., description="S7 area: 'DB', 'I', 'Q', 'M'")
    db_number: int = Field(0, description="DB number (only for area='DB')")
    start: int = Field(..., description="Start byte address")
    size: int = Field(..., description="Number of bytes to read")
    data_type: DataType = DataType.FLOAT32
    bit_offset: int | None = Field(None, description="Bit offset (for BOOL type)")
    scale: float = Field(1.0)
    offset: float = Field(0.0)
    unit: str = ""
    writable: bool = False


class DeviceConfig(BaseModel):
    """Configuration for a single device (Modbus TCP or S7)."""
    name: str = Field(..., description="Unique device name")
    device_type: DeviceType
    host: str
    port: int = 502
    enabled: bool = True

    # Modbus-specific
    slave_id: int = 1
    registers: list[ModbusRegisterConfig] = []

    # S7-specific
    rack: int = 0
    slot: int = 1
    areas: list[S7AreaConfig] = []


class ScheduleConfig(BaseModel):
    """Polling schedule for a device."""
    device_name: str
    interval_seconds: int = Field(10, ge=1, description="Polling interval in seconds")
    enabled: bool = True


class FtpConfig(BaseModel):
    """FTP server connection settings."""
    host: str = ""
    port: int = 21
    username: str = "anonymous"
    password: str = ""
    remote_dir: str = "/"
    enabled: bool = False
    upload_interval_seconds: int = Field(300, ge=60, description="How often to upload data files")


class AppConfig(BaseModel):
    """Top-level application configuration."""
    devices: list[DeviceConfig] = []
    schedules: list[ScheduleConfig] = []
    ftp: FtpConfig = FtpConfig()
    web_port: int = 8000
    data_dir: str = "data"
    log_level: str = "INFO"
