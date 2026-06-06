"""System info API routes (FTP, reports, MQTT, status, logs)."""

import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import load_config, save_config
from app.models import FtpConfig, SystemInfo, UploadConfig, UploadTask

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/api/ftp")
async def get_ftp_config():
    """Get FTP configuration."""
    config = load_config()
    return {"ftp": config.ftp.model_dump()}


@router.post("/api/ftp")
async def update_ftp_config(ftp_config: FtpConfig):
    """Update FTP configuration and restart uploader if needed."""
    config = load_config()
    config.ftp = ftp_config
    save_config(config)

    from app.ftp_uploader import stop_ftp_uploader, start_ftp_uploader
    await stop_ftp_uploader()
    await start_ftp_uploader()

    logger.info("Updated FTP configuration and restarted uploader")
    return {"status": "success", "ftp": ftp_config.model_dump()}


@router.get("/api/ftp/status")
async def ftp_upload_status():
    """Get FTP upload runtime status."""
    from app.ftp_uploader import get_upload_status
    return get_upload_status()


@router.post("/api/ftp/upload-now")
async def ftp_upload_now():
    """Manually trigger an immediate upload of pending files."""
    config = load_config()
    if not config.ftp.host:
        return {"status": "error", "message": "FTP 服务器未配置"}

    from app.ftp_uploader import upload_pending_files
    uploaded = await upload_pending_files(config.ftp, config.data_dir)
    if uploaded:
        return {"status": "success", "message": f"已上传 {len(uploaded)} 个文件", "files": uploaded}


@router.post("/api/ftp/test")
async def test_ftp_connection():
    """Test FTP connection."""
    from app.ftp_uploader import test_ftp_connection as _test
    config = load_config()
    ok, msg = await _test(config.ftp)
    if ok:
        return {"status": "success", "message": msg}
    return {"status": "error", "message": msg}


@router.get("/api/system-info")
async def get_system_info():
    """Get system information."""
    config = load_config()
    return {"system_info": config.system_info.model_dump()}


@router.post("/api/system-info")
async def update_system_info(system_info: SystemInfo):
    """Update system information."""
    config = load_config()
    config.system_info = system_info
    save_config(config)
    logger.info("Updated system information")
    return {"status": "success", "system_info": system_info.model_dump()}


@router.get("/api/status")
async def system_status():
    """Get system status."""
    from app.server import get_pipeline
    config = load_config()
    device_statuses = get_pipeline().get_device_statuses()
    online_count = sum(1 for s in device_statuses.values() if s["online"])
    return {
        "devices": {
            "total": len(config.devices),
            "enabled": len([d for d in config.devices if d.enabled]),
            "online": online_count,
        },
        "schedules": {
            "total": len(config.schedules),
            "enabled": len([s for s in config.schedules if s.enabled])
        },
        "ftp": {
            "enabled": config.ftp.enabled,
            "host": config.ftp.host
        },
        "timestamp": datetime.now().isoformat()
    }


@router.get("/api/device-status")
async def device_statuses():
    """Get per-device online/offline status."""
    from app.server import get_pipeline
    return get_pipeline().get_device_statuses()


@router.delete("/api/logs")
async def clear_logs():
    """Clear all log entries from app.log."""
    log_file = Path(__file__).parent.parent.parent / "app.log"
    try:
        log_file.write_text("", encoding="utf-8")
        logger.info("Logs cleared")
        return {"status": "success", "message": "日志已清空"}
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/api/logs")
async def get_logs(level: str = "INFO", limit: int = 100):
    """Get recent log entries from app.log."""
    log_lines = []
    log_file = Path(__file__).parent.parent.parent / "app.log"

    if log_file.exists():
        try:
            all_lines = log_file.read_text(encoding="utf-8").splitlines()
            level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            min_idx = level_order.index(level) if level in level_order else 1

            pattern = re.compile(r"\] (" + "|".join(level_order[min_idx:]) + r"):")
            for line in all_lines:
                if pattern.search(line) or not re.search(r"\] [A-Z]+:", line):
                    log_lines.append(line)

            log_lines = log_lines[-limit:]
        except Exception:
            pass

    return {"logs": log_lines, "count": len(log_lines)}


@router.get("/api/reports/generate/{data_type}")
async def generate_report(data_type: str):
    """Generate standard format report file and return content."""
    from app.formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        write_report_file, SYSTEM_MAP,
    )

    config = load_config()
    system_info = config.system_info

    formatter_map = {
        "jbsj": lambda si=system_info: format_jbsj(config.basic_devices, si),
        "absj": lambda si=system_info: format_absj(config.safety_cert_list, si),
        "jztt": lambda si=system_info: format_jztt(config.obsolete_device_list, si),
        "jcjy": lambda si=system_info: format_jcjy(config.device_test_list, si),
    }

    for sys_key, (code, name, short) in SYSTEM_MAP.items():
        prefix = short.lower()
        formatter_map[f"{prefix}jc"] = lambda sk=sys_key, si=system_info: format_system_jc(
            config.measure_point_list, sk, si
        )
        formatter_map[f"{prefix}ss"] = lambda sk=sys_key, si=system_info: format_system_ss(
            config.measure_point_realtime_list, sk, si
        )
        formatter_map[f"{prefix}yc"] = lambda sk=sys_key, si=system_info: format_system_yc(
            config.alarm_data_list, sk, si
        )

    if data_type not in formatter_map:
        raise HTTPException(status_code=400, detail=f"不支持的数据类型: {data_type}")

    content = formatter_map[data_type]()
    file_name = write_report_file(data_type.upper(), content, config.data_dir, system_info.mine_code or "000000000000")
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / config.data_dir
    file_path = data_dir / file_name
    file_path.write_text(content, encoding="utf-8")

    return {
        "status": "success",
        "file": str(file_path),
        "content": content,
    }


@router.post("/api/reports/generate-all")
async def generate_all_reports():
    """Batch generate all standard report files."""
    from app.formatter import (
        format_jbsj, format_absj, format_jztt, format_jcjy,
        format_system_jc, format_system_ss, format_system_yc,
        write_report_file, SYSTEM_MAP,
    )

    config = load_config()
    system_info = config.system_info
    files = []

    static_generators = [
        ("JBSJ", lambda si=system_info: format_jbsj(config.basic_devices, si)),
        ("ABSJ", lambda si=system_info: format_absj(config.safety_cert_list, si)),
        ("JZTT", lambda si=system_info: format_jztt(config.obsolete_device_list, si)),
        ("JCJY", lambda si=system_info: format_jcjy(config.device_test_list, si)),
    ]
    for name, gen in static_generators:
        content = gen()
        file_name = write_report_file(name, content, config.data_dir, system_info.mine_code or "000000000000")
        project_root = Path(__file__).parent.parent.parent
        data_dir = project_root / config.data_dir
        fp = data_dir / file_name
        fp.write_text(content, encoding="utf-8")
        files.append(str(fp))

    for sys_key, (code, sys_name, short) in SYSTEM_MAP.items():
        for suffix, gen in [
            ("JC", lambda sk=sys_key, si=system_info: format_system_jc(config.measure_point_list, sk, si)),
            ("SS", lambda sk=sys_key, si=system_info: format_system_ss(config.measure_point_realtime_list, sk, si)),
            ("YC", lambda sk=sys_key, si=system_info: format_system_yc(config.alarm_data_list, sk, si)),
        ]:
            content = gen()
            file_name = write_report_file(f"{short}{suffix}", content, config.data_dir, system_info.mine_code or "000000000000")
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / config.data_dir
            fp = data_dir / file_name
            fp.write_text(content, encoding="utf-8")
            files.append(str(fp))

    return {"status": "success", "files": files, "count": len(files)}