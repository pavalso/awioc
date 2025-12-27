"""
Management Dashboard App Component

A web server that exposes endpoints for:
- Listing all activated components
- Enabling/disabling plugins
- Showing overall application state
- Real-time updates via WebSocket with component state monitoring
- Real-time log streaming with filtering
"""

import asyncio
import base64
import json
import logging
import sys
import time
import warnings
from collections import deque
from dataclasses import dataclass
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Lock
from typing import Any, Optional, Set, Dict, List, Deque
from urllib.parse import urlparse

import pydantic
import websockets
import yaml
from pydantic_core import PydanticUndefined
from websockets.server import WebSocketServerProtocol

from awioc import (
    get_config,
    get_logger,
    get_container_api,
    inject,
    ContainerInterface,
    component_internals,
    component_registration,
    initialize_components,
    shutdown_components,
    register_plugin,
    reconfigure_ioc_app,
    as_component,
)
from awioc.loader.module_loader import compile_component, _load_module


def _get_component_file(component) -> Optional[str]:
    """
    Get the file path for a component, handling both module-based and class-based components.

    For modules: returns module.__file__
    For class instances: returns the module file where the class is defined
    """
    # Try direct __file__ attribute (module-based components)
    if hasattr(component, '__file__'):
        return component.__file__

    # For class-based components (instances), get the class's module
    component_class = type(component)
    module_name = getattr(component_class, '__module__', None)

    if module_name and module_name in sys.modules:
        module = sys.modules[module_name]
        return getattr(module, '__file__', None)

    return None


def _scan_module_for_components(module_path: Path, logger=None) -> list[dict]:
    """
    Scan a module for classes that have __metadata__ attribute.

    Uses runtime inspection to correctly find classes that may be imported
    from submodules (e.g., HttpServerApp imported in __init__.py from http_server.py).

    Returns a list of dicts with class info:
    - class_name: the class name
    - metadata_name: name from __metadata__ if available
    - reference: the reference string to use for registration
    """
    import inspect
    import logging

    if logger is None:
        logger = logging.getLogger(__name__)

    components = []

    try:
        # Load the module at runtime to inspect it
        logger.debug(f"Loading module for inspection: {module_path}")
        module = _load_module(module_path)
        logger.debug(f"Module loaded successfully: {module}")

        # Also check __all__ if defined to prioritize exported names
        all_names = getattr(module, '__all__', None)
        names_to_check = all_names if all_names else dir(module)

        # Iterate over all attributes in the module
        for name in names_to_check:
            if name.startswith('_'):
                continue

            try:
                obj = getattr(module, name)
            except Exception as e:
                logger.debug(f"Could not get attribute {name}: {e}")
                continue

            # Check if it's a class with __metadata__
            if inspect.isclass(obj) and hasattr(obj, '__metadata__'):
                metadata = obj.__metadata__
                if isinstance(metadata, dict):
                    metadata_name = metadata.get("name")
                    logger.debug(f"Found component class: {name} ({metadata_name})")
                    components.append({
                        "class_name": name,
                        "metadata_name": metadata_name,
                        "reference": f":{name}()",
                    })

        # If no components found via __all__, also scan dir() as fallback
        if not components and all_names:
            for name in dir(module):
                if name.startswith('_') or name in all_names:
                    continue
                try:
                    obj = getattr(module, name)
                    if inspect.isclass(obj) and hasattr(obj, '__metadata__'):
                        metadata = obj.__metadata__
                        if isinstance(metadata, dict):
                            metadata_name = metadata.get("name")
                            logger.debug(f"Found component class (fallback): {name} ({metadata_name})")
                            components.append({
                                "class_name": name,
                                "metadata_name": metadata_name,
                                "reference": f":{name}()",
                            })
                except Exception:
                    continue

    except Exception as e:
        # If loading fails, fall back to AST parsing for basic detection
        logger.debug(f"Runtime inspection failed for {module_path}: {e}, falling back to AST")
        components = _scan_module_for_components_ast(module_path)

    return components


def _scan_module_for_components_ast(module_path: Path) -> list[dict]:
    """
    Fallback AST-based scanning for when runtime loading fails.
    Only detects classes defined directly in the file, not imported ones.
    """
    import ast

    components = []

    try:
        if module_path.is_dir():
            init_file = module_path / "__init__.py"
            if not init_file.exists():
                return components
            source_file = init_file
        else:
            source_file = module_path

        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                has_metadata = False
                metadata_name = None

                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "__metadata__":
                                has_metadata = True
                                if isinstance(item.value, ast.Dict):
                                    for key, value in zip(item.value.keys, item.value.values):
                                        if isinstance(key, ast.Constant) and key.value == "name":
                                            if isinstance(value, ast.Constant):
                                                metadata_name = value.value
                                break

                if has_metadata:
                    components.append({
                        "class_name": node.name,
                        "metadata_name": metadata_name,
                        "reference": f":{node.name}()",
                    })

    except Exception:
        pass

    return components


def _check_module_has_metadata(module_path: Path) -> bool:
    """Check if a module has module-level __metadata__."""
    try:
        # Try runtime inspection first
        module = _load_module(module_path)
        # Check for module-level __metadata__ (not on a class)
        if hasattr(module, '__metadata__'):
            import inspect
            # Make sure it's not a class attribute we're seeing
            metadata = getattr(module, '__metadata__')
            # If __metadata__ is directly on the module (not inherited from a class)
            if isinstance(metadata, dict):
                # Check if it's defined at module level by seeing if any class owns it
                for name in dir(module):
                    obj = getattr(module, name, None)
                    if inspect.isclass(obj) and hasattr(obj, '__metadata__'):
                        if obj.__metadata__ is metadata:
                            return False  # It belongs to a class
                return True
        return False
    except Exception:
        # Fallback to AST parsing
        return _check_module_has_metadata_ast(module_path)


def _check_module_has_metadata_ast(module_path: Path) -> bool:
    """Fallback AST-based check for module-level __metadata__."""
    import ast

    try:
        if module_path.is_dir():
            init_file = module_path / "__init__.py"
            if not init_file.exists():
                return False
            source_file = init_file
        else:
            source_file = module_path

        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__metadata__":
                        return True
    except Exception:
        pass

    return False


class DashboardConfig(pydantic.BaseModel):
    """Dashboard Server configuration."""
    __prefix__ = "dashboard"

    host: str = pydantic.Field(
        default="127.0.0.1",
        description="The hostname or IP address to bind the HTTP server to"
    )
    port: int = pydantic.Field(
        default=8090,
        description="The port number for the HTTP dashboard interface"
    )
    ws_port: int = pydantic.Field(
        default=8091,
        description="The port number for the WebSocket server (real-time updates)"
    )
    monitor_interval: float = pydantic.Field(
        default=0.25,
        description="How often to check for component state changes (in seconds)"
    )
    log_buffer_size: int = pydantic.Field(
        default=500,
        description="Maximum number of log entries to keep in memory for the UI"
    )
    plugin_upload_path: str = pydantic.Field(
        default="plugins",
        description="Directory path where uploaded plugins will be saved (relative to config file or absolute)"
    )


# Path to the web assets directory
WEB_DIR = Path(__file__).parent / "web"


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
        # module_name -> (display_name, type)
        self._component_info: Dict[str, tuple] = {}

    def set_component_info(self, component_info: Dict[str, tuple]):
        """Set the mapping of module names to (display_name, type)."""
        with self._lock:
            self._component_info = component_info.copy()

    def add(self, level: str, logger_name: str, message: str) -> LogEntry:
        """Add a log entry and return it."""
        with self._lock:
            self._id_counter += 1

            # Determine source and component from logger name
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
        # Logger names are like "awioc.samples.management_dashboard.management_dashboard"
        for module_name, (display_name, comp_type) in self._component_info.items():
            module_lower = module_name.lower()
            # Check if module name is contained in logger name
            if module_lower in logger_lower or logger_lower.endswith(module_lower):
                return comp_type, display_name
            # Also check last part of module name (e.g., "management_dashboard")
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

    def __init__(self, log_buffer: LogBuffer, broadcast_callback=None):
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

            # Trigger broadcast if callback is set
            if self._broadcast_callback:
                self._broadcast_callback(entry)
        except Exception:
            self.handleError(record)


# Global log buffer instance
log_buffer = LogBuffer()


class WebSocketManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        self._clients: Set[WebSocketServerProtocol] = set()
        self._container: Optional[ContainerInterface] = None
        self._lock = asyncio.Lock()
        self._previous_states: Dict[str, ComponentState] = {}
        self._monitoring = False
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._log_buffer: Optional[LogBuffer] = None
        self._plugin_upload_path: Optional[Path] = None
        self._discovered_plugins: Dict[str, dict] = {}  # path -> plugin info

    def set_container(self, container: ContainerInterface):
        self._container = container

    def set_plugin_upload_path(self, path: Path):
        """Set the plugin upload path for auto-sync."""
        self._plugin_upload_path = path

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the main event loop for scheduling lifecycle operations."""
        self._main_loop = loop

    def set_ws_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the WebSocket event loop for log broadcasting."""
        self._ws_loop = loop

    def set_log_buffer(self, buffer: LogBuffer):
        """Set the log buffer reference."""
        self._log_buffer = buffer

    def on_new_log(self, entry: LogEntry):
        """Callback when a new log entry is added. Schedules broadcast in WS loop."""
        if self._ws_loop and self._clients:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_log(entry),
                self._ws_loop
            )

    async def broadcast_log(self, entry: LogEntry):
        """Broadcast a single log entry to all connected clients."""
        message = {
            "type": "log",
            "entry": entry.to_dict(),
        }
        await self.broadcast(message)

    async def register(self, websocket: WebSocketServerProtocol):
        async with self._lock:
            self._clients.add(websocket)

    async def unregister(self, websocket: WebSocketServerProtocol):
        async with self._lock:
            self._clients.discard(websocket)

    @property
    def has_clients(self) -> bool:
        return len(self._clients) > 0

    def _get_component_state(self, component) -> ComponentState:
        """Get the current state of a component."""
        internals = component_internals(component)
        return ComponentState(
            is_initialized=internals.is_initialized,
            is_initializing=internals.is_initializing,
            is_shutting_down=internals.is_shutting_down,
        )

    def _get_component_info(self, component) -> dict:
        """Get information about a component."""
        internals = component_internals(component)
        metadata = component.__metadata__
        state = self._get_component_state(component)

        # Get configuration info
        config_info = self._get_component_config_info(component)

        # Get requires (dependencies)
        requires = metadata.get("requires", set())
        requires_names = [
            req.__metadata__.get("name", "unknown")
            for req in requires
        ]

        # Get registration info
        registration = component_registration(component)
        registration_info = None
        if registration:
            registration_info = {
                "registered_by": registration.registered_by,
                "registered_at": registration.registered_at.isoformat(),
                "file": registration.file,
                "line": registration.line,
            }

        return {
            "name": metadata.get("name", "unknown"),
            "version": metadata.get("version", "unknown"),
            "description": metadata.get("description", ""),
            "type": internals.type.value,
            "state": {
                "is_initialized": internals.is_initialized,
                "is_initializing": internals.is_initializing,
                "is_shutting_down": internals.is_shutting_down,
            },
            "status": state.get_status_label(),
            "required_by": [
                req.__metadata__.get("name", "unknown")
                for req in internals.required_by
            ],
            "config": config_info,
            "registration": registration_info,
            # Internal data
            "internals": {
                "module": getattr(component, "__name__", "unknown"),
                "wire": metadata.get("wire", False),
                "requires": requires_names,
                "initialized_by": [
                    req.__metadata__.get("name", "unknown")
                    for req in internals.initialized_by
                ],
            }
        }

    def _normalize_pydantic_schema(self, model: type[pydantic.BaseModel]) -> dict:
        # 1. Generate schema with a VALID ref_template
        # Suppress PydanticJsonSchemaWarning for non-serializable defaults
        # (we handle default injection manually below)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=pydantic.json_schema.PydanticJsonSchemaWarning)
            raw_schema = model.model_json_schema(ref_template="#/$defs/{model}")

        # 2. Get $defs for resolving references
        defs = raw_schema.get("$defs", {})

        # 3. Resolve top-level $ref if present
        if "$ref" in raw_schema:
            ref_name = raw_schema["$ref"].split("/")[-1]
            schema = defs.get(ref_name, {}).copy()
        else:
            schema = {k: v for k, v in raw_schema.items() if k != "$defs"}

        # 4. Recursively resolve all $ref in the schema
        schema = self._resolve_refs(schema, defs)

        # 5. Ensure required keys
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        schema.setdefault("required", [])

        # 6. Inject defaults in a JSON-safe way (for UI)
        for field_name, field in model.model_fields.items():
            prop = schema["properties"].get(field_name, {})

            default = field.default
            if default is not PydanticUndefined:
                try:
                    # For nested BaseModel defaults, convert to dict
                    if isinstance(default, pydantic.BaseModel):
                        default = default.model_dump()
                    # Only inject if JSON-serializable
                    json.dumps(default)
                    prop.setdefault("default", default)
                except TypeError:
                    # Fallback: stringify non-serializable defaults
                    prop.setdefault("default", str(default))

            schema["properties"][field_name] = prop

        return schema

    def _resolve_refs(self, obj: Any, defs: dict) -> Any:
        """Recursively resolve all $ref references in a schema."""
        if isinstance(obj, dict):
            # Handle allOf with single $ref (Pydantic pattern for nested models with defaults)
            if "allOf" in obj and isinstance(obj["allOf"], list):
                # Merge all schemas in allOf
                merged = {}
                for item in obj["allOf"]:
                    resolved_item = self._resolve_refs(item, defs)
                    if isinstance(resolved_item, dict):
                        # Deep merge properties
                        for k, v in resolved_item.items():
                            if k == "properties" and "properties" in merged:
                                merged["properties"].update(v)
                            elif k == "required" and "required" in merged:
                                merged["required"] = list(set(merged["required"]) | set(v))
                            else:
                                merged[k] = v
                # Also include any other keys from original obj (like default)
                for k, v in obj.items():
                    if k != "allOf" and k not in merged:
                        merged[k] = self._resolve_refs(v, defs)
                return merged

            # If this dict has a $ref, resolve it
            if "$ref" in obj:
                ref_path = obj["$ref"]
                if ref_path.startswith("#/$defs/"):
                    ref_name = ref_path.split("/")[-1]
                    resolved = defs.get(ref_name, {}).copy()
                    # Recursively resolve any refs in the resolved schema
                    resolved = self._resolve_refs(resolved, defs)
                    # Merge with any other keys in the original object
                    for k, v in obj.items():
                        if k != "$ref" and k not in resolved:
                            resolved[k] = self._resolve_refs(v, defs)
                    return resolved
                return obj

            # Otherwise, recursively process all values
            return {k: self._resolve_refs(v, defs) for k, v in obj.items() if k != "$defs"}

        elif isinstance(obj, list):
            return [self._resolve_refs(item, defs) for item in obj]

        return obj

    def _get_component_config_info(self, component) -> Optional[list[dict]]:
        """Get configuration info for a component.

        Returns a list of config info dicts, one for each configuration model.
        Each dict contains: prefix, values, and schema.
        """
        metadata = component.__metadata__
        config_model = metadata.get("config")

        if not config_model:
            return None

        # Normalize to a list of config models
        # Note: metadata() converts config to a set, so we need to handle sets too
        if isinstance(config_model, (list, tuple, set, frozenset)):
            config_models = list(config_model)
        else:
            config_models = [config_model]

        configs = []
        for idx, model in enumerate(config_models):
            prefix = getattr(model, "__prefix__", None)
            # Use model name as fallback if no prefix
            if not prefix:
                prefix = getattr(model, "__name__", f"config_{idx}")

            # Get the merged config values from awioc (includes YAML, .env, .{context}.env)
            values = {}
            try:
                provided_config = self._container.provided_config(model)
                if provided_config:
                    # Use model_dump to get all values as a dict
                    values = provided_config.model_dump()
                    # Make values JSON serializable
                    values = self._make_json_serializable(values)
            except Exception:
                # Fallback: get default values from the model fields
                try:
                    for field_name, field_info in model.model_fields.items():
                        if field_info.default is not None and field_info.default is not PydanticUndefined:
                            default_val = field_info.default
                            if isinstance(default_val, pydantic.BaseModel):
                                default_val = default_val.model_dump()
                            values[field_name] = self._make_json_serializable(default_val)
                except Exception:
                    pass

            try:
                schema = self._normalize_pydantic_schema(model)
            except Exception:
                # If schema generation fails, create a minimal schema
                schema = {"type": "object", "properties": {}, "required": []}

            configs.append({
                "prefix": prefix,
                "values": values,
                "schema": schema,
            })

        return configs if configs else None

    def _make_json_serializable(self, obj):
        """Recursively convert non-JSON-serializable objects to strings."""
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(v) for v in obj]
        elif isinstance(obj, Path):
            return str(obj)
        elif hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, type(None))):
            # For other non-serializable objects, convert to string
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
        return obj

    def _get_full_state(self) -> dict:
        """Get the full application state."""
        if not self._container:
            return {}

        components = self._container.components
        app = self._container.provided_app()
        plugins = self._container.provided_plugins()
        libs = self._container.provided_libs()

        initialized_count = sum(
            1 for c in components
            if component_internals(c).is_initialized
        )

        # Get config file paths from IOCBaseConfig
        config_file_path = None
        config_targets = []
        try:
            ioc_config = self._container.ioc_config_model
            config_path = ioc_config.config_path
            config_file_path = str(config_path) if config_path else None

            if config_path:
                config_dir = config_path.parent

                # YAML config file (always available)
                config_targets.append({
                    "id": "yaml",
                    "label": f"YAML ({config_path.name})",
                    "path": str(config_path),
                    "exists": config_path.exists()
                })

                # Base .env file
                env_path = config_dir / ".env"
                config_targets.append({
                    "id": "env",
                    "label": ".env",
                    "path": str(env_path),
                    "exists": env_path.exists()
                })

                # Context-specific .env file (if context is set or inferred from config filename)
                context = ioc_config.context

                # Try to infer context from config filename if not explicitly set
                # Patterns: dev.conf.yaml, ioc.dev.yaml, config.dev.yaml, etc.
                if not context and config_path:
                    stem = config_path.stem  # filename without extension
                    # Pattern: {context}.conf or {context}.config
                    if stem.endswith('.conf') or stem.endswith('.config'):
                        context = stem.rsplit('.', 1)[0]
                    # Pattern: ioc.{context} or config.{context}
                    elif '.' in stem:
                        parts = stem.split('.')
                        if len(parts) == 2 and parts[0] in ('ioc', 'config', 'conf'):
                            context = parts[1]

                if context:
                    context_env_path = config_dir / f".{context}.env"
                    config_targets.append({
                        "id": "context_env",
                        "label": f".{context}.env",
                        "path": str(context_env_path),
                        "exists": context_env_path.exists()
                    })
        except Exception:
            pass

        return {
            "type": "full_state",
            "state": {
                "app_name": app.__metadata__.get("name", "unknown"),
                "app_version": app.__metadata__.get("version", "unknown"),
                "total_components": len(components),
                "initialized_components": initialized_count,
                "plugins_count": len(plugins),
                "libraries_count": len(libs),
                "discovered_plugins_count": len(self._discovered_plugins),
                "config_file": config_file_path,
                "config_targets": config_targets,
            },
            "components": [self._get_component_info(c) for c in components],
            "plugins": [self._get_component_info(p) for p in plugins],
            "discovered_plugins": list(self._discovered_plugins.values()),
        }

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self._clients:
            return

        data = json.dumps(message)

        async with self._lock:
            dead_clients = set()
            for client in self._clients:
                try:
                    await client.send(data)
                except websockets.exceptions.ConnectionClosed:
                    dead_clients.add(client)

            self._clients -= dead_clients

    async def broadcast_state(self):
        """Broadcast the current full state to all connected clients."""
        await self.broadcast(self._get_full_state())

    async def broadcast_component_update(self, component_name: str, component_info: dict, old_status: str,
                                         new_status: str):
        """Broadcast a component state change."""
        message = {
            "type": "component_update",
            "component": component_info,
            "transition": {
                "from": old_status,
                "to": new_status,
            }
        }
        await self.broadcast(message)

    async def check_state_changes(self):
        """Check for component state changes and broadcast updates."""
        if not self._container or not self._clients:
            return

        components = self._container.components
        state_changed = False

        for component in components:
            name = component.__metadata__.get("name", "unknown")
            current_state = self._get_component_state(component)
            previous_state = self._previous_states.get(name)

            if previous_state is None:
                # First time seeing this component
                self._previous_states[name] = current_state
            elif current_state != previous_state:
                # State changed!
                state_changed = True
                old_status = previous_state.get_status_label()
                new_status = current_state.get_status_label()

                component_info = self._get_component_info(component)
                await self.broadcast_component_update(name, component_info, old_status, new_status)

                self._previous_states[name] = current_state

        # If any state changed, also broadcast updated summary stats
        if state_changed:
            await self.broadcast_state_summary()

    async def broadcast_state_summary(self):
        """Broadcast just the summary statistics."""
        if not self._container:
            return

        components = self._container.components
        app = self._container.provided_app()
        plugins = self._container.provided_plugins()
        libs = self._container.provided_libs()

        initialized_count = sum(
            1 for c in components
            if component_internals(c).is_initialized
        )

        message = {
            "type": "state_summary",
            "state": {
                "app_name": app.__metadata__.get("name", "unknown"),
                "app_version": app.__metadata__.get("version", "unknown"),
                "total_components": len(components),
                "initialized_components": initialized_count,
                "plugins_count": len(plugins),
                "libraries_count": len(libs),
            }
        }
        await self.broadcast(message)

    async def start_monitoring(self, interval: float = 0.25):
        """Start the state monitoring loop."""
        self._monitoring = True
        while self._monitoring:
            try:
                await self.check_state_changes()
            except Exception:
                pass  # Don't let monitoring errors crash the loop
            await asyncio.sleep(interval)

    def stop_monitoring(self):
        """Stop the state monitoring loop."""
        self._monitoring = False

    async def handle_client(self, websocket: WebSocketServerProtocol):
        """Handle a WebSocket client connection."""
        await self.register(websocket)
        try:
            # Send initial full state
            state = self._get_full_state()
            await websocket.send(json.dumps(state))

            # Send initial logs
            if self._log_buffer:
                logs_message = {
                    "type": "logs_history",
                    "logs": self._log_buffer.get_all(),
                }
                await websocket.send(json.dumps(logs_message))

            # Keep connection alive and handle incoming messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "error": "Invalid JSON"}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def _handle_message(self, websocket: WebSocketServerProtocol, data: dict):
        """Handle incoming WebSocket messages."""
        action = data.get("action")

        if action == "refresh":
            state = self._get_full_state()
            await websocket.send(json.dumps(state))

        elif action == "get_logs":
            if self._log_buffer:
                last_id = data.get("since_id", 0)
                logs = self._log_buffer.get_since(last_id) if last_id else self._log_buffer.get_all()
                await websocket.send(json.dumps({
                    "type": "logs_history",
                    "logs": logs,
                }))

        elif action == "clear_logs":
            if self._log_buffer:
                self._log_buffer.clear()
                await websocket.send(json.dumps({
                    "type": "success",
                    "message": "Logs cleared",
                }))
                await self.broadcast({"type": "logs_cleared"})

        elif action == "enable_plugin":
            plugin_name = data.get("name")
            result = await self._enable_plugin(plugin_name)
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after enable
            if result.get("type") == "success":
                await self.broadcast_state()

        elif action == "disable_plugin":
            plugin_name = data.get("name")
            result = await self._disable_plugin(plugin_name)
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after disable
            if result.get("type") == "success":
                await self.broadcast_state()

        elif action == "register_plugin":
            plugin_path = data.get("path")
            class_reference = data.get("class_reference")  # Optional: e.g., "MyClass" or ":MyClass()"
            result = await self._register_plugin_from_path(plugin_path, class_reference=class_reference)
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after registration
            if result.get("type") == "success":
                await self.broadcast_state()

        elif action == "upload_plugin":
            upload_type = data.get("type")
            if upload_type == "file":
                result = await self._upload_plugin_file(data.get("filename"), data.get("content"))
            elif upload_type == "directory":
                result = await self._upload_plugin_directory(data.get("dirname"), data.get("files"))
            else:
                result = {"type": "error", "error": "Invalid upload type"}
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after registration
            if result.get("type") == "success":
                await self.broadcast_state()

        elif action == "save_config":
            component_name = data.get("name")
            config_values = data.get("config")
            target_file = data.get("target_file", "yaml")  # yaml, env, or context_env
            config_prefix = data.get("prefix")  # For components with multiple configs
            result = await self._save_component_config(component_name, config_values, target_file, config_prefix)
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after config change
            if result.get("type") == "success":
                await self.broadcast_state()

        elif action == "unregister_plugin":
            plugin_name = data.get("name")
            result = await self._unregister_plugin(plugin_name)
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after unregistration
            if result.get("type") == "success":
                await self.broadcast_state()

        elif action == "save_plugins":
            result = await self._save_plugins_to_config()
            await websocket.send(json.dumps(result))

        elif action == "sync_plugins":
            result = await self._sync_plugins_from_path()
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after sync
            if result.get("type") in ("success", "info"):
                await self.broadcast_state()

        elif action == "remove_plugin":
            plugin_path = data.get("path")
            result = await self._remove_plugin_file(plugin_path)
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after removal
            if result.get("type") == "success":
                await self.broadcast_state()

        # Pot management actions
        elif action == "list_pots":
            result = await self._list_pots()
            await websocket.send(json.dumps(result))

        elif action == "list_pot_components":
            pot_name = data.get("pot_name")
            result = await self._list_pot_components(pot_name)
            await websocket.send(json.dumps(result))

        elif action == "register_pot_component":
            pot_name = data.get("pot_name")
            component_name = data.get("component_name")
            # Build the pot reference
            pot_ref = f"@{pot_name}/{component_name}"
            result = await self._register_plugin_from_path(pot_ref)
            await websocket.send(json.dumps(result))
            if result.get("type") == "success":
                await self.broadcast_state()

    def _run_in_main_loop(self, coro) -> Any:
        """Run a coroutine in the main event loop and wait for result."""
        if self._main_loop is None:
            raise RuntimeError("Main event loop not set")

        future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
        return future.result(timeout=30)  # 30 second timeout

    @inject
    async def _enable_plugin(
            self,
            plugin_name: str,
            logger=get_logger()
    ) -> dict:
        """Enable a plugin."""
        if not plugin_name:
            return {"type": "error", "error": "Plugin name required"}

        plugin = self._container.provided_plugin(plugin_name)
        if plugin is None:
            return {"type": "error", "error": f"Plugin '{plugin_name}' not found"}

        internals = component_internals(plugin)
        if internals.is_initialized:
            return {"type": "info", "message": f"Plugin '{plugin_name}' is already enabled"}

        try:
            # Run in main event loop to avoid cross-loop issues
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_in_main_loop(initialize_components(plugin))
            )
            return {"type": "success", "message": f"Plugin '{plugin_name}' enabled successfully"}
        except Exception as e:
            logger.error(f"Error enabling plugin '{plugin_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _disable_plugin(
            self,
            plugin_name: str,
            logger=get_logger()
    ) -> dict:
        """Disable a plugin."""
        if not plugin_name:
            return {"type": "error", "error": "Plugin name required"}

        plugin = self._container.provided_plugin(plugin_name)
        if plugin is None:
            return {"type": "error", "error": f"Plugin '{plugin_name}' not found"}

        internals = component_internals(plugin)
        if not internals.is_initialized:
            return {"type": "info", "message": f"Plugin '{plugin_name}' is already disabled"}

        # Only block if there are initialized components that require this plugin
        active_dependents = [
            r for r in internals.required_by
            if component_internals(r).is_initialized
        ]
        if active_dependents:
            required_names = [r.__metadata__.get("name") for r in active_dependents]
            return {
                "type": "error",
                "error": f"Cannot disable plugin '{plugin_name}': required by {required_names}"
            }

        try:
            # Run in main event loop to avoid cross-loop issues
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_in_main_loop(shutdown_components(plugin))
            )
            return {"type": "success", "message": f"Plugin '{plugin_name}' disabled successfully"}
        except Exception as e:
            logger.error(f"Error disabling plugin '{plugin_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _register_plugin_from_path(
            self,
            plugin_path: str,
            class_reference: Optional[str] = None,
            auto_initialize: bool = False,
            logger=get_logger()
    ) -> dict:
        """Register a new plugin from a file path.

        Args:
            plugin_path: Path to the plugin file or directory
            class_reference: Optional class reference (e.g., ":MyClass()" or "MyClass")
                           If provided, loads a specific class from the module.
                           If None, tries to auto-detect a component class, or loads the module.
            auto_initialize: If True, initialize the plugin after registration (default: False)
        """
        if not plugin_path:
            return {"type": "error", "error": "Plugin path required"}

        try:
            path = Path(plugin_path)
            if not path.exists():
                return {"type": "error", "error": f"File not found: {plugin_path}"}

            # Build the component reference
            if class_reference:
                # Normalize the reference format
                ref = class_reference.strip()
                if not ref.startswith(":"):
                    ref = f":{ref}"
                if not ref.endswith("()"):
                    ref = f"{ref}()"
                component_ref = f"{path}:{ref[1:]}"  # Remove leading : for compile_component
            else:
                # No class reference provided - try to auto-detect
                # First, scan for component classes
                component_classes = _scan_module_for_components(path, logger=logger)

                if component_classes:
                    # Use the first component class found
                    first_class = component_classes[0]
                    class_name = first_class["class_name"]
                    logger.info(f"Auto-detected component class: {class_name}")
                    component_ref = f"{path}:{class_name}()"
                else:
                    # No classes found, try loading the module directly
                    component_ref = path

            # Load the component from the file
            plugin = compile_component(component_ref)
            plugin_name = plugin.__metadata__.get("name", "unknown")

            # Check if already registered
            existing = self._container.provided_plugin(plugin_name)
            if existing is not None:
                return {"type": "info", "message": f"Plugin '{plugin_name}' is already registered"}

            # Register the plugin in the main event loop
            # Note: This only registers the plugin in memory, it does NOT modify ioc.yaml
            async def register_only():
                await register_plugin(self._container, plugin)
                # Reconfigure wires up dependencies for the new plugin
                reconfigure_ioc_app(self._container, (plugin,))
                if auto_initialize:
                    await initialize_components(plugin)

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_in_main_loop(register_only())
            )

            # Update the log buffer with the new component info
            if self._log_buffer:
                # Handle both module-based and class-based components
                if hasattr(plugin, '__name__'):
                    module_name = plugin.__name__
                else:
                    module_name = type(plugin).__name__
                display_name = plugin_name
                internals = component_internals(plugin)
                comp_type = internals.type.value
                with self._log_buffer._lock:
                    self._log_buffer._component_info[module_name] = (display_name, comp_type)

            # Remove from discovered plugins list
            resolved_path = str(path.resolve())
            self._discovered_plugins.pop(resolved_path, None)

            if auto_initialize:
                return {"type": "success", "message": f"Plugin '{plugin_name}' registered and initialized successfully"}
            else:
                return {"type": "success",
                        "message": f"Plugin '{plugin_name}' registered successfully (not initialized)"}
        except Exception as e:
            logger.error(f"Error registering plugin from '{plugin_path}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _upload_plugin_file(
            self,
            filename: str,
            content: str,
            config=get_config(DashboardConfig),
            ioc_api=get_container_api(),
            logger=get_logger()
    ) -> dict:
        """Handle single file plugin upload."""
        if not filename or not content:
            return {"type": "error", "error": "Filename and content required"}

        try:
            # Decode base64 content (sent from browser's FileReader.readAsDataURL)
            raw_bytes = base64.b64decode(content)

            # Determine the upload directory from config
            upload_path = Path(config.plugin_upload_path)
            if not upload_path.is_absolute():
                # Make relative to config file directory
                ioc_config = ioc_api.ioc_config_model
                if ioc_config.config_path:
                    upload_path = ioc_config.config_path.parent / upload_path
                else:
                    upload_path = Path.cwd() / upload_path

            # Create the directory if it doesn't exist
            upload_path.mkdir(parents=True, exist_ok=True)

            plugin_path = upload_path / filename

            # Check if file already exists
            if plugin_path.exists():
                return {"type": "error", "error": f"Plugin file '{filename}' already exists in {upload_path}"}

            # Write the file as bytes to preserve original line endings
            plugin_path.write_bytes(raw_bytes)
            logger.info(f"Saved plugin file to {plugin_path}")

            # Register the plugin (without auto-initialization)
            return await self._register_plugin_from_path(str(plugin_path), auto_initialize=False)
        except Exception as e:
            logger.error(f"Error uploading plugin file '{filename}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _upload_plugin_directory(
            self,
            dirname: str,
            files: List[Dict[str, str]],
            config=get_config(DashboardConfig),
            ioc_api=get_container_api(),
            logger=get_logger()
    ) -> dict:
        """Handle directory plugin upload."""
        if not dirname or not files:
            return {"type": "error", "error": "Directory name and files required"}

        try:
            # Determine the upload directory from config
            upload_path = Path(config.plugin_upload_path)
            if not upload_path.is_absolute():
                # Make relative to config file directory
                ioc_config = ioc_api.ioc_config_model
                if ioc_config.config_path:
                    upload_path = ioc_config.config_path.parent / upload_path
                else:
                    upload_path = Path.cwd() / upload_path

            # Create the directory if it doesn't exist
            upload_path.mkdir(parents=True, exist_ok=True)

            # Check if plugin directory already exists
            plugin_dir = upload_path / dirname
            if plugin_dir.exists():
                return {"type": "error", "error": f"Plugin directory '{dirname}' already exists in {upload_path}"}

            # Write all files preserving directory structure
            for file_info in files:
                relative_path = file_info.get("path", "")
                content_b64 = file_info.get("content", "")
                if not relative_path or not content_b64:
                    continue

                # Decode base64 content
                raw_bytes = base64.b64decode(content_b64)

                file_path = upload_path / relative_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                # Write as bytes to preserve original line endings
                file_path.write_bytes(raw_bytes)

            logger.info(f"Saved plugin directory to {plugin_dir}")

            # Register the plugin (without auto-initialization)
            return await self._register_plugin_from_path(str(plugin_dir), auto_initialize=False)
        except Exception as e:
            logger.error(f"Error uploading plugin directory '{dirname}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _save_component_config(
            self,
            component_name: str,
            config_values: Dict[str, Any],
            target_file: str = "yaml",
            config_prefix: Optional[str] = None,
            ioc_api=get_container_api(),
            logger=get_logger()
    ) -> dict:
        """Save configuration for a component to the specified target file.

        Args:
            component_name: Name of the component to save config for
            config_values: Dictionary of configuration values to save
            target_file: Target file type - "yaml", "env", or "context_env"
            config_prefix: The config prefix to save to (for components with multiple configs)
        """
        if not component_name:
            return {"type": "error", "error": "Component name required"}

        if not config_values:
            return {"type": "error", "error": "Configuration values required"}

        if target_file not in ("yaml", "env", "context_env"):
            return {"type": "error", "error": f"Invalid target file: {target_file}"}

        try:
            # Find the component
            component = None
            for c in self._container.components:
                if c.__metadata__.get("name") == component_name:
                    component = c
                    break

            if component is None:
                return {"type": "error", "error": f"Component '{component_name}' not found"}

            # Get the config model(s) and find the matching one by prefix
            config_models = component.__metadata__.get("config")
            if not config_models:
                return {"type": "error", "error": f"Component '{component_name}' has no configuration"}

            # Normalize to a list (metadata() converts config to a set)
            if not isinstance(config_models, (list, tuple, set, frozenset)):
                config_models = [config_models]
            else:
                config_models = list(config_models)

            # Find the config model matching the prefix
            config_model = None
            if config_prefix:
                for model in config_models:
                    if getattr(model, "__prefix__", None) == config_prefix:
                        config_model = model
                        break
                if not config_model:
                    return {"type": "error",
                            "error": f"No config with prefix '{config_prefix}' found for '{component_name}'"}
            else:
                # Use the first config model if no prefix specified
                config_model = config_models[0]

            prefix = getattr(config_model, "__prefix__", None)
            if not prefix:
                return {"type": "error", "error": f"Configuration model for '{component_name}' has no prefix"}

            ioc_config = ioc_api.ioc_config_model
            SECRET_MASK = "**********"

            # Filter out masked secret values - these should not be saved
            def filter_masked_secrets(obj):
                """Recursively filter out masked secret values."""
                if isinstance(obj, dict):
                    return {k: filter_masked_secrets(v) for k, v in obj.items()
                            if v != SECRET_MASK}
                elif isinstance(obj, list):
                    return [filter_masked_secrets(v) for v in obj if v != SECRET_MASK]
                return obj

            # Recursively serialize values for JSON/YAML compatibility
            def serialize_values(obj):
                if isinstance(obj, dict):
                    return {k: serialize_values(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_values(v) for v in obj]
                elif isinstance(obj, Path):
                    return str(obj)
                elif hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, type(None))):
                    try:
                        json.dumps(obj)
                        return obj
                    except (TypeError, ValueError):
                        return str(obj)
                return obj

            # Filter and serialize the provided config values
            filtered_config_values = filter_masked_secrets(config_values)
            filtered_config_values = serialize_values(filtered_config_values)

            if not filtered_config_values:
                return {"type": "info", "message": "No changes to save (all values were masked secrets)"}

            if target_file == "yaml":
                # Save to YAML config file - only update specified fields
                config_path = ioc_config.config_path
                if not config_path or not config_path.exists():
                    return {"type": "error", "error": "IOC configuration file not found"}

                with open(config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f) or {}

                # Get existing section or create empty one
                existing_section = existing_config.get(prefix, {})
                if not isinstance(existing_section, dict):
                    existing_section = {}

                # Merge: only update the fields that were provided
                def deep_merge(base, updates):
                    """Recursively merge updates into base dict."""
                    result = base.copy()
                    for key, value in updates.items():
                        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                            result[key] = deep_merge(result[key], value)
                        else:
                            result[key] = value
                    return result

                existing_config[prefix] = deep_merge(existing_section, filtered_config_values)

                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(existing_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

                target_display = str(config_path)

            else:
                # Save to .env file (env or context_env)
                config_path = ioc_config.config_path
                if not config_path:
                    return {"type": "error", "error": "IOC configuration path not set"}

                config_dir = config_path.parent

                if target_file == "env":
                    env_path = config_dir / ".env"
                else:  # context_env
                    context = ioc_config.context
                    if not context:
                        return {"type": "error",
                                "error": "No context configured. Set 'context' in IOC config to use context-specific .env files."}
                    env_path = config_dir / f".{context}.env"

                # Read existing .env file
                existing_env = {}
                if env_path.exists():
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, _, value = line.partition('=')
                                existing_env[key.strip()] = value.strip()

                # Convert config values to env format (PREFIX_KEY=value)
                # Only update the fields that were modified
                prefix_upper = prefix.upper()
                for key, value in filtered_config_values.items():
                    env_key = f"{prefix_upper}_{key.upper()}"
                    if isinstance(value, bool):
                        existing_env[env_key] = str(value).lower()
                    elif isinstance(value, (dict, list)):
                        existing_env[env_key] = json.dumps(value)
                    else:
                        existing_env[env_key] = str(value)

                # Write back the .env file
                with open(env_path, 'w', encoding='utf-8') as f:
                    for key, value in existing_env.items():
                        f.write(f"{key}={value}\n")

                target_display = str(env_path)

            # Reconfigure the component to reload config from files
            # This properly reloads and validates the config (including SecretStr, etc.)
            try:
                reconfigure_ioc_app(self._container, components=(component,))
                logger.info(f"Reconfigured component '{component_name}' with new config values")
            except Exception as e:
                logger.warning(f"Could not reconfigure component '{component_name}': {e}. Restart may be required.")

            field_count = len(filtered_config_values)
            logger.info(f"Saved {field_count} field(s) for '{component_name}' (prefix: {prefix}) to {target_display}")
            return {
                "type": "success",
                "message": f"Saved {field_count} field(s) for '{component_name}' to {target_display}. Restart the component to apply changes."
            }

        except Exception as e:
            logger.error(f"Error saving config for '{component_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _unregister_plugin(
            self,
            plugin_name: str,
            logger=get_logger()
    ) -> dict:
        """Unregister a plugin from the container."""
        if not plugin_name:
            return {"type": "error", "error": "Plugin name required"}

        plugin = self._container.provided_plugin(plugin_name)
        if plugin is None:
            return {"type": "error", "error": f"Plugin '{plugin_name}' not found"}

        internals = component_internals(plugin)

        # Don't allow unregistering active plugins
        if internals.is_initialized:
            return {"type": "error", "error": f"Cannot unregister active plugin '{plugin_name}'. Disable it first."}

        # Check for dependents
        if internals.required_by:
            required_names = [r.__metadata__.get("name") for r in internals.required_by]
            return {
                "type": "error",
                "error": f"Cannot unregister plugin '{plugin_name}': required by {required_names}"
            }

        try:
            # Remove from container
            self._container.unregister_plugins(plugin)

            # Remove from log buffer component info
            if self._log_buffer:
                # Handle both module-based and class-based components
                if hasattr(plugin, '__name__'):
                    module_name = plugin.__name__
                else:
                    module_name = type(plugin).__name__
                with self._log_buffer._lock:
                    self._log_buffer._component_info.pop(module_name, None)

            # Remove from previous states tracking
            self._previous_states.pop(plugin_name, None)

            logger.info(f"Plugin '{plugin_name}' unregistered successfully")
            return {"type": "success", "message": f"Plugin '{plugin_name}' unregistered successfully"}
        except Exception as e:
            logger.error(f"Error unregistering plugin '{plugin_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _sync_plugins_from_path(
            self,
            logger=get_logger()
    ) -> dict:
        """Discover plugins from the configured upload path without auto-registering.

        Updates the list of discovered plugins that can be registered manually.
        """
        if not self._plugin_upload_path:
            return {"type": "error", "error": "Plugin upload path not configured"}

        if not self._plugin_upload_path.exists():
            # Create the directory if it doesn't exist
            self._plugin_upload_path.mkdir(parents=True, exist_ok=True)
            return {"type": "info", "message": f"Created plugin directory: {self._plugin_upload_path}"}

        try:
            # Find all plugin files/directories in the upload path
            plugin_paths_on_disk: Set[Path] = set()

            for item in self._plugin_upload_path.iterdir():
                if item.name.startswith('_') or item.name.startswith('.'):
                    continue  # Skip __pycache__, __init__.py at root level, hidden files

                if item.is_file() and item.suffix == '.py':
                    # Single file plugin
                    plugin_paths_on_disk.add(item.resolve())
                elif item.is_dir() and (item / '__init__.py').exists():
                    # Directory plugin with __init__.py
                    plugin_paths_on_disk.add(item.resolve())

            # Get currently registered plugins and their paths AND names
            registered_plugins = self._container.provided_plugins()
            registered_paths: Set[Path] = set()
            registered_names: Set[str] = set()

            for plugin in registered_plugins:
                # Track registered plugin names
                plugin_meta_name = plugin.__metadata__.get("name", "")
                if plugin_meta_name:
                    registered_names.add(plugin_meta_name)

                plugin_file = _get_component_file(plugin)
                if plugin_file:
                    plugin_path = Path(plugin_file).resolve()
                    registered_paths.add(plugin_path)
                    # Also add parent directory for any .py file in a package
                    # This handles class-based components in submodules (e.g., http_server/http_server.py)
                    if plugin_path.suffix == '.py':
                        parent = plugin_path.parent
                        registered_paths.add(parent)
                        # Also check if parent has __init__.py (is a package)
                        if (parent / '__init__.py').exists():
                            registered_paths.add(parent)

            # Update discovered plugins (on disk but not registered)
            self._discovered_plugins.clear()
            for path in plugin_paths_on_disk:
                # Check if already registered by path
                is_registered = path in registered_paths
                if not is_registered and path.is_dir():
                    # For directory plugins, also check if __init__.py is registered
                    init_path = path / "__init__.py"
                    is_registered = init_path in registered_paths

                if not is_registered:
                    # Extract basic info from the file
                    plugin_name = path.stem if path.is_file() else path.name

                    # Scan for component classes (pass logger for debugging)
                    logger.debug(f"Scanning plugin for components: {path}")
                    component_classes = _scan_module_for_components(path, logger=logger)
                    logger.debug(f"Found {len(component_classes)} component classes in {path}")

                    # Filter out component classes that are already registered
                    unregistered_classes = [
                        cls for cls in component_classes
                        if cls.get("metadata_name") not in registered_names
                    ]

                    # Check for module-level __metadata__
                    has_module_metadata = _check_module_has_metadata(path)
                    logger.debug(f"Module-level metadata: {has_module_metadata}")

                    # Skip if all component classes are already registered
                    if not unregistered_classes and not has_module_metadata:
                        logger.debug(f"All components in {path} already registered, skipping")
                        continue

                    self._discovered_plugins[str(path)] = {
                        "name": plugin_name,
                        "path": str(path),
                        "is_directory": path.is_dir(),
                        "component_classes": unregistered_classes,
                        "has_module_metadata": has_module_metadata,
                    }

            discovered_count = len(self._discovered_plugins)
            if discovered_count > 0:
                return {"type": "success", "message": f"Found {discovered_count} unregistered plugin(s)"}
            return {"type": "info", "message": "No unregistered plugins found"}

        except Exception as e:
            logger.error("Error discovering plugins from path", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _remove_plugin_file(
            self,
            plugin_path: str,
            logger=get_logger()
    ) -> dict:
        """Remove a plugin file or directory from disk."""
        import shutil

        if not plugin_path:
            return {"type": "error", "error": "Plugin path is required"}

        path = Path(plugin_path).resolve()

        # Security check: ensure the path is within the upload directory
        if not self._plugin_upload_path:
            return {"type": "error", "error": "Plugin upload path not configured"}

        try:
            path.relative_to(self._plugin_upload_path.resolve())
        except ValueError:
            return {"type": "error", "error": "Cannot remove plugins outside the upload directory"}

        if not path.exists():
            # Remove from discovered list if present
            self._discovered_plugins.pop(str(path), None)
            return {"type": "error", "error": "Plugin file not found"}

        try:
            plugin_name = path.stem if path.is_file() else path.name

            if path.is_file():
                path.unlink()
                logger.info(f"Removed plugin file: {path}")
            elif path.is_dir():
                shutil.rmtree(path)
                logger.info(f"Removed plugin directory: {path}")

            # Remove from discovered list
            self._discovered_plugins.pop(str(path), None)

            return {"type": "success", "message": f"Plugin '{plugin_name}' removed from disk"}

        except Exception as e:
            logger.error(f"Error removing plugin file '{plugin_path}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _save_plugins_to_config(
            self,
            ioc_api=get_container_api(),
            logger=get_logger()
    ) -> dict:
        """Save the current list of registered plugins to ioc.yaml."""
        try:
            ioc_config = ioc_api.ioc_config_model
            config_path = ioc_config.config_path

            if not config_path or not config_path.exists():
                return {"type": "error", "error": "IOC configuration file not found"}

            # Read existing config
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = yaml.safe_load(f) or {}

            # Get current plugins from container
            plugins = self._container.provided_plugins()

            # Build list of plugin paths (relative to config directory if possible)
            config_dir = config_path.parent
            plugin_paths = []

            for plugin in plugins:
                plugin_name = plugin.__metadata__.get("name", "unknown")

                # Check if plugin has a source reference (e.g., pot reference)
                source_ref = plugin.__metadata__.get("_source_ref")

                # If source is a pot reference (@pot/component), use it directly
                if source_ref and source_ref.startswith("@"):
                    plugin_paths.append(source_ref)
                    continue

                # Otherwise, build path from file location
                plugin_file = _get_component_file(plugin)

                if plugin_file:
                    plugin_path = Path(plugin_file)

                    # For class-based components, we need to include the class reference
                    # Check if this is an instance (class-based) or module
                    is_class_based = not hasattr(plugin, '__file__')

                    # Try to make path relative to config directory
                    try:
                        relative_path = plugin_path.relative_to(config_dir)
                        path_str = str(relative_path)
                    except ValueError:
                        # Path is not relative to config dir, use absolute
                        path_str = str(plugin_path)

                    # For directory-based plugins, use parent directory
                    if plugin_path.name == "__init__.py":
                        path_str = str(Path(path_str).parent)

                    # Add class reference for class-based components
                    if is_class_based:
                        class_name = type(plugin).__name__
                        path_str = f"{path_str}:{class_name}()"

                    plugin_paths.append(path_str)
                else:
                    logger.warning(f"Plugin '{plugin_name}' has no path, skipping in save")

            # Update the components.plugins section
            if "components" not in existing_config:
                existing_config["components"] = {}

            existing_config["components"]["plugins"] = plugin_paths

            # Write back to config file
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            logger.info(f"Saved {len(plugin_paths)} plugin(s) to {config_path}")
            return {
                "type": "success",
                "message": f"Saved {len(plugin_paths)} plugin(s) to {config_path.name}"
            }
        except Exception as e:
            logger.error("Error saving plugins to config", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _list_pots(self, logger=get_logger()) -> dict:
        """List all available pots and their metadata."""
        try:
            from awioc.commands.pot import get_pot_dir, load_pot_manifest

            pot_dir = get_pot_dir()

            if not pot_dir.exists():
                return {"type": "success", "pots": []}

            pots = []
            for pot_path in sorted(pot_dir.iterdir()):
                if not pot_path.is_dir():
                    continue

                manifest = load_pot_manifest(pot_path)
                component_count = len(manifest.get("components", {}))

                pots.append({
                    "name": pot_path.name,
                    "version": manifest.get("version", "?"),
                    "description": manifest.get("description", ""),
                    "component_count": component_count,
                })

            return {"type": "success", "pots": pots}
        except Exception as e:
            logger.error("Error listing pots", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _list_pot_components(self, pot_name: str, logger=get_logger()) -> dict:
        """List components in a specific pot."""
        try:
            if not pot_name:
                return {"type": "error", "error": "Pot name required"}

            from awioc.commands.pot import get_pot_path, load_pot_manifest

            pot_path = get_pot_path(pot_name)

            if not pot_path.exists():
                return {"type": "error", "error": f"Pot not found: {pot_name}"}

            manifest = load_pot_manifest(pot_path)
            components_data = manifest.get("components", {})

            # Get currently registered plugins to mark which ones are already loaded
            registered_refs = set()
            for plugin in self._container.provided_plugins():
                source_ref = plugin.__metadata__.get("_source_ref", "")
                if source_ref.startswith("@"):
                    registered_refs.add(source_ref)

            components = []
            for comp_id, comp_info in sorted(components_data.items()):
                pot_ref = f"@{pot_name}/{comp_id}"
                components.append({
                    "id": comp_id,
                    "name": comp_info.get("name", comp_id),
                    "version": comp_info.get("version", "?"),
                    "description": comp_info.get("description", ""),
                    "class_name": comp_info.get("class_name"),
                    "pot_ref": pot_ref,
                    "is_registered": pot_ref in registered_refs,
                })

            return {
                "type": "success",
                "pot_name": pot_name,
                "pot_version": manifest.get("version", "?"),
                "pot_description": manifest.get("description", ""),
                "components": components,
            }
        except Exception as e:
            logger.error(f"Error listing components in pot '{pot_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}


# Global WebSocket manager instance
ws_manager = WebSocketManager()


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the management dashboard."""

    container: Optional[ContainerInterface] = None

    @inject
    def _get_dependencies(
            self,
            logger=get_logger(),
            container=get_container_api()
    ):
        return logger, container

    def _send_json_response(self, data: dict, status: int = 200):
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _send_html_response(self, html: str, status: int = 200):
        """Send an HTML response."""
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _get_component_info(self, component) -> dict:
        """Get information about a component."""
        internals = component_internals(component)
        metadata = component.__metadata__
        return {
            "name": metadata.get("name", "unknown"),
            "version": metadata.get("version", "unknown"),
            "description": metadata.get("description", ""),
            "type": internals.type.value,
            "state": {
                "is_initialized": internals.is_initialized,
                "is_initializing": internals.is_initializing,
                "is_shutting_down": internals.is_shutting_down,
            },
            "required_by": [
                req.__metadata__.get("name", "unknown")
                for req in internals.required_by
            ]
        }

    def do_GET(self):
        """Handle GET requests."""
        logger, container = self._get_dependencies()
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        logger.info(f"GET {self.path} FROM {self.client_address[0]}:{self.client_address[1]}")

        if path == "/":
            self._serve_dashboard_html()
        elif path == "/api/components":
            self._handle_list_components(container)
        elif path == "/api/state":
            self._handle_app_state(container)
        elif path == "/api/plugins":
            self._handle_list_plugins(container)
        else:
            self._send_json_response({"error": "Not Found"}, 404)

    def do_POST(self):
        """Handle POST requests."""
        logger, container = self._get_dependencies()
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        logger.info(f"POST {self.path} FROM {self.client_address[0]}:{self.client_address[1]}")

        if path == "/api/plugins/enable":
            self._handle_enable_plugin(container)
        elif path == "/api/plugins/disable":
            self._handle_disable_plugin(container)
        else:
            self._send_json_response({"error": "Not Found"}, 404)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_dashboard_html(self):
        """Serve the dashboard HTML page from web/index.html."""
        index_path = WEB_DIR / "index.html"
        try:
            html = index_path.read_text(encoding="utf-8")
            self._send_html_response(html)
        except FileNotFoundError:
            self._send_json_response({"error": "Dashboard not found"}, 404)

    def _handle_list_components(self, container: ContainerInterface):
        """List all registered components."""
        components = container.components
        components_info = [self._get_component_info(c) for c in components]
        self._send_json_response({"components": components_info})

    def _handle_app_state(self, container: ContainerInterface):
        """Get overall application state."""
        components = container.components
        app = container.provided_app()
        plugins = container.provided_plugins()
        libs = container.provided_libs()

        initialized_count = sum(
            1 for c in components
            if component_internals(c).is_initialized
        )

        state = {
            "app_name": app.__metadata__.get("name", "unknown"),
            "app_version": app.__metadata__.get("version", "unknown"),
            "total_components": len(components),
            "initialized_components": initialized_count,
            "plugins_count": len(plugins),
            "libraries_count": len(libs),
            "plugins": [p.__metadata__.get("name") for p in plugins],
            "libraries": [lib.__metadata__.get("name") for lib in libs],
        }
        self._send_json_response(state)

    def _handle_list_plugins(self, container: ContainerInterface):
        """List all registered plugins."""
        plugins = container.provided_plugins()
        plugins_info = [self._get_component_info(p) for p in plugins]
        self._send_json_response({"plugins": plugins_info})

    def _handle_enable_plugin(self, container: ContainerInterface):
        """Enable (initialize) a plugin."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()

        try:
            data = json.loads(body)
            plugin_name = data.get("name")
        except json.JSONDecodeError:
            self._send_json_response({"error": "Invalid JSON"}, 400)
            return

        if not plugin_name:
            self._send_json_response({"error": "Plugin name required"}, 400)
            return

        plugin = container.provided_plugin(plugin_name)
        if plugin is None:
            self._send_json_response({"error": f"Plugin '{plugin_name}' not found"}, 404)
            return

        internals = component_internals(plugin)
        if internals.is_initialized:
            self._send_json_response({"message": f"Plugin '{plugin_name}' is already enabled"})
            return

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(initialize_components(plugin))
            self._send_json_response({"message": f"Plugin '{plugin_name}' enabled successfully"})
        except Exception as e:
            self._send_json_response({"error": str(e)}, 500)
        finally:
            loop.close()

    def _handle_disable_plugin(self, container: ContainerInterface):
        """Disable (shutdown) a plugin."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()

        try:
            data = json.loads(body)
            plugin_name = data.get("name")
        except json.JSONDecodeError:
            self._send_json_response({"error": "Invalid JSON"}, 400)
            return

        if not plugin_name:
            self._send_json_response({"error": "Plugin name required"}, 400)
            return

        plugin = container.provided_plugin(plugin_name)
        if plugin is None:
            self._send_json_response({"error": f"Plugin '{plugin_name}' not found"}, 404)
            return

        internals = component_internals(plugin)
        if not internals.is_initialized:
            self._send_json_response({"message": f"Plugin '{plugin_name}' is already disabled"})
            return

        if internals.required_by:
            required_names = [r.__metadata__.get("name") for r in internals.required_by]
            self._send_json_response({
                "error": f"Cannot disable plugin '{plugin_name}': required by {required_names}"
            }, 400)
            return

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(shutdown_components(plugin))
            self._send_json_response({"message": f"Plugin '{plugin_name}' disabled successfully"})
        except Exception as e:
            self._send_json_response({"error": str(e)}, 500)
        finally:
            loop.close()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


@as_component(
    name="Management Dashboard",
    version="1.3.0",
    description="Management Dashboard App Component",
    wire=True,
    config=DashboardConfig,
)
class ManagementDashboardApp:
    """
    Management Dashboard App Component.

    Provides a web interface for monitoring and managing IOC components.
    Supports real-time updates via WebSocket with automatic state monitoring.
    Includes real-time log streaming with filtering capabilities.
    """

    def __init__(self):
        self._server: Optional[ThreadingHTTPServer] = None
        self._ws_server = None
        self._thread: Optional[Thread] = None
        self._ws_thread: Optional[Thread] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._monitor_interval: float = 0.25
        self._log_handler: Optional[DashboardLogHandler] = None

    def _run_ws_server(self, host: str, port: int):
        """Run the WebSocket server in a separate thread with state monitoring."""
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)

        # Set the WS loop on the manager so it can broadcast logs
        ws_manager.set_ws_loop(self._ws_loop)

        async def serve():
            # Start the state monitoring task
            monitor_task = asyncio.create_task(
                ws_manager.start_monitoring(self._monitor_interval)
            )

            async with websockets.serve(ws_manager.handle_client, host, port):
                while self._running:
                    await asyncio.sleep(0.1)

            # Stop monitoring when server stops
            ws_manager.stop_monitoring()
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

        self._ws_loop.run_until_complete(serve())
        self._ws_loop.close()

    @inject
    async def initialize(
            self,
            logger=get_logger(),
            config=get_config(DashboardConfig),
            container=get_container_api()
    ) -> None:
        """Start the management dashboard server."""
        self._shutdown_event = asyncio.Event()
        self._running = True
        self._monitor_interval = config.monitor_interval

        # Store container reference and main event loop
        DashboardRequestHandler.container = container
        ws_manager.set_container(container)
        ws_manager.set_main_loop(asyncio.get_running_loop())

        # Set up log buffer with component type mappings
        log_buffer._buffer = deque(maxlen=config.log_buffer_size)
        component_info = {}
        for comp in container.components:
            # Use module name (e.g., "samples.management_dashboard.management_dashboard") as key
            display_name = comp.__metadata__.get("name", "unknown")
            module_name = display_name
            internals = component_internals(comp)
            comp_type = internals.type.value
            component_info[module_name] = (display_name, comp_type)
        log_buffer.set_component_info(component_info)

        # Set up log handler
        ws_manager.set_log_buffer(log_buffer)
        self._log_handler = DashboardLogHandler(
            log_buffer,
            broadcast_callback=ws_manager.on_new_log
        )
        self._log_handler.setLevel(logging.DEBUG)

        # Attach handler to root logger to capture all logs
        logger.parent.addHandler(self._log_handler)

        # Start HTTP server
        logger.info(f"Starting Management Dashboard on {config.host}:{config.port}")
        self._server = ThreadingHTTPServer(
            (config.host, config.port),
            DashboardRequestHandler
        )
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        # Set up plugin upload path for auto-sync
        upload_path = Path(config.plugin_upload_path)
        if not upload_path.is_absolute():
            # Make relative to config file directory
            ioc_config = container.ioc_config_model
            if ioc_config.config_path:
                upload_path = ioc_config.config_path.parent / upload_path
            else:
                upload_path = Path.cwd() / upload_path
        ws_manager.set_plugin_upload_path(upload_path)
        logger.info(f"Plugin upload path: {upload_path}")

        # Discover plugins from the upload path (without auto-registering)
        logger.info("Discovering plugins from upload path...")
        sync_result = await ws_manager._sync_plugins_from_path()
        if sync_result.get("type") == "success":
            logger.info(sync_result.get("message"))
        elif sync_result.get("type") == "info":
            logger.info(sync_result.get("message"))
        elif sync_result.get("type") == "error":
            logger.warning(f"Plugin discovery issue: {sync_result.get('message') or sync_result.get('error')}")

        # Start WebSocket server with state monitoring
        logger.info(f"Starting WebSocket server on {config.host}:{config.ws_port}")
        logger.info(f"State monitoring interval: {config.monitor_interval}s")
        self._ws_thread = Thread(
            target=self._run_ws_server,
            args=(config.host, config.ws_port),
            daemon=True
        )
        self._ws_thread.start()

        logger.info(f"Management Dashboard running at http://{config.host}:{config.port}")
        logger.info(f"WebSocket available at ws://{config.host}:{config.ws_port}")
        logger.info(f"Log buffer size: {config.log_buffer_size} entries")

    async def wait(self) -> None:
        """Wait until shutdown is requested."""
        if self._shutdown_event:
            await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        """Stop the management dashboard server."""
        self._running = False
        ws_manager.stop_monitoring()

        if self._shutdown_event:
            self._shutdown_event.set()

        # Remove log handler
        if self._log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self._log_handler)
            self._log_handler = None

        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

        if self._ws_thread:
            self._ws_thread.join(timeout=2)
            self._ws_thread = None
