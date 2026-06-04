"""上传配置管理 — 读写 upload_config.json"""

import json
import logging
from pathlib import Path

from .models import UploadConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent / "upload_config.json"


def load_upload_config() -> UploadConfig:
    """加载上传配置，文件不存在时返回空配置"""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return UploadConfig(**data)
        except Exception as e:
            logger.error(f"Failed to load upload config: {e}, using defaults")
    return UploadConfig()


def save_upload_config(config: UploadConfig) -> None:
    """保存上传配置到文件"""
    CONFIG_FILE.write_text(
        config.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info(f"Upload config saved to {CONFIG_FILE}")


def get_upload_config() -> UploadConfig:
    """获取当前上传配置（单例封装）"""
    return load_upload_config()


def update_upload_config(config: UploadConfig) -> None:
    """保存并返回更新后的配置"""
    save_upload_config(config)
