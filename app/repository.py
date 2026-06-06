"""Generic CRUD repository for config-backed resources."""

import logging
from typing import Generic, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel

from .config import get_config, load_config, save_config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class CrudRepository(Generic[T]):
    """Encapsulates load → find → mutate → save for a list inside AppConfig.

    Usage:
        repo = CrudRepository("basic_devices", "device_name", DeviceBasicInfo)
        items = repo.list()
        repo.add(item)
        repo.update("key_value", item)
        repo.delete("key_value")
    """

    def __init__(self, config_attr: str, key_field: str, model_cls: type[T],
                 not_found_msg: str = "记录不存在", duplicate_msg: str = "记录已存在"):
        self.config_attr = config_attr
        self.key_field = key_field
        self.model_cls = model_cls
        self.not_found_msg = not_found_msg
        self.duplicate_msg = duplicate_msg

    def _get_list(self, config) -> list[T]:
        return getattr(config, self.config_attr)

    def _get_key(self, item: T):
        return getattr(item, self.key_field)

    def list(self) -> list[T]:
        config = get_config()
        return self._get_list(config)

    def get(self, key_value) -> T | None:
        config = get_config()
        return next(
            (item for item in self._get_list(config) if self._get_key(item) == key_value),
            None,
        )

    def add(self, item: T) -> T:
        config = load_config()
        items = self._get_list(config)

        if any(self._get_key(i) == self._get_key(item) for i in items):
            raise HTTPException(status_code=400, detail=self.duplicate_msg)

        items.append(item)
        save_config(config)
        logger.info(f"Added {self.config_attr}: {self._get_key(item)}")
        return item

    def update(self, key_value, item: T) -> T:
        config = load_config()
        items = self._get_list(config)

        idx = next(
            (i for i, x in enumerate(items) if self._get_key(x) == key_value),
            None,
        )
        if idx is None:
            raise HTTPException(status_code=404, detail=self.not_found_msg)

        items[idx] = item
        save_config(config)
        logger.info(f"Updated {self.config_attr}: {key_value}")
        return item

    def delete(self, key_value) -> None:
        config = load_config()
        items = self._get_list(config)
        original_len = len(items)

        setattr(config, self.config_attr,
                [x for x in items if self._get_key(x) != key_value])

        if len(getattr(config, self.config_attr)) == original_len:
            raise HTTPException(status_code=404, detail=self.not_found_msg)

        save_config(config)
        logger.info(f"Deleted {self.config_attr}: {key_value}")
