"""APScheduler-based device data collection scheduler."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.collectors.base import DataPoint
from app.collectors.modbus_collector import ModbusCollector
from app.collectors.s7_collector import S7Collector
from app.config import load_config
from app.models import DeviceConfig, DeviceType

logger = logging.getLogger(__name__)

# Resolve data directory relative to the project root (parent of app/)
_PROJECT_ROOT = Path(__file__).parent.parent

_scheduler: AsyncIOScheduler | None = None
_collectors: dict[str, ModbusCollector | S7Collector] = {}

# Runtime device status tracking
_device_status: dict[str, dict] = {}


def _create_collector(device: DeviceConfig) -> ModbusCollector | S7Collector:
    """Instantiate the appropriate collector for a device."""
    if device.device_type == DeviceType.MODBUS_TCP:
        return ModbusCollector(device)
    if device.device_type == DeviceType.S7:
        return S7Collector(device)
    raise ValueError(f"Unknown device type: {device.device_type}")


def _format_datapoints(datapoints: list[DataPoint]) -> str:
    """Format data points as human-readable lines."""
    lines = []
    for dp in datapoints:
        if dp.quality == "bad":
            lines.append(f"{dp.name} = <READ_ERROR>")
        else:
            unit = f" {dp.unit}" if dp.unit else ""
            lines.append(f"{dp.name} = {dp.value}{unit}")
    return "\n".join(lines)


def get_device_statuses() -> dict[str, dict]:
    """Return per-device runtime status for API consumption."""
    config = load_config()
    result = {}
    for device in config.devices:
        status = _device_status.get(device.name, {})
        result[device.name] = {
            "name": device.name,
            "online": status.get("online", False),
            "last_success": status.get("last_success"),
            "last_attempt": status.get("last_attempt"),
            "consecutive_failures": status.get("consecutive_failures", 0),
        }
    return result


def _update_device_status(device_name: str, online: bool) -> None:
    """Record the result of a poll attempt."""
    now = datetime.now().isoformat()
    prev = _device_status.get(device_name, {})
    failures = prev.get("consecutive_failures", 0)

    _device_status[device_name] = {
        "online": online,
        "last_attempt": now,
        "last_success": now if online else prev.get("last_success"),
        "consecutive_failures": 0 if online else failures + 1,
    }


async def _collect_and_write(device_name: str) -> None:
    """Async job: connect → poll → write data → disconnect.

    Runs directly on the event loop (AsyncIOScheduler detects the coroutine).
    Each cycle creates a fresh TCP connection to avoid stale links.
    """
    collector = _collectors.get(device_name)
    if collector is None:
        logger.error("No collector found for device '%s'", device_name)
        return

    # Always start with a fresh connection
    try:
        await collector.disconnect()
    except Exception:
        pass

    connected = await collector.connect()
    if not connected:
        _update_device_status(device_name, False)
        logger.warning("Failed to connect to device '%s', skipping poll", device_name)
        return

    try:
        datapoints = await collector.poll()
    except Exception:
        _update_device_status(device_name, False)
        logger.exception("Error polling device '%s'", device_name)
        datapoints = []
    finally:
        try:
            await collector.disconnect()
        except Exception:
            pass

    if not datapoints:
        _update_device_status(device_name, False)
        logger.debug("No data points from device '%s'", device_name)
        return

    _update_device_status(device_name, True)

    config = load_config()
    data_dir = _PROJECT_ROOT / config.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    file_path = data_dir / f"{device_name}_{datetime.now().strftime('%Y-%m-%d')}.txt"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = f"=== 设备: {device_name} | 时间: {now} ===\n"
    block += _format_datapoints(datapoints) + "\n"

    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(block)
        logger.info("Wrote %d data points for '%s' to %s", len(datapoints), device_name, file_path)
    except OSError:
        logger.exception("Failed to write data file for '%s'", device_name)


async def add_device_job(device_name: str) -> None:
    """Create a collector and schedule a polling job for a device."""
    global _collectors

    config = load_config()
    device = next((d for d in config.devices if d.name == device_name), None)
    if device is None:
        logger.error("Device '%s' not found in config", device_name)
        return

    schedule = next(
        (s for s in config.schedules if s.device_name == device_name and s.enabled),
        None,
    )
    if schedule is None:
        logger.info("No enabled schedule for device '%s', skipping", device_name)
        return

    if _scheduler is None:
        logger.error("Scheduler not running")
        return

    # Remove existing job if present
    remove_device_job(device_name)

    try:
        collector = _create_collector(device)
        _collectors[device_name] = collector
    except ValueError:
        logger.exception("Cannot create collector for '%s'", device_name)
        return

    job_id = f"poll_{device_name}"
    _scheduler.add_job(
        _collect_and_write,
        "interval",
        seconds=schedule.interval_seconds,
        args=[device_name],
        id=job_id,
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(),
    )
    logger.info(
        "Scheduled polling job for '%s' every %ds", device_name, schedule.interval_seconds
    )


def remove_device_job(device_name: str) -> None:
    """Remove the polling job and disconnect the collector for a device."""
    job_id = f"poll_{device_name}"
    if _scheduler is not None:
        try:
            _scheduler.remove_job(job_id)
            logger.info("Removed polling job for '%s'", device_name)
        except LookupError:
            pass

    collector = _collectors.pop(device_name, None)
    if collector is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(collector.disconnect())
        except RuntimeError:
            asyncio.run(collector.disconnect())


async def reload_jobs() -> None:
    """Reload all jobs from the current config, adding/removing as needed."""
    config = load_config()
    device_names = {d.name for d in config.devices if d.enabled}
    scheduled_names = {s.device_name for s in config.schedules if s.enabled}
    active_names = device_names & scheduled_names

    # Remove jobs for devices no longer active
    current_jobs = set(_collectors.keys())
    for name in current_jobs - active_names:
        remove_device_job(name)

    # Add or refresh jobs for active devices
    for name in active_names:
        await add_device_job(name)

    logger.info("Reloaded %d device job(s)", len(active_names))


async def start_scheduler() -> None:
    """Start the APScheduler instance and load all device jobs."""
    global _scheduler

    if _scheduler is not None:
        logger.warning("Scheduler already running")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    logger.info("Scheduler started")

    await reload_jobs()


async def stop_scheduler() -> None:
    """Stop the scheduler and disconnect all collectors."""
    global _scheduler

    if _scheduler is None:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None

    # Disconnect all collectors
    for name, collector in list(_collectors.items()):
        try:
            await collector.disconnect()
        except Exception:
            logger.exception("Error disconnecting collector '%s'", name)
    _collectors.clear()

    logger.info("Scheduler stopped")
