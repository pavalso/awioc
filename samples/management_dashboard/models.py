"""Data models for the management dashboard."""

import logging
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Deque, Dict, List, Optional


@dataclass
class ComponentState:
    """Snapshot of a component's state."""
    is_initialized: bool
    is_initializing: bool
    is_shutting_down: bool

    def __eq__(self, other):
        if not isinstance(other, ComponentState):
            return False
        return (
                self.is_initialized == other.is_initialized and
                self.is_initializing == other.is_initializing and
                self.is_shutting_down == other.is_shutting_down
        )

    def get_status_label(self) -> str:
        """Get a human-readable status label."""
        if self.is_shutting_down:
            return "shutting_down"
        elif self.is_initializing:
            return "initializing"
        elif self.is_initialized:
            return "active"
        else:
            return "inactive"


@dataclass
class LogEntry:
    """A single log entry."""
    id: int
    timestamp: float
    level: str
    logger_name: str
    message: str
    source: str = "unknown"  # app, plugin, library, or framework
    component: str = "unknown"  # component name

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "logger_name": self.logger_name,
            "message": self.message,
            "source": self.source,
            "component": self.component,
        }


class LogBuffer:
    """Thread-safe circular buffer for log entries."""

    def __init__(self, max_size: int = 500):
        self._buffer: Deque[LogEntry] = deque(maxlen=max_size)
        self._lock = Lock()
        self._id_counter = 0
        self._component_info: Dict[str, tuple] = {}

    def set_component_info(self, component_info: Dict[str, tuple]):
        """Set the mapping of module names to (display_name, type)."""
        with self._lock:
            self._component_info = component_info.copy()

    def add(self, level: str, logger_name: str, message: str) -> LogEntry:
        """Add a log entry and return it."""
        with self._lock:
            self._id_counter += 1
            source, component = self._parse_logger_name(logger_name)
            entry = LogEntry(
                id=self._id_counter,
                timestamp=time.time(),
                level=level,
                logger_name=logger_name,
                message=message,
                source=source,
                component=component,
            )
            self._buffer.append(entry)
            return entry

    def _parse_logger_name(self, logger_name: str) -> tuple:
        """Parse logger name to determine source and component."""
        logger_lower = logger_name.lower()

        # Check for framework logs first
        if "awioc" in logger_lower:
            return "framework", "awioc"

        # Try to match logger name against registered module names
        for module_name, (display_name, comp_type) in self._component_info.items():
            module_lower = module_name.lower()
            if module_lower in logger_lower or logger_lower.endswith(module_lower):
                return comp_type, display_name
            module_last = module_lower.rsplit('.', 1)[-1]
            if module_last in logger_lower:
                return comp_type, display_name

        # Default - extract component name from logger path
        parts = logger_name.split(".")
        return "unknown", parts[-1] if parts else logger_name

    def get_all(self) -> List[dict]:
        """Get all log entries as dicts."""
        with self._lock:
            return [entry.to_dict() for entry in self._buffer]

    def get_since(self, last_id: int) -> List[dict]:
        """Get log entries since a given ID."""
        with self._lock:
            return [entry.to_dict() for entry in self._buffer if entry.id > last_id]

    def clear(self):
        """Clear all log entries."""
        with self._lock:
            self._buffer.clear()


class DashboardLogHandler(logging.Handler):
    """Custom logging handler that captures logs for the dashboard."""

    def __init__(
            self,
            log_buffer: LogBuffer,
            broadcast_callback: Optional[Callable[[LogEntry], None]] = None
    ):
        super().__init__()
        self._log_buffer = log_buffer
        self._broadcast_callback = broadcast_callback
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord):
        try:
            message = self.format(record)
            entry = self._log_buffer.add(
                level=record.levelname,
                logger_name=record.name,
                message=message,
            )
            if self._broadcast_callback:
                self._broadcast_callback(entry)
        except Exception:
            self.handleError(record)


# Global log buffer instance
log_buffer = LogBuffer()
