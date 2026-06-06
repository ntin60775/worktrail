"""worktrail.tracker — time tracking, idle detection, and session management.

This module provides:

* :class:`TrackerEngine` — main tracking logic with session lifecycle
  (active → paused → ended), auto-pause on idle, and checkpoint recording
* :class:`IdleMonitor` — filesystem-based idle detection via mtime monitoring

All datetime values use ISO8601 UTC.
"""

from worktrail.tracker.engine import TrackerEngine
from worktrail.tracker.idle import IdleMonitor

__all__ = [
    "TrackerEngine",
    "IdleMonitor",
]
