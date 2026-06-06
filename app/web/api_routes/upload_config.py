"""Upload config API routes."""

import logging

from fastapi import APIRouter, HTTPException

from app.models import DeviceWithRegisters, RegisterPoint, UploadConfig, UploadTask

router = APIRouter(prefix="/api/upload-config", tags=["upload-config"])
logger = logging.getLogger(__name__)


@router.get("")
async def get_upload_config():
    """获取上传配置"""
    from app.upload_config import load_upload_config
    config = load_upload_config()
    return {"upload_config": config.model_dump()}


@router.post("")
async def save_upload_config(config: UploadConfig):
    """保存上传配置并重新加载调度任务"""
    from app.upload_config import save_upload_config as _save
    _save(config)
    await _sync_collect_enabled(config)
    from app.upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()
    logger.info("Upload config saved and jobs reloaded")
    return {"status": "success", "upload_config": config.model_dump()}


async def _sync_collect_enabled(config: UploadConfig) -> None:
    """将寄存器的采集启用状态同步到 DeviceConfig.registers"""
    from app.config import load_config, save_config
    from app.models import ModbusRegisterConfig

    app_config = load_config()
    synced_count = 0

    for system_code, devices in config.system_devices.items():
        for dev in devices:
            plc_name = dev.plc_device
            if not plc_name:
                continue

            device_cfg = next(
                (d for d in app_config.devices if d.name == plc_name), None
            )
            if device_cfg is None:
                continue

            for reg in dev.registers:
                existing_idx = next(
                    (i for i, r in enumerate(device_cfg.registers)
                     if r.name == reg.point_code),
                    None,
                )

                if reg.collect_enabled:
                    new_reg = ModbusRegisterConfig(
                        name=reg.point_code,
                        address=int(reg.register_address) if reg.register_address.isdigit() else 0,
                        count=1,
                        data_type=reg.data_type,
                        scale=1.0,
                        offset=0.0,
                        unit=reg.unit,
                    )
                    if existing_idx is not None:
                        device_cfg.registers[existing_idx] = new_reg
                    else:
                        device_cfg.registers.append(new_reg)
                    synced_count += 1
                else:
                    if existing_idx is not None:
                        device_cfg.registers.pop(existing_idx)

    save_config(app_config)
    if synced_count > 0:
        logger.info("Synced %d register(s) to DeviceConfig", synced_count)


@router.get("/tasks")
async def list_upload_tasks():
    """获取所有上传任务"""
    from app.upload_config import load_upload_config
    config = load_upload_config()
    return {"tasks": [t.model_dump() for t in config.tasks]}


@router.post("/tasks")
async def add_upload_task(task: UploadTask):
    """添加上传任务"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    if any(t.task_id == task.task_id for t in config.tasks):
        raise HTTPException(status_code=400, detail="任务ID已存在")

    config.tasks.append(task)
    save_upload_config(config)

    from app.upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()

    return {"status": "success", "task": task.model_dump()}


@router.put("/tasks/{task_id}")
async def update_upload_task(task_id: str, task: UploadTask):
    """更新上传任务"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    idx = next((i for i, t in enumerate(config.tasks) if t.task_id == task_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    config.tasks[idx] = task
    save_upload_config(config)

    from app.upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()

    return {"status": "success", "task": task.model_dump()}


@router.delete("/tasks/{task_id}")
async def delete_upload_task(task_id: str):
    """删除上传任务"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    original_len = len(config.tasks)
    config.tasks = [t for t in config.tasks if t.task_id != task_id]

    if len(config.tasks) == original_len:
        raise HTTPException(status_code=404, detail="任务不存在")

    save_upload_config(config)

    from app.upload_scheduler import reload_upload_jobs
    await reload_upload_jobs()

    return {"status": "success"}


@router.get("/systems")
async def list_system_devices():
    """获取所有系统的设备配置"""
    from app.upload_config import load_upload_config
    config = load_upload_config()
    return {"system_devices": config.system_devices}


@router.get("/systems/{system_code}")
async def get_system_devices(system_code: str):
    """获取指定系统的设备列表"""
    from app.upload_config import load_upload_config
    config = load_upload_config()
    devices = config.system_devices.get(system_code, [])
    return {"devices": [d.model_dump() for d in devices]}


@router.post("/systems/{system_code}/devices")
async def add_system_device(system_code: str, device: DeviceWithRegisters):
    """为系统添加设备"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    if system_code not in config.system_devices:
        config.system_devices[system_code] = []

    devices = config.system_devices[system_code]
    if any(d.device_name == device.device_name for d in devices):
        raise HTTPException(status_code=400, detail="设备名称已存在")

    devices.append(device)
    save_upload_config(config)

    return {"status": "success", "device": device.model_dump()}


@router.put("/systems/{system_code}/devices/{device_name}")
async def update_system_device(system_code: str, device_name: str, device: DeviceWithRegisters):
    """更新系统设备"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    idx = next((i for i, d in enumerate(devices) if d.device_name == device_name), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    devices[idx] = device
    save_upload_config(config)

    return {"status": "success", "device": device.model_dump()}


@router.delete("/systems/{system_code}/devices/{device_name}")
async def delete_system_device(system_code: str, device_name: str):
    """删除系统设备"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    original_len = len(devices)
    config.system_devices[system_code] = [
        d for d in devices if d.device_name != device_name
    ]

    if len(config.system_devices[system_code]) == original_len:
        raise HTTPException(status_code=404, detail="设备不存在")

    save_upload_config(config)
    return {"status": "success"}


@router.get("/systems/{system_code}/devices/{device_name}/registers")
async def list_registers(system_code: str, device_name: str):
    """获取设备的寄存器列表"""
    from app.upload_config import load_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    return {"registers": [r.model_dump() for r in device.registers]}


@router.post("/systems/{system_code}/devices/{device_name}/registers")
async def add_register(system_code: str, device_name: str, register: RegisterPoint):
    """为设备添加寄存器"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    if any(r.point_code == register.point_code for r in device.registers):
        raise HTTPException(status_code=400, detail="测点编码已存在")

    device.registers.append(register)
    save_upload_config(config)

    return {"status": "success", "register": register.model_dump()}


@router.put("/systems/{system_code}/devices/{device_name}/registers/{point_code}")
async def update_register(system_code: str, device_name: str, point_code: str, register: RegisterPoint):
    """更新寄存器"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    idx = next((i for i, r in enumerate(device.registers) if r.point_code == point_code), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="测点不存在")

    device.registers[idx] = register
    save_upload_config(config)

    return {"status": "success", "register": register.model_dump()}


@router.delete("/systems/{system_code}/devices/{device_name}/registers/{point_code}")
async def delete_register(system_code: str, device_name: str, point_code: str):
    """删除寄存器"""
    from app.upload_config import load_upload_config, save_upload_config
    config = load_upload_config()

    devices = config.system_devices.get(system_code, [])
    device = next((d for d in devices if d.device_name == device_name), None)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    original_len = len(device.registers)
    device.registers = [r for r in device.registers if r.point_code != point_code]

    if len(device.registers) == original_len:
        raise HTTPException(status_code=404, detail="测点不存在")

    save_upload_config(config)
    return {"status": "success"}


@router.post("/execute/{task_id}")
async def execute_upload_task(task_id: str):
    """手动触发执行上传任务"""
    from app.upload_config import load_upload_config
    from app.upload_scheduler import execute_upload_task as _execute

    config = load_upload_config()
    task = next((t for t in config.tasks if t.task_id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    await _execute(task)
    return {"status": "success", "message": f"任务 {task_id} 已执行"}