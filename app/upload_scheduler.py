"""上传任务调度器 — 管理定时报文生成任务

职责（由 UploadExecutor 深化后变得集中）：
- 根据 UploadConfig.tasks 注册/注销 APScheduler 定时任务
- 任务触发时调用 UploadExecutor.execute()

真正的执行逻辑（采集→格式化→写文件）封装在 app/upload_executor.py 中。
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.models import ScheduleType, UploadTask

from .upload_executor import (
    CollectorPool, ConfigSystemInfoProvider, JsonFileConfigReader,
    LocalFileWriter, UploadExecutor,
)
from .formatter import _header
from .upload_config import load_upload_config

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_executor: UploadExecutor | None = None


def _build_trigger(task: UploadTask):
    """根据任务配置构建 APScheduler trigger"""
    if task.schedule_type == ScheduleType.INTERVAL_MINUTES:
        return IntervalTrigger(minutes=max(1, task.interval_value))
    elif task.schedule_type == ScheduleType.INTERVAL_HOURS:
        return IntervalTrigger(hours=max(1, task.interval_value))
    elif task.schedule_type == ScheduleType.DAILY:
        return CronTrigger(hour=task.hour, minute=task.minute)
    elif task.schedule_type == ScheduleType.WEEKLY:
        return CronTrigger(
            day_of_week=task.weekday if task.weekday is not None else 0,
            hour=task.hour,
            minute=task.minute,
        )
    else:
        logger.error("Unknown schedule type: %s", task.schedule_type)
        return None


async def reload_upload_jobs() -> None:
    """重新加载所有上传任务"""
    if _scheduler is None:
        logger.error("Upload scheduler not running")
        return

    upload_cfg = load_upload_config()

    existing_jobs = [j.id for j in _scheduler.get_jobs() if j.id.startswith("upload_")]
    for job_id in existing_jobs:
        _scheduler.remove_job(job_id)

    count = 0
    for task in upload_cfg.tasks:
        if not task.enabled:
            continue

        trigger = _build_trigger(task)
        if trigger is None:
            continue

        job_id = f"upload_{task.task_id}"
        _scheduler.add_job(
            _execute_task,
            trigger=trigger,
            args=[task],
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )
        count += 1
        logger.info("Scheduled upload job: %s", task.task_id)

    logger.info("Reloaded %d upload job(s)", count)


async def _execute_task(task: UploadTask) -> None:
    """Wrapper: delegate to UploadExecutor."""
    if _executor is not None:
        await _executor.execute(task)


async def start_upload_scheduler() -> None:
    """启动上传调度器"""
    global _scheduler, _executor

    if _scheduler is not None:
        logger.warning("Upload scheduler already running")
        return

    config_reader = JsonFileConfigReader()
    collector_pool = CollectorPool()
    system_info_provider = ConfigSystemInfoProvider(config_reader)
    file_writer = LocalFileWriter(config_reader)

    _executor = UploadExecutor(
        config_reader=config_reader,
        collector_pool=collector_pool,
        system_info_provider=system_info_provider,
        file_writer=file_writer,
        format_header_fn=_header,
    )

    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    logger.info("Upload scheduler started")

    await reload_upload_jobs()


async def stop_upload_scheduler() -> None:
    """停止上传调度器"""
    global _scheduler, _executor

    if _scheduler is None:
        return

    _scheduler.shutdown(wait=False)
    _scheduler = None

    if _executor is not None:
        await _executor.shutdown()
        _executor = None

    logger.info("Upload scheduler stopped")