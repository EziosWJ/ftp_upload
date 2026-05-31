"""Base collector interface for device communication."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DataPoint:
    """A single collected data value."""
    name: str
    value: Any
    timestamp: datetime = field(default_factory=datetime.now)
    unit: str = ""
    quality: str = "good"  # "good", "bad", "uncertain"


class BaseCollector(ABC):
    """Abstract base class for device collectors."""

    def __init__(self, device_config: Any):
        self.device_config = device_config
        self.logger = logging.getLogger(self.__class__.__name__)
        self._connected = False

    @property
    def device_name(self) -> str:
        return self.device_config.name

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the device. Returns True if successful."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        ...

    @abstractmethod
    async def poll(self) -> list[DataPoint]:
        """Poll the device and return collected data points."""
        ...

    @abstractmethod
    async def write_value(self, name: str, value: Any) -> bool:
        """Write a value to the device. Returns True if successful."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the device is reachable. Returns True if successful."""
        ...

    @property
    def is_connected(self) -> bool:
        return self._connected
