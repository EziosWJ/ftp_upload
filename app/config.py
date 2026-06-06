"""Configuration management - read/write config.json."""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from .models import AppConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

_cache: tuple[AppConfig, float] | None = None


def load_config() -> AppConfig:
    """Load configuration from config.json. Returns defaults if file doesn't exist."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return AppConfig(**data)
        except json.JSONDecodeError as e:
            logger.error(f"Config file is not valid JSON: {e}")
        except ValidationError as e:
            logger.error(f"Config validation failed: {e}")
        except OSError as e:
            logger.error(f"Failed to read config file: {e}")
    return AppConfig()


def get_config() -> AppConfig:
    """Get cached config, reloading only if file changed."""
    global _cache
    current_mtime = CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0

    if _cache is not None:
        cached_config, cached_mtime = _cache
        if current_mtime == cached_mtime:
            return cached_config

    config = load_config()
    _cache = (config, current_mtime)
    return config


def save_config(config: AppConfig) -> None:
    """Save configuration to config.json and update cache."""
    global _cache
    try:
        CONFIG_FILE.write_text(
            config.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info(f"Config saved to {CONFIG_FILE}")
        _cache = (config, CONFIG_FILE.stat().st_mtime)
    except OSError as e:
        logger.error(f"Failed to write config file: {e}")
        raise


def update_config(config: AppConfig) -> None:
    """Save and return updated config."""
    save_config(config)
