"""Web page routes using Jinja2 templates."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ..config import load_config

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/")
async def dashboard(request: Request):
    """Dashboard showing device status, recent data, FTP status."""
    config = load_config()
    return templates.TemplateResponse(
        request, "index.html",
        {"config": config, "active_page": "dashboard"},
    )


@router.get("/devices")
async def device_list(request: Request):
    """Device management page - list all devices."""
    config = load_config()
    return templates.TemplateResponse(
        request, "devices.html",
        {"config": config, "active_page": "devices"},
    )


@router.get("/devices/add")
async def device_add(request: Request):
    """Add device form."""
    return templates.TemplateResponse(
        request, "device_form.html",
        {"active_page": "devices", "device": None},
    )


@router.get("/devices/{device_name}/edit")
async def device_edit(request: Request, device_name: str):
    """Edit device form."""
    config = load_config()
    device = next((d for d in config.devices if d.name == device_name), None)
    if not device:
        return templates.TemplateResponse(
            request, "404.html", {}, status_code=404,
        )
    return templates.TemplateResponse(
        request, "device_form.html",
        {"active_page": "devices", "device": device},
    )


@router.get("/schedules")
async def schedule_list(request: Request):
    """Schedule management page."""
    config = load_config()
    return templates.TemplateResponse(
        request, "schedules.html",
        {"config": config, "active_page": "schedules"},
    )


@router.get("/ftp")
async def ftp_config(request: Request):
    """FTP configuration page."""
    config = load_config()
    return templates.TemplateResponse(
        request, "ftp.html",
        {"config": config, "active_page": "ftp"},
    )


@router.get("/logs")
async def log_viewer(request: Request):
    """Log viewer page."""
    return templates.TemplateResponse(
        request, "logs.html",
        {"active_page": "logs"},
    )


@router.get("/system-info")
async def system_info_page(request: Request):
    """System information configuration page."""
    config = load_config()
    return templates.TemplateResponse(
        request, "system_info.html",
        {"config": config, "active_page": "system-info"},
    )


@router.get("/device-basic-info")
async def device_basic_info_page(request: Request):
    """Device basic information page with device list."""
    config = load_config()
    basic_devices_data = [d.model_dump() for d in config.basic_devices]
    return templates.TemplateResponse(
        request, "device_basic_info.html",
        {"config": config, "devices": basic_devices_data, "active_page": "device-basic-info"},
    )


@router.get("/safety-cert")
async def safety_cert_page(request: Request):
    """Safety certificate info page."""
    config = load_config()
    safety_certs_data = [c.model_dump() for c in config.safety_cert_list]
    return templates.TemplateResponse(
        request, "safety_cert.html",
        {"config": config, "safety_certs": safety_certs_data, "active_page": "safety-cert"},
    )


@router.get("/measure-point")
async def measure_point_page(request: Request):
    """Measure point info page."""
    config = load_config()
    measure_points_data = [p.model_dump() for p in config.measure_point_list]
    return templates.TemplateResponse(
        request, "measure_point.html",
        {"config": config, "measure_points": measure_points_data, "active_page": "measure-point"},
    )


@router.get("/measure-point-realtime")
async def measure_point_realtime_page(request: Request):
    """Measure point realtime info page."""
    config = load_config()
    measure_point_realtime_data = [p.model_dump() for p in config.measure_point_realtime_list]
    measure_points_data = [p.model_dump() for p in config.measure_point_list]
    return templates.TemplateResponse(
        request, "measure_point_realtime.html",
        {"config": config, "measure_point_realtime_list": measure_point_realtime_data, "measure_point_list": measure_points_data, "active_page": "measure-point-realtime"},
    )


@router.get("/obsolete-devices")
async def obsolete_device_page(request: Request):
    """Obsolete device info page (JZTT)."""
    config = load_config()
    items_data = [d.model_dump() for d in config.obsolete_device_list]
    return templates.TemplateResponse(
        request, "obsolete_device.html",
        {"config": config, "items": items_data, "active_page": "obsolete-devices"},
    )


@router.get("/device-tests")
async def device_test_page(request: Request):
    """Device test info page (JCJY)."""
    config = load_config()
    items_data = [t.model_dump() for t in config.device_test_list]
    return templates.TemplateResponse(
        request, "device_test.html",
        {"config": config, "items": items_data, "active_page": "device-tests"},
    )


@router.get("/alarm-data")
async def alarm_data_page(request: Request):
    """Alarm data page (YC)."""
    config = load_config()
    items_data = [a.model_dump() for a in config.alarm_data_list]
    return templates.TemplateResponse(
        request, "alarm_data.html",
        {"config": config, "items": items_data, "active_page": "alarm-data"},
    )


@router.get("/reports")
async def reports_page(request: Request):
    """Standard report management page (MT/T 1201.2-2023)."""
    from app.formatter import SYSTEM_MAP
    systems = [
        {"name": name, "code": code, "prefix": short.lower()}
        for sys_key, (code, name, short) in SYSTEM_MAP.items()
    ]
    return templates.TemplateResponse(
        request, "reports.html",
        {"active_page": "reports", "systems": systems},
    )
