"""Device runtime status tracking — independent of scheduler and collectors."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DeviceStatusTracker:
    """Track per-device online/offline status across poll cycles."""

    def __init__(self) -> None:
        self._status: dict[str, dict] = {}

    def record_result(self, device_name: str, online: bool) -> None:
        """Record the outcome of a single poll attempt."""
        now = datetime.now().isoformat()
        prev = self._status.get(device_name, {})
        failures = prev.get("consecutive_failures", 0)

        self._status[device_name] = {
            "online": online,
            "last_attempt": now,
            "last_success": now if online else prev.get("last_success"),
            "consecutive_failures": 0 if online else failures + 1,
        }

    def get_status(self, device_name: str) -> dict:
        """Return status for a single device."""
        return self._status.get(device_name, {
            "online": False,
            "last_success": None,
            "last_attempt": None,
            "consecutive_failures": 0,
        })

    def get_all(self) -> dict[str, dict]:
        """Return status for all tracked devices."""
        return dict(self._status)
