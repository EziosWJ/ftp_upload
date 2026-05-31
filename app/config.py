"""Configuration management - read/write config.json."""

import json
import logging
from pathlib import Path

from .models import AppConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent / "config.json"


def load_config() -> AppConfig:
    """Load configuration from config.json. Returns defaults if file doesn't exist."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return AppConfig(**data)
        except Exception as e:
            logger.error(f"Failed to load config: {e}, using defaults")
    return AppConfig()


def save_config(config: AppConfig) -> None:
    """Save configuration to config.json."""
    CONFIG_FILE.write_text(
        config.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info(f"Config saved to {CONFIG_FILE}")


def get_config() -> AppConfig:
    """Get current config (singleton-like wrapper)."""
    return load_config()


def update_config(config: AppConfig) -> None:
    """Save and return updated config."""
    save_config(config)
