"""APScheduler-based device data collection scheduler.

This module only owns the APScheduler instance and job lifecycle.
All collection logic lives in DataPipeline; status tracking in DeviceStatusTracker.
"""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import load_config
from app.pipeline import DataPipeline

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_pipeline: DataPipeline | None = None


def set_pipeline(pipeline: DataPipeline) -> None:
    """Inject the DataPipeline instance (called from server startup)."""
    global _pipeline
    _pipeline = pipeline


async def add_device_job(device_name: str) -> None:
    """Register a polling job for a device."""
    if _scheduler is None:
        logger.error("Scheduler not running")
        return
    if _pipeline is None:
        logger.error("DataPipeline not set")
        return

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
        logger.info("No enabled schedule for '%s', skipping", device_name)
        return

    # Remove existing job if present
    remove_device_job(device_name)

    try:
        _pipeline.add_device(device)
    except ValueError:
        logger.exception("Cannot create collector for '%s'", device_name)
        return

    job_id = f"poll_{device_name}"
    _scheduler.add_job(
        _pipeline.poll_device,
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

    if _pipeline is not None:
        collector = _pipeline.remove_device(device_name)
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
    if _pipeline is not None:
        current_jobs = set(_pipeline._collectors.keys())
    else:
        current_jobs = set()

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

    if _pipeline is not None:
        await _pipeline.shutdown()

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
