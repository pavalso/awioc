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
import tempfile
import time
import warnings
from collections import deque
from dataclasses import dataclass
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Lock
from typing import Any, Optional, Set, Dict, List, Deque, Iterable
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
    initialize_components,
    shutdown_components,
    register_plugin, reconfigure_ioc_app,
)
from awioc.loader.module_loader import compile_component


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

    def set_container(self, container: ContainerInterface):
        self._container = container

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

    def _get_component_config_info(self, component) -> Optional[dict]:
        metadata = component.__metadata__
        config_model = metadata.get("config")

        if not config_model:
            return None

        prefix = getattr(config_model, "__prefix__", None)
        if not prefix:
            return None

        # Get the merged config values from awioc (includes YAML, .env, .{context}.env)
        values = {}
        try:
            provided_config = self._container.provided_config(config_model)
            if provided_config:
                # Use model_dump to get all values as a dict
                values = provided_config.model_dump()
                # Make values JSON serializable
                values = self._make_json_serializable(values)
        except Exception:
            # Fallback: get default values from the model fields
            try:
                for field_name, field_info in config_model.model_fields.items():
                    if field_info.default is not None and field_info.default is not PydanticUndefined:
                        default_val = field_info.default
                        if isinstance(default_val, pydantic.BaseModel):
                            default_val = default_val.model_dump()
                        values[field_name] = self._make_json_serializable(default_val)
            except Exception:
                pass

        schema = self._normalize_pydantic_schema(config_model)

        return {
            "prefix": prefix,
            "values": values,
            "schema": schema,
        }

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
                "config_file": config_file_path,
                "config_targets": config_targets,
            },
            "components": [self._get_component_info(c) for c in components],
            "plugins": [self._get_component_info(p) for p in plugins],
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
            result = await self._register_plugin_from_path(plugin_path)
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
            result = await self._save_component_config(component_name, config_values, target_file)
            await websocket.send(json.dumps(result))
            # Refresh state for all clients after config change
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
            logger=get_logger()
    ) -> dict:
        """Register a new plugin from a file path."""
        if not plugin_path:
            return {"type": "error", "error": "Plugin path required"}

        try:
            path = Path(plugin_path)
            if not path.exists():
                return {"type": "error", "error": f"File not found: {plugin_path}"}

            # Load the component from the file
            plugin = compile_component(path)
            plugin_name = plugin.__metadata__.get("name", "unknown")

            # Check if already registered
            existing = self._container.provided_plugin(plugin_name)
            if existing is not None:
                return {"type": "info", "message": f"Plugin '{plugin_name}' is already registered"}

            # Register and initialize the plugin in the main event loop
            # Note: This only registers the plugin in memory, it does NOT modify ioc.yaml
            async def register_and_init():
                await register_plugin(self._container, plugin)
                # Reconfigure wires up dependencies for the new plugin
                reconfigure_ioc_app(self._container, (plugin,))
                await initialize_components(plugin)

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._run_in_main_loop(register_and_init())
            )

            # Update the log buffer with the new component info
            if self._log_buffer:
                module_name = plugin.__name__
                display_name = plugin_name
                internals = component_internals(plugin)
                comp_type = internals.type.value
                with self._log_buffer._lock:
                    self._log_buffer._component_info[module_name] = (display_name, comp_type)

            return {"type": "success", "message": f"Plugin '{plugin_name}' registered and initialized successfully"}
        except Exception as e:
            logger.error(f"Error registering plugin from '{plugin_path}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _upload_plugin_file(
            self,
            filename: str,
            content: str,
            logger=get_logger()
    ) -> dict:
        """Handle single file plugin upload."""
        if not filename or not content:
            return {"type": "error", "error": "Filename and content required"}

        try:
            # Decode base64 content (sent from browser's FileReader.readAsDataURL)
            raw_bytes = base64.b64decode(content)

            # Try UTF-8 first, fall back to latin-1 (which can decode any byte sequence)
            try:
                decoded_content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                decoded_content = raw_bytes.decode("latin-1")

            # Create a temporary directory for the plugin
            temp_dir = Path(tempfile.mkdtemp(prefix="plugin_"))
            plugin_path = temp_dir / filename

            # Write the file
            plugin_path.write_text(decoded_content, encoding="utf-8")

            # Register the plugin
            return await self._register_plugin_from_path(str(plugin_path))
        except Exception as e:
            logger.error(f"Error uploading plugin file '{filename}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _upload_plugin_directory(
            self,
            dirname: str,
            files: List[Dict[str, str]],
            logger=get_logger()
    ) -> dict:
        """Handle directory plugin upload."""
        if not dirname or not files:
            return {"type": "error", "error": "Directory name and files required"}

        try:
            # Create a temporary directory for the plugin
            temp_dir = Path(tempfile.mkdtemp(prefix="plugin_"))

            # Write all files preserving directory structure
            for file_info in files:
                relative_path = file_info.get("path", "")
                content_b64 = file_info.get("content", "")
                if not relative_path or not content_b64:
                    continue

                # Decode base64 content
                raw_bytes = base64.b64decode(content_b64)

                # Try UTF-8 first, fall back to latin-1 (which can decode any byte sequence)
                try:
                    decoded_content = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    decoded_content = raw_bytes.decode("latin-1")

                file_path = temp_dir / relative_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(decoded_content, encoding="utf-8")

            # The plugin directory is the first component of the path
            plugin_dir = temp_dir / dirname

            # Register the plugin
            return await self._register_plugin_from_path(str(plugin_dir))
        except Exception as e:
            logger.error(f"Error uploading plugin directory '{dirname}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _save_component_config(
            self,
            component_name: str,
            config_values: Dict[str, Any],
            target_file: str = "yaml",
            ioc_api=get_container_api(),
            logger=get_logger()
    ) -> dict:
        """Save configuration for a component to the specified target file.

        Args:
            component_name: Name of the component to save config for
            config_values: Dictionary of configuration values to save
            target_file: Target file type - "yaml", "env", or "context_env"
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

            # Get the config model and prefix
            config_model = component.__metadata__.get("config")
            if not config_model:
                return {"type": "error", "error": f"Component '{component_name}' has no configuration"}

            if isinstance(config_model, Iterable):
                config_model = config_model[0]  # Take the first model if multiple

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
        root_logger = logging.getLogger()
        root_logger.addHandler(self._log_handler)

        # Start HTTP server
        logger.info(f"Starting Management Dashboard on {config.host}:{config.port}")
        self._server = ThreadingHTTPServer(
            (config.host, config.port),
            DashboardRequestHandler
        )
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

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
