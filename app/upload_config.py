"""上传配置管理 — 读写 upload_config.json"""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from .models import UploadConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent / "upload_config.json"

_cache: tuple[UploadConfig, float] | None = None


def load_upload_config() -> UploadConfig:
    """加载上传配置，文件不存在时返回空配置"""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return UploadConfig(**data)
        except json.JSONDecodeError as e:
            logger.error(f"Upload config file is not valid JSON: {e}")
        except ValidationError as e:
            logger.error(f"Upload config validation failed: {e}")
        except OSError as e:
            logger.error(f"Failed to read upload config file: {e}")
    return UploadConfig()


def get_upload_config() -> UploadConfig:
    """获取缓存的配置，仅在文件变更时重新加载"""
    global _cache
    current_mtime = CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0

    if _cache is not None:
        cached_config, cached_mtime = _cache
        if current_mtime == cached_mtime:
            return cached_config

    config = load_upload_config()
    _cache = (config, current_mtime)
    return config


def save_upload_config(config: UploadConfig) -> None:
    """保存上传配置到文件并更新缓存"""
    global _cache
    try:
        CONFIG_FILE.write_text(
            config.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info(f"Upload config saved to {CONFIG_FILE}")
        _cache = (config, CONFIG_FILE.stat().st_mtime)
    except OSError as e:
        logger.error(f"Failed to write upload config file: {e}")
        raise


def update_upload_config(config: UploadConfig) -> None:
    """保存并返回更新后的配置"""
    save_upload_config(config)
