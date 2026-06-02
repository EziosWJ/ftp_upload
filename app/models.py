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


class DeviceBasicInfo(BaseModel):
    """Basic device information - separate from device configuration."""
    device_name: str = Field(..., description="设备名称")
    device_code: str = Field("", description="设备编码")
    spec_model: str = Field("", description="规格型号")
    device_category: str = Field("", description="设备类别")
    production_date: str = Field("", description="生产日期")
    belonging_system: str = Field("", description="所属系统")
    install_date: str = Field("", description="安装日期")
    install_location: str = Field("", description="安装位置")
    manufacturer: str = Field("", description="生产厂家")
    factory_code: str = Field("", description="出厂编码")
    safety_cert_no: str = Field("", description="安标证书编号")
    explosion_proof_no: str = Field("", description="防爆证书编号")
    rated_voltage: str = Field("", description="额定电压")
    rated_current: str = Field("", description="额定电流")
    rated_power: str = Field("", description="额定功率")


class SafetyCertStatus(int, Enum):
    """安标状态枚举"""
    VALID = 1      # 有效
    SUSPENDED = 2  # 暂停
    CANCELLED = 3  # 注销
    REVOKED = 4    # 撤销


class SafetyCertInfo(BaseModel):
    """安标证书信息"""
    device_name: str = Field(..., description="设备名称")
    product_name: str = Field("", description="产品名称")
    spec_model: str = Field("", description="规格型号")
    factory_code: str = Field("", description="出厂编码")
    cert_no: str = Field("", description="安标证书编号")
    valid_from: str = Field("", description="安标有效开始时间，格式YYYY-MM-DD")
    valid_to: str = Field("", description="安标有效结束时间，格式YYYY-MM-DD")
    cert_status: SafetyCertStatus = Field(SafetyCertStatus.VALID, description="安标状态")
    production_unit: str = Field("", description="生产单位名称")
    production_address: str = Field("", description="生产地址")
    contact_person: str = Field("", description="生产单位联系人")
    contact_phone: str = Field("", description="生产单位联系电话")
    certificate_holder: str = Field("", description="持证人")


class FtpConfig(BaseModel):
    """FTP server connection settings."""
    host: str = ""
    port: int = 21
    username: str = "anonymous"
    password: str = ""
    remote_dir: str = "/"
    enabled: bool = False
    upload_interval_seconds: int = Field(300, ge=60, description="How often to upload data files")


class SystemInfo(BaseModel):
    """System-level information for the application."""
    mine_code: str = Field("", description="煤矿编码，如：14122800315")
    mine_name: str = Field("", description="煤矿名称，如：XX煤矿")
    system_name: str = Field("", description="系统名称")
    system_model: str = Field("", description="系统型号")


class AppConfig(BaseModel):
    """Top-level application configuration."""
    devices: list[DeviceConfig] = []
    basic_devices: list[DeviceBasicInfo] = []
    safety_cert_list: list[SafetyCertInfo] = []
    schedules: list[ScheduleConfig] = []
    ftp: FtpConfig = FtpConfig()
    system_info: SystemInfo = SystemInfo()
    web_port: int = 8000
    data_dir: str = "data"
    log_level: str = "INFO"
