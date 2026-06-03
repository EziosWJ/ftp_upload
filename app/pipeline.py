"""DataPipeline — orchestrates the collect → write → track-status cycle.

This module owns the per-device collector instances and delegates
status tracking to DeviceStatusTracker and persistence to a write callback.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.collectors import create_collector
from app.collectors.base import BaseCollector, DataPoint
from app.config import load_config
from app.models import DeviceConfig
from app.status_tracker import DeviceStatusTracker

logger = logging.getLogger(__name__)

# Resolve data directory relative to the project root (parent of app/)
_PROJECT_ROOT = Path(__file__).parent.parent


def format_datapoints(datapoints: list[DataPoint]) -> str:
    """Format data points as human-readable lines."""
    lines = []
    for dp in datapoints:
        if dp.quality == "bad":
            lines.append(f"{dp.name} = <READ_ERROR>")
        else:
            unit = f" {dp.unit}" if dp.unit else ""
            lines.append(f"{dp.name} = {dp.value}{unit}")
    return "\n".join(lines)


def file_writer(device_name: str, datapoints: list[DataPoint]) -> None:
    """Default write callback: append data points to a daily file."""
    config = load_config()
    data_dir = _PROJECT_ROOT / config.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    file_path = data_dir / f"{device_name}_{datetime.now().strftime('%Y-%m-%d')}.txt"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = f"=== 设备: {device_name} | 时间: {now} ===\n"
    block += format_datapoints(datapoints) + "\n"

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(block)


class DataPipeline:
    """Orchestrate connect → poll → write → status for a single device.

    Owns per-device collector instances. The write callback handles
    persistence; DeviceStatusTracker handles status recording.
    """

    def __init__(
        self,
        status_tracker: DeviceStatusTracker,
        write: Callable[[str, list[DataPoint]], None] = file_writer,
    ) -> None:
        self._status = status_tracker
        self._write = write
        self._collectors: dict[str, BaseCollector] = {}

    def add_device(self, device: DeviceConfig) -> None:
        """Create and cache a collector for a device."""
        collector = create_collector(device)
        self._collectors[device.name] = collector

    def remove_device(self, device_name: str) -> BaseCollector | None:
        """Remove and return the collector for a device."""
        return self._collectors.pop(device_name, None)

    async def poll_device(self, device_name: str) -> None:
        """Single poll cycle: connect → poll → write → update status."""
        collector = self._collectors.get(device_name)
        if collector is None:
            logger.error("No collector for device '%s'", device_name)
            return

        # Always start with a fresh connection
        try:
            await collector.disconnect()
        except Exception:
            pass

        connected = await collector.connect()
        if not connected:
            self._status.record_result(device_name, False)
            logger.warning("Failed to connect to '%s', skipping poll", device_name)
            return

        try:
            datapoints = await collector.poll()
        except Exception:
            self._status.record_result(device_name, False)
            logger.exception("Error polling device '%s'", device_name)
            datapoints = []
        finally:
            try:
                await collector.disconnect()
            except Exception:
                pass

        if not datapoints:
            self._status.record_result(device_name, False)
            logger.debug("No data points from device '%s'", device_name)
            return

        self._status.record_result(device_name, True)

        try:
            self._write(device_name, datapoints)
            logger.info("Wrote %d data points for '%s'", len(datapoints), device_name)
        except OSError:
            logger.exception("Failed to write data for '%s'", device_name)

    def get_device_statuses(self) -> dict[str, dict]:
        """Return per-device runtime status for API consumption."""
        config = load_config()
        result = {}
        for device in config.devices:
            status = self._status.get_status(device.name)
            result[device.name] = {
                "name": device.name,
                "online": status.get("online", False),
                "last_success": status.get("last_success"),
                "last_attempt": status.get("last_attempt"),
                "consecutive_failures": status.get("consecutive_failures", 0),
            }
        return result

    async def shutdown(self) -> None:
        """Disconnect all collectors."""
        for name, collector in list(self._collectors.items()):
            try:
                await collector.disconnect()
            except Exception:
                logger.warning("Error disconnecting collector '%s'", name)
        self._collectors.clear()
