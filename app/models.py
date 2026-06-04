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


class MeasurePointInfo(BaseModel):
    """测点基础信息"""
    point_code: str = Field(..., description="测点编码")
    point_type_code: str = Field("", description="测点类型编码")
    point_type_name: str = Field("", description="测点类型名称")
    device_code: str = Field("", description="所属设备编码")
    point_location: str = Field("", description="测点位置")
    unit: str = Field("", description="测量值单位")
    range_upper: float = Field(0, description="量程上限")
    range_lower: float = Field(0, description="量程下限")
    alarm_upper: float = Field(0, description="报警上限")
    alarm_lower: float = Field(0, description="报警下限")
    sensor_relation: str = Field("", description="传感器关联关系")
    data_define_time: str = Field("", description="数据定义时间")


class MeasurePointRealtimeInfo(BaseModel):
    """测点实时信息"""
    point_code: str = Field(..., description="测点编码")
    point_type_code: str = Field("", description="测点类型编码")
    point_type_name: str = Field("", description="测点类型名称")
    device_code: str = Field("", description="所属设备编码")
    point_value: float = Field(0, description="测点数值")
    point_unit: str = Field("", description="测点数值单位")
    point_status: str = Field("", description="测点状态")
    data_time: str = Field("", description="数据时间")


class ObsoleteDeviceInfo(BaseModel):
    """淘汰禁用设备信息 (JZTT) — MT/T 1201.2-2023"""
    product_name: str = Field(..., description="产品名称")
    spec_model: str = Field("", description="规格型号")
    non_compliance_reason: str = Field("", description="不符合原因")
    immediate_prohibition: int = Field(0, description="是否立即禁止，1=是")
    prohibition_deadline: str = Field("", description="禁止期限")
    announcement_batch: str = Field("", description="公告批次")
    announcement_date: str = Field("", description="公告日期，格式YYYY-MM-DD")
    effective_date: str = Field("", description="生效日期，格式YYYY-MM-DD")
    elimination_category: int = Field(0, description="淘汰类别，1-4")
    remark: str = Field("", description="备注")


class DeviceTestInfo(BaseModel):
    """设备检测检验信息 (JCJY) — MT/T 1201.2-2023"""
    factory_code: str = Field(..., description="出厂编码")
    device_name: str = Field("", description="设备名称")
    spec_model: str = Field("", description="规格型号")
    test_no: str = Field("", description="检验编号")
    test_project: str = Field("", description="检验项目")
    test_result: int = Field(0, description="检验结论，0=合格/1=不合格")
    test_date: str = Field("", description="检验日期，格式YYYY-MM-DD")
    test_agency: str = Field("", description="检验机构")
    valid_from: str = Field("", description="有效期开始，格式YYYY-MM-DD")
    valid_to: str = Field("", description="有效期结束，格式YYYY-MM-DD")
    test_cycle: int = Field(0, description="检验周期（月）")
    remark: str = Field("", description="备注")
    contact_person: str = Field("", description="联系人")
    contact_phone: str = Field("", description="联系电话")


class AlarmData(BaseModel):
    """设备异常/报警数据 (YC) — MT/T 1201.2-2023"""
    point_code: str = Field(..., description="测点编码")
    point_type_code: str = Field("", description="测点类型编码")
    point_name: str = Field("", description="测点名称")
    device_code: str = Field("", description="设备编码")
    alarm_status: int = Field(0, description="报警状态，1=报警")
    alarm_start_time: str = Field("", description="报警开始时间")
    alarm_end_time: str = Field("", description="报警结束时间")
    alarm_level: int = Field(0, description="报警等级")
    recovery_time: str = Field("", description="恢复正常时间")
    recovery_value: float = Field(0, description="恢复正常值")
    peak_time: str = Field("", description="最值时间")
    peak_value: float = Field(0, description="最值")
    data_time: str = Field("", description="数据时间")


class FtpConfig(BaseModel):
    """FTP server connection settings."""
    host: str = ""
    port: int = 21
    username: str = "anonymous"
    password: str = ""
    remote_dir: str = "/"
    enabled: bool = False
    upload_interval_seconds: int = Field(300, ge=60, description="How often to upload data files")
    file_filter: list[str] = Field(default_factory=list, description="允许上传的文件类型标识，空列表=上传全部")


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
    obsolete_device_list: list[ObsoleteDeviceInfo] = []
    device_test_list: list[DeviceTestInfo] = []
    measure_point_list: list[MeasurePointInfo] = []
    measure_point_realtime_list: list[MeasurePointRealtimeInfo] = []
    alarm_data_list: list[AlarmData] = []
    schedules: list[ScheduleConfig] = []
    ftp: FtpConfig = FtpConfig()
    system_info: SystemInfo = SystemInfo()
    web_port: int = 8000
    data_dir: str = "data"
    log_level: str = "INFO"


# ──────────────── 上传配置模型 ────────────────

class ScheduleType(str, Enum):
    """定时类型枚举"""
    INTERVAL_MINUTES = "interval_minutes"  # 自定义分钟
    INTERVAL_HOURS = "interval_hours"      # 自定义小时
    DAILY = "daily"                        # 每日固定时点
    WEEKLY = "weekly"                      # 每周指定日期+时点


class RegisterPoint(BaseModel):
    """上传配置中的寄存器测点"""
    point_code: str = Field(..., description="测点编码")
    point_name: str = Field("", description="测点名称")
    register_address: str = Field("", description="寄存器地址（如 DB1.DBW0 或 40001）")
    data_type: DataType = DataType.FLOAT32
    range_upper: float = Field(0, description="量程上限")
    range_lower: float = Field(0, description="量程下限")
    alarm_upper: float = Field(0, description="报警上限")
    alarm_lower: float = Field(0, description="报警下限")
    unit: str = Field("", description="计量单位")
    collect_enabled: bool = Field(False, description="采集启用状态")
    report_enabled: bool = Field(False, description="是否参与报文生成")
    fault_default: float = Field(-9999, description="故障缺省值")


class DeviceWithRegisters(BaseModel):
    """某个系统下的设备及其寄存器"""
    device_name: str = Field(..., description="设备名称")
    device_code: str = Field("", description="设备编码")
    plc_device: str = Field("", description="对应的PLC连接设备（DeviceConfig.name）")
    registers: list[RegisterPoint] = Field(default_factory=list)


class UploadTask(BaseModel):
    """单个上传任务：一个数据项目 + 它的定时配置"""
    task_id: str = Field(..., description="唯一标识，如 JBSJ、tfjk_SS")
    data_type: str = Field(..., description="数据类型标识")
    system_code: str = Field("", description="六大系统编码（动态数据才需要）")
    file_name_fields: list[str] = Field(
        default_factory=lambda: ["mine_code", "type", "timestamp"],
        description="文件名组成字段",
    )
    file_name_template: str = Field("", description="自定义文件名模板，优先于字段勾选")
    schedule_type: ScheduleType = ScheduleType.DAILY
    interval_value: int = Field(0, ge=0, description="间隔值（分钟或小时）")
    hour: int = Field(0, ge=0, le=23, description="时（daily/weekly）")
    minute: int = Field(0, ge=0, le=59, description="分（daily/weekly）")
    weekday: int | None = Field(None, ge=0, le=6, description="星期几（weekly: 0=周一）")
    enabled: bool = True


class UploadConfig(BaseModel):
    """上传配置顶层模型，独立存储在 upload_config.json"""
    tasks: list[UploadTask] = Field(default_factory=list)
    system_devices: dict[str, list[DeviceWithRegisters]] = Field(
        default_factory=dict,
        description="系统→设备→寄存器 三层结构",
    )
