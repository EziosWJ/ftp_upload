"""Async FTP upload module for pushing data files to a remote FTP server."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import aioftp

from app.config import load_config
from app.models import FtpConfig

logger = logging.getLogger(__name__)

_upload_task: asyncio.Task | None = None
_shutdown_event: asyncio.Event | None = None
_state_file: Path | None = None

# Runtime upload tracking
_upload_status: dict = {
    "running": False,
    "last_upload_time": None,
    "last_upload_files": [],
    "total_uploads": 0,
}
_upload_history: list[dict] = []


def _load_uploaded_set() -> set[str]:
    """从持久化文件加载已上传文件列表（断点续传）"""
    if _state_file and _state_file.exists():
        try:
            data = json.loads(_state_file.read_text(encoding="utf-8"))
            return set(data.get("uploaded", []))
        except Exception:
            logger.warning("Failed to load upload state, starting fresh")
    return set()


def _save_uploaded_set(uploaded: set[str]) -> None:
    """持久化已上传文件列表"""
    if _state_file:
        try:
            _state_file.write_text(
                json.dumps({"uploaded": list(uploaded)}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Failed to save upload state")


def get_upload_status() -> dict:
    """Return current FTP upload runtime status."""
    config = load_config()
    data_dir = Path(config.data_dir)
    uploaded = _load_uploaded_set()
    pending_count = 0
    if data_dir.is_dir():
        pending_count = len([
            p for p in data_dir.glob("*.txt") if p.name not in uploaded
        ])
    return {
        "running": _upload_task is not None and not _upload_task.done(),
        "last_upload_time": _upload_status["last_upload_time"],
        "last_upload_files": _upload_status["last_upload_files"],
        "total_uploads": _upload_status["total_uploads"],
        "pending_files": pending_count,
        "history": _upload_history[-20:],
    }


async def test_ftp_connection(config: FtpConfig) -> tuple[bool, str]:
    """Test connectivity to the FTP server.

    Returns (success, message).
    """
    if not config.host:
        return False, "FTP host is not configured"

    try:
        async with aioftp.Client.context(
            host=config.host,
            port=config.port,
            user=config.username or "anonymous",
            password=config.password or "",
        ) as client:
            await client.change_directory(config.remote_dir)
            return True, f"Connected to {config.host}:{config.port}"
    except Exception as exc:
        logger.error("FTP connection test failed: %s", exc)
        return False, f"Connection failed: {exc}"


async def upload_pending_files(config: FtpConfig, data_dir: str) -> list[str]:
    """Upload all data files that haven't been uploaded yet.

    Returns a list of filenames that were successfully uploaded.
    """
    if not config.host:
        logger.warning("FTP host not configured, skipping upload")
        return []

    data_path = Path(data_dir)
    if not data_path.is_dir():
        logger.warning("Data directory '%s' does not exist", data_dir)
        return []

    uploaded_set = _load_uploaded_set()

    # Collect .txt files that haven't been uploaded
    pending = [
        p for p in sorted(data_path.glob("*.txt"))
        if p.name not in uploaded_set
    ]

    if not pending:
        logger.debug("No pending files to upload")
        return []

    uploaded: list[str] = []

    try:
        async with aioftp.Client.context(
            host=config.host,
            port=config.port,
            user=config.username or "anonymous",
            password=config.password or "",
        ) as client:
            remote_dir = config.remote_dir.rstrip("/")
            try:
                await client.change_directory(remote_dir)
            except Exception:
                logger.info("Creating remote directory '%s'", remote_dir)
                await client.make_directory(remote_dir)
                await client.change_directory(remote_dir)

            for file_path in pending:
                try:
                    remote_path = file_path.name
                    async with client.upload_stream(remote_path) as stream:
                        with open(file_path, "rb") as f:
                            while True:
                                chunk = f.read(8192)
                                if not chunk:
                                    break
                                await stream.write(chunk)
                    uploaded_set.add(file_path.name)
                    uploaded.append(file_path.name)
                    _upload_history.append({
                        "file": file_path.name,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "success",
                        "size": file_path.stat().st_size,
                    })
                    logger.info("Uploaded '%s' to %s", file_path.name, remote_dir)
                except Exception as e:
                    _upload_history.append({
                        "file": file_path.name,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "failed",
                        "error": str(e),
                    })
                    logger.exception("Failed to upload '%s'", file_path.name)

    except Exception:
        logger.exception("FTP connection error during upload")

    # 持久化已上传列表（断点续传）
    if uploaded:
        _save_uploaded_set(uploaded_set)
        _upload_status["last_upload_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _upload_status["last_upload_files"] = uploaded
        _upload_status["total_uploads"] += len(uploaded)

    return uploaded


async def _upload_loop() -> None:
    """Periodically check for and upload pending data files."""
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    while True:
        config = load_config()
        if not config.ftp.enabled or not config.ftp.host:
            logger.debug("FTP upload disabled, waiting...")
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=30.0)
                break
            except asyncio.TimeoutError:
                continue

        uploaded = await upload_pending_files(config.ftp, config.data_dir)
        if uploaded:
            logger.info("Batch upload complete: %d file(s)", len(uploaded))

        try:
            await asyncio.wait_for(
                _shutdown_event.wait(),
                timeout=config.ftp.upload_interval_seconds,
            )
            break  # shutdown requested
        except asyncio.TimeoutError:
            pass  # time to upload again


async def start_ftp_uploader() -> None:
    """Start the periodic FTP upload background task."""
    global _upload_task, _state_file

    if _upload_task is not None and not _upload_task.done():
        logger.warning("FTP uploader already running")
        return

    config = load_config()
    if not config.ftp.enabled:
        logger.info("FTP upload is disabled in config")
        return

    # 初始化断点续传状态文件
    _state_file = Path(config.data_dir) / ".upload_state.json"
    uploaded_set = _load_uploaded_set()
    logger.info("Upload state loaded: %d files already uploaded", len(uploaded_set))

    _upload_task = asyncio.create_task(_upload_loop())
    _upload_status["running"] = True
    logger.info("FTP uploader started (interval: %ds)", config.ftp.upload_interval_seconds)


async def stop_ftp_uploader() -> None:
    """Stop the periodic FTP upload task."""
    global _upload_task

    if _shutdown_event is not None:
        _shutdown_event.set()

    if _upload_task is not None and not _upload_task.done():
        _upload_task.cancel()
        try:
            await _upload_task
        except asyncio.CancelledError:
            pass
        logger.info("FTP uploader stopped")

    _upload_task = None
    _upload_status["running"] = False
