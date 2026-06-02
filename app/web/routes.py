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
