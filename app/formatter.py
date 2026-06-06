"""MT/T 1201.2-2023 标准报文格式化器

格式规范：
- 字段分隔：;
- 单条结尾：~
- 文件结尾：||
- 异常值：-9999
- 编码：UTF-8 无 BOM
- 文件名：煤矿编码_类型_时间戳.txt

所有函数签名中的 mine_code 和 mine_name 均从 SystemInfo 直接传入，
不调用 load_config()，确保 formatter 为纯函数。
"""

from datetime import datetime
from pathlib import Path

from app.models import (
    AlarmData, DeviceBasicInfo, DeviceTestInfo, MeasurePointInfo,
    MeasurePointRealtimeInfo, ObsoleteDeviceInfo, SafetyCertInfo, SystemInfo,
)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _header(system_code: str, system_name: str, mine_code: str, mine_name: str) -> str:
    """生成标准报文头：煤矿编码;煤矿名称;系统标识;系统名称;时间戳~"""
    return f"{mine_code};{mine_name};{system_code};{system_name};{_now_str()}~"


def _safe(val) -> str:
    """安全转字符串，None/空 返回空串"""
    if val is None:
        return ""
    return str(val)


def _format_row(*fields) -> str:
    """格式化单行数据：分号分隔，末尾~"""
    return ";".join(_safe(f) for f in fields) + "~"


def _device_basic_row(d: DeviceBasicInfo) -> str:
    return _format_row(
        d.device_code, d.device_name, d.spec_model,
        d.device_category, d.production_date,
        d.belonging_system, d.install_date,
        d.install_location, d.manufacturer,
        d.factory_code, d.safety_cert_no,
        d.explosion_proof_no, d.rated_voltage,
        d.rated_current, d.rated_power,
    )


def _safety_cert_row(c: SafetyCertInfo) -> str:
    return _format_row(
        c.product_name, c.spec_model, c.factory_code,
        c.cert_no, c.valid_from, c.valid_to,
        c.cert_status.value, c.production_unit,
        c.production_address, c.contact_person,
        c.contact_phone, c.certificate_holder,
    )


def _obsolete_device_row(d: ObsoleteDeviceInfo) -> str:
    return _format_row(
        d.product_name, d.spec_model,
        d.non_compliance_reason, d.immediate_prohibition,
        d.prohibition_deadline, d.announcement_batch,
        d.announcement_date, d.effective_date,
        d.elimination_category, d.remark,
    )


def _device_test_row(t: DeviceTestInfo) -> str:
    return _format_row(
        t.factory_code, t.device_name, t.spec_model,
        t.test_no, t.test_project, t.test_result,
        t.test_date, t.test_agency,
        t.valid_from, t.valid_to, t.test_cycle,
        t.remark, t.contact_person, t.contact_phone,
    )


def _measure_point_info_row(p: MeasurePointInfo) -> str:
    return _format_row(
        p.point_code, p.point_type_code,
        p.point_type_name, p.device_code,
        p.point_location, p.unit,
        p.range_upper, p.range_lower,
        p.alarm_upper, p.alarm_lower,
        p.sensor_relation, p.data_define_time,
    )


def _measure_point_realtime_row(p: MeasurePointRealtimeInfo) -> str:
    return _format_row(
        p.point_code, p.point_type_code,
        p.point_type_name, p.device_code,
        p.point_value, p.point_unit,
        p.point_status, p.data_time,
    )


def _alarm_data_row(a: AlarmData) -> str:
    return _format_row(
        a.point_code, a.point_type_code,
        a.point_name, a.device_code,
        a.alarm_status, a.alarm_start_time,
        a.alarm_end_time, a.alarm_level,
        a.recovery_time, a.recovery_value,
        a.peak_time, a.peak_value,
        a.data_time,
    )


# ──────────────── 静态基础数据格式化 ────────────────

def format_jbsj(items: list[DeviceBasicInfo], system_info: SystemInfo) -> str:
    """设备基本信息 (JBSJ)"""
    si = system_info
    lines = [_header("JBSJ", "设备基本信息", si.mine_code, si.mine_name)]
    for d in items:
        lines.append(_device_basic_row(d))
    lines.append("||")
    return "\n".join(lines)


def format_absj(items: list[SafetyCertInfo], system_info: SystemInfo) -> str:
    """安标信息 (ABSJ)"""
    si = system_info
    lines = [_header("ABSJ", "安标信息", si.mine_code, si.mine_name)]
    for c in items:
        lines.append(_safety_cert_row(c))
    lines.append("||")
    return "\n".join(lines)


def format_jztt(items: list[ObsoleteDeviceInfo], system_info: SystemInfo) -> str:
    """淘汰禁用设备 (JZTT)"""
    si = system_info
    lines = [_header("JZTT", "淘汰禁用设备", si.mine_code, si.mine_name)]
    for d in items:
        lines.append(_obsolete_device_row(d))
    lines.append("||")
    return "\n".join(lines)


def format_jcjy(items: list[DeviceTestInfo], system_info: SystemInfo) -> str:
    """设备检测检验 (JCJY)"""
    si = system_info
    lines = [_header("JCJY", "设备检测检验", si.mine_code, si.mine_name)]
    for t in items:
        lines.append(_device_test_row(t))
    lines.append("||")
    return "\n".join(lines)


# ──────────────── 动态监控数据格式化 ────────────────

def format_measure_point_define(
    items: list[MeasurePointInfo],
    system_code: str,
    system_name: str,
    mine_code: str,
    mine_name: str,
) -> str:
    """测点基础信息 (JC) — 通用"""
    lines = [_header(system_code, system_name, mine_code, mine_name)]
    for p in items:
        lines.append(_measure_point_info_row(p))
    lines.append("||")
    return "\n".join(lines)


def format_measure_point_realtime(
    items: list[MeasurePointRealtimeInfo],
    system_code: str,
    system_name: str,
    mine_code: str,
    mine_name: str,
) -> str:
    """测点实时数据 (SS) — 通用"""
    lines = [_header(system_code, system_name, mine_code, mine_name)]
    for p in items:
        lines.append(_measure_point_realtime_row(p))
    lines.append("||")
    return "\n".join(lines)


def format_alarm_data(
    items: list[AlarmData],
    system_code: str,
    system_name: str,
    mine_code: str,
    mine_name: str,
) -> str:
    """异常/报警数据 (YC) — 通用"""
    lines = [_header(system_code, system_name, mine_code, mine_name)]
    for a in items:
        lines.append(_alarm_data_row(a))
    lines.append("||")
    return "\n".join(lines)


# ──────────────── 文件写入 ────────────────

def write_report_file(
    data_type: str,
    content: str,
    data_dir: str = "data",
    mine_code: str = "000000000000",
) -> str:
    """按标准命名写入文件，返回文件路径。 caller 负责写入。"""
    project_root = Path(__file__).parent.parent
    dir_path = project_root / data_dir
    dir_path.mkdir(parents=True, exist_ok=True)
    return f"{mine_code}_{data_type}_{_file_timestamp()}.txt"


# ──────────────── 六大系统便捷函数 ────────────────

SYSTEM_MAP = {
    "tfjk": ("30", "主要通风机监控系统", "TF"),
    "psjk": ("31", "主排水监控系统", "PS"),
    "lijk": ("32", "立井提升监控系统", "LJ"),
    "xjjk": ("33", "斜井提升监控系统", "XJ"),
    "kyjk": ("34", "空气压缩机监控系统", "KY"),
    "jcjk": ("35", "绞车监控系统", "JC"),
}


def format_system_jc(items: list[MeasurePointInfo], system_key: str, system_info: SystemInfo) -> str:
    """六大系统测点基础 (JC)"""
    code, name, short = SYSTEM_MAP[system_key]
    si = system_info
    return format_measure_point_define(items, code, name, si.mine_code, si.mine_name)


def format_system_ss(items: list[MeasurePointRealtimeInfo], system_key: str, system_info: SystemInfo) -> str:
    """六大系统实时数据 (SS)"""
    code, name, _ = SYSTEM_MAP[system_key]
    si = system_info
    return format_measure_point_realtime(items, code, name, si.mine_code, si.mine_name)


def format_system_yc(items: list[AlarmData], system_key: str, system_info: SystemInfo) -> str:
    """六大系统异常数据 (YC)"""
    code, name, _ = SYSTEM_MAP[system_key]
    si = system_info
    return format_alarm_data(items, code, name, si.mine_code, si.mine_name)