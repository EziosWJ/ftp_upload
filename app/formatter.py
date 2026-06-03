"""MT/T 1201.2-2023 标准报文格式化器

格式规范：
- 字段分隔：;
- 单条结尾：~
- 文件结尾：||
- 异常值：-9999
- 编码：UTF-8 无 BOM
- 文件名：煤矿编码_类型_时间戳.txt
"""

from datetime import datetime
from pathlib import Path

from app.config import load_config
from app.models import (
    DeviceBasicInfo, SafetyCertInfo, ObsoleteDeviceInfo, DeviceTestInfo,
    MeasurePointInfo, MeasurePointRealtimeInfo, AlarmData,
)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _header(system_code: str, system_name: str) -> str:
    """生成标准报文头：煤矿编码;煤矿名称;系统标识;系统名称;时间戳~"""
    config = load_config()
    si = config.system_info
    return f"{si.mine_code};{si.mine_name};{system_code};{system_name};{_now_str()}~"


def _safe(val) -> str:
    """安全转字符串，None/空 返回空串"""
    if val is None:
        return ""
    return str(val)


# ──────────────── 静态基础数据格式化 ────────────────

def format_jbsj(items: list[DeviceBasicInfo]) -> str:
    """设备基本信息 (JBSJ)"""
    lines = [_header("JBSJ", "设备基本信息")]
    for d in items:
        fields = [
            _safe(d.device_code), _safe(d.device_name), _safe(d.spec_model),
            _safe(d.device_category), _safe(d.production_date),
            _safe(d.belonging_system), _safe(d.install_date),
            _safe(d.install_location), _safe(d.manufacturer),
            _safe(d.factory_code), _safe(d.safety_cert_no),
            _safe(d.explosion_proof_no), _safe(d.rated_voltage),
            _safe(d.rated_current), _safe(d.rated_power),
        ]
        lines.append(";".join(fields) + "~")
    lines.append("||")
    return "\n".join(lines)


def format_absj(items: list[SafetyCertInfo]) -> str:
    """安标信息 (ABSJ)"""
    lines = [_header("ABSJ", "安标信息")]
    for c in items:
        fields = [
            _safe(c.product_name), _safe(c.spec_model), _safe(c.factory_code),
            _safe(c.cert_no), _safe(c.valid_from), _safe(c.valid_to),
            str(c.cert_status.value), _safe(c.production_unit),
            _safe(c.production_address), _safe(c.contact_person),
            _safe(c.contact_phone), _safe(c.certificate_holder),
        ]
        lines.append(";".join(fields) + "~")
    lines.append("||")
    return "\n".join(lines)


def format_jztt(items: list[ObsoleteDeviceInfo]) -> str:
    """淘汰禁用设备 (JZTT)"""
    lines = [_header("JZTT", "淘汰禁用设备")]
    for d in items:
        fields = [
            _safe(d.product_name), _safe(d.spec_model),
            _safe(d.non_compliance_reason), str(d.immediate_prohibition),
            _safe(d.prohibition_deadline), _safe(d.announcement_batch),
            _safe(d.announcement_date), _safe(d.effective_date),
            str(d.elimination_category), _safe(d.remark),
        ]
        lines.append(";".join(fields) + "~")
    lines.append("||")
    return "\n".join(lines)


def format_jcjy(items: list[DeviceTestInfo], mine_code: str = "", mine_name: str = "") -> str:
    """设备检测检验 (JCJY)"""
    lines = [_header("JCJY", "设备检测检验")]
    for t in items:
        fields = [
            _safe(t.factory_code), _safe(t.device_name), _safe(t.spec_model),
            _safe(t.test_no), _safe(t.test_project), str(t.test_result),
            _safe(t.test_date), _safe(t.test_agency),
            _safe(t.valid_from), _safe(t.valid_to), str(t.test_cycle),
            _safe(t.remark), _safe(t.contact_person), _safe(t.contact_phone),
        ]
        lines.append(";".join(fields) + "~")
    lines.append("||")
    return "\n".join(lines)


# ──────────────── 动态监控数据格式化 ────────────────

def format_measure_point_define(
    items: list[MeasurePointInfo],
    system_code: str,
    system_name: str,
    system_short: str,
) -> str:
    """测点基础信息 (JC) — 通用"""
    lines = [_header(system_code, system_name)]
    for p in items:
        fields = [
            _safe(p.point_code), _safe(p.point_type_code),
            _safe(p.point_type_name), _safe(p.device_code),
            _safe(p.point_location), _safe(p.unit),
            str(p.range_upper), str(p.range_lower),
            str(p.alarm_upper), str(p.alarm_lower),
            _safe(p.sensor_relation), _safe(p.data_define_time),
        ]
        lines.append(";".join(fields) + "~")
    lines.append("||")
    return "\n".join(lines)


def format_measure_point_realtime(
    items: list[MeasurePointRealtimeInfo],
    system_code: str,
    system_name: str,
) -> str:
    """测点实时数据 (SS) — 通用"""
    lines = [_header(system_code, system_name)]
    for p in items:
        fields = [
            _safe(p.point_code), _safe(p.point_type_code),
            _safe(p.point_type_name), _safe(p.device_code),
            str(p.point_value), _safe(p.point_unit),
            _safe(p.point_status), _safe(p.data_time),
        ]
        lines.append(";".join(fields) + "~")
    lines.append("||")
    return "\n".join(lines)


def format_alarm_data(
    items: list[AlarmData],
    system_code: str,
    system_name: str,
) -> str:
    """异常/报警数据 (YC) — 通用"""
    lines = [_header(system_code, system_name)]
    for a in items:
        fields = [
            _safe(a.point_code), _safe(a.point_type_code),
            _safe(a.point_name), _safe(a.device_code),
            str(a.alarm_status), _safe(a.alarm_start_time),
            _safe(a.alarm_end_time), str(a.alarm_level),
            _safe(a.recovery_time), str(a.recovery_value),
            _safe(a.peak_time), str(a.peak_value),
            _safe(a.data_time),
        ]
        lines.append(";".join(fields) + "~")
    lines.append("||")
    return "\n".join(lines)


# ──────────────── 文件写入 ────────────────

def write_report_file(
    data_type: str,
    content: str,
    data_dir: str = "data",
) -> Path:
    """按标准命名写入文件：煤矿编码_类型_时间戳.txt"""
    config = load_config()
    mine_code = config.system_info.mine_code or "000000000000"
    dir_path = Path(data_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    filename = f"{mine_code}_{data_type}_{_file_timestamp()}.txt"
    file_path = dir_path / filename

    # UTF-8 无 BOM
    file_path.write_text(content, encoding="utf-8")
    return file_path


# ──────────────── 六大系统便捷函数 ────────────────

SYSTEM_MAP = {
    "tfjk": ("30", "主要通风机监控系统", "TF"),
    "psjk": ("31", "主排水监控系统", "PS"),
    "lijk": ("32", "立井提升监控系统", "LJ"),
    "xjjk": ("33", "斜井提升监控系统", "XJ"),
    "kyjk": ("34", "空气压缩机监控系统", "KY"),
    "jcjk": ("35", "绞车监控系统", "JC"),
}


def format_system_jc(items: list[MeasurePointInfo], system_key: str) -> str:
    """六大系统测点基础 (JC)"""
    code, name, short = SYSTEM_MAP[system_key]
    return format_measure_point_define(items, code, name, short)


def format_system_ss(items: list[MeasurePointRealtimeInfo], system_key: str) -> str:
    """六大系统实时数据 (SS)"""
    code, name, _ = SYSTEM_MAP[system_key]
    return format_measure_point_realtime(items, code, name)


def format_system_yc(items: list[AlarmData], system_key: str) -> str:
    """六大系统异常数据 (YC)"""
    code, name, _ = SYSTEM_MAP[system_key]
    return format_alarm_data(items, code, name)
