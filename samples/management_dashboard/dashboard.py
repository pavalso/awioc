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
import warnings
from collections import deque
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, Optional, Set

import pydantic
import websockets
import yaml
from pydantic_core import PydanticUndefined
from websockets.server import WebSocketServerProtocol

from awioc import (
    as_component,
    compile_component,
    component_internals,
    component_registration,
    ContainerInterface,
    get_config,
    get_container_api,
    get_logger,
    initialize_components,
    inject,
    is_awioc_project,
    open_project,
    reconfigure_ioc_app,
    register_plugin,
    shutdown_components,
)
from .config import DashboardConfig
from .http_handler import DashboardRequestHandler
from .models import ComponentState, DashboardLogHandler, log_buffer, LogBuffer, LogEntry


def _get_component_file(component) -> Optional[str]:
    """Get the file path for a component using AWIOC's component_registration API."""
    reg = component_registration(component)
    if reg and reg.file:
        return reg.file
    return getattr(component, '__file__', None)


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
        self._discovered_plugins: Dict[str, dict] = {}

    def set_container(self, container: ContainerInterface):
        self._container = container

    def set_plugin_upload_path(self, path: Path):
        self._plugin_upload_path = path

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        self._main_loop = loop

    def set_ws_loop(self, loop: asyncio.AbstractEventLoop):
        self._ws_loop = loop

    def set_log_buffer(self, buffer: LogBuffer):
        self._log_buffer = buffer

    def on_new_log(self, entry: LogEntry):
        """Callback when a new log entry is added."""
        if self._ws_loop and self._clients:
            asyncio.run_coroutine_threadsafe(self.broadcast_log(entry), self._ws_loop)

    async def broadcast_log(self, entry: LogEntry):
        await self.broadcast({"type": "log", "entry": entry.to_dict()})

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
        internals = component_internals(component)
        return ComponentState(
            is_initialized=internals.is_initialized,
            is_initializing=internals.is_initializing,
            is_shutting_down=internals.is_shutting_down,
        )

    def _get_component_info(self, component) -> dict:
        """Get detailed information about a component."""
        internals = component_internals(component)
        metadata = component.__metadata__
        state = self._get_component_state(component)
        config_info = self._get_component_config_info(component)

        requires = metadata.get("requires") or set()
        requires_names = [req.__metadata__.get("name", "unknown") for req in requires]

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
            "required_by": [req.__metadata__.get("name", "unknown") for req in internals.required_by],
            "config": config_info,
            "registration": registration_info,
            "internals": {
                "module": getattr(component, "__name__", "unknown"),
                "wire": metadata.get("wire", False),
                "requires": requires_names,
                "initialized_by": [req.__metadata__.get("name", "unknown") for req in internals.initialized_by],
            }
        }

    def _normalize_pydantic_schema(self, model: type[pydantic.BaseModel]) -> dict:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=pydantic.json_schema.PydanticJsonSchemaWarning)
            raw_schema = model.model_json_schema(ref_template="#/$defs/{model}")

        defs = raw_schema.get("$defs", {})

        if "$ref" in raw_schema:
            ref_name = raw_schema["$ref"].split("/")[-1]
            schema = defs.get(ref_name, {}).copy()
        else:
            schema = {k: v for k, v in raw_schema.items() if k != "$defs"}

        schema = self._resolve_refs(schema, defs)
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        schema.setdefault("required", [])

        for field_name, field in model.model_fields.items():
            prop = schema["properties"].get(field_name, {})
            default = field.default
            if default is not PydanticUndefined:
                try:
                    if isinstance(default, pydantic.BaseModel):
                        default = default.model_dump()
                    json.dumps(default)
                    prop.setdefault("default", default)
                except TypeError:
                    prop.setdefault("default", str(default))
            schema["properties"][field_name] = prop

        return schema

    def _resolve_refs(self, obj: Any, defs: dict) -> Any:
        """Recursively resolve all $ref references in a schema."""
        if isinstance(obj, dict):
            if "allOf" in obj and isinstance(obj["allOf"], list):
                merged = {}
                for item in obj["allOf"]:
                    resolved_item = self._resolve_refs(item, defs)
                    if isinstance(resolved_item, dict):
                        for k, v in resolved_item.items():
                            if k == "properties" and "properties" in merged:
                                merged["properties"].update(v)
                            elif k == "required" and "required" in merged:
                                merged["required"] = list(set(merged["required"]) | set(v))
                            else:
                                merged[k] = v
                for k, v in obj.items():
                    if k != "allOf" and k not in merged:
                        merged[k] = self._resolve_refs(v, defs)
                return merged

            if "$ref" in obj:
                ref_path = obj["$ref"]
                if ref_path.startswith("#/$defs/"):
                    ref_name = ref_path.split("/")[-1]
                    resolved = defs.get(ref_name, {}).copy()
                    resolved = self._resolve_refs(resolved, defs)
                    for k, v in obj.items():
                        if k != "$ref" and k not in resolved:
                            resolved[k] = self._resolve_refs(v, defs)
                    return resolved
                return obj

            return {k: self._resolve_refs(v, defs) for k, v in obj.items() if k != "$defs"}

        elif isinstance(obj, list):
            return [self._resolve_refs(item, defs) for item in obj]

        return obj

    def _get_component_config_info(self, component) -> Optional[list[dict]]:
        metadata = component.__metadata__
        config_model = metadata.get("config")

        if not config_model:
            return None

        if isinstance(config_model, (list, tuple, set, frozenset)):
            config_models = list(config_model)
        else:
            config_models = [config_model]

        configs = []
        for idx, model in enumerate(config_models):
            prefix = getattr(model, "__prefix__", None) or getattr(model, "__name__", f"config_{idx}")

            values = {}
            try:
                provided_config = self._container.provided_config(model)
                if provided_config:
                    values = self._make_json_serializable(provided_config.model_dump())
            except Exception:
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
                schema = {"type": "object", "properties": {}, "required": []}

            configs.append({"prefix": prefix, "values": values, "schema": schema})

        return configs if configs else None

    def _make_json_serializable(self, obj):
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(v) for v in obj]
        elif isinstance(obj, Path):
            return str(obj)
        elif hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, type(None))):
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)
        return obj

    def _get_full_state(self) -> dict:
        if not self._container:
            return {}

        components = self._container.components
        app = self._container.provided_app()
        plugins = self._container.provided_plugins()
        libs = self._container.provided_libs()

        initialized_count = sum(1 for c in components if component_internals(c).is_initialized)

        config_file_path = None
        config_targets = []
        try:
            ioc_config = self._container.ioc_config_model
            config_path = ioc_config.config_path
            config_file_path = str(config_path) if config_path else None

            if config_path:
                config_dir = config_path.parent
                config_targets.append({
                    "id": "yaml", "label": f"YAML ({config_path.name})",
                    "path": str(config_path), "exists": config_path.exists()
                })
                env_path = config_dir / ".env"
                config_targets.append({
                    "id": "env", "label": ".env",
                    "path": str(env_path), "exists": env_path.exists()
                })

                context = ioc_config.context
                if not context and config_path:
                    stem = config_path.stem
                    if stem.endswith('.conf') or stem.endswith('.config'):
                        context = stem.rsplit('.', 1)[0]
                    elif '.' in stem:
                        parts = stem.split('.')
                        if len(parts) == 2 and parts[0] in ('ioc', 'config', 'conf'):
                            context = parts[1]

                if context:
                    context_env_path = config_dir / f".{context}.env"
                    config_targets.append({
                        "id": "context_env", "label": f".{context}.env",
                        "path": str(context_env_path), "exists": context_env_path.exists()
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
        await self.broadcast(self._get_full_state())

    async def broadcast_component_update(self, component_name: str, component_info: dict, old_status: str,
                                         new_status: str):
        await self.broadcast({
            "type": "component_update",
            "component": component_info,
            "transition": {"from": old_status, "to": new_status}
        })

    async def check_state_changes(self):
        if not self._container or not self._clients:
            return

        state_changed = False
        for component in self._container.components:
            name = component.__metadata__.get("name", "unknown")
            current_state = self._get_component_state(component)
            previous_state = self._previous_states.get(name)

            if previous_state is None:
                self._previous_states[name] = current_state
            elif current_state != previous_state:
                state_changed = True
                await self.broadcast_component_update(
                    name, self._get_component_info(component),
                    previous_state.get_status_label(), current_state.get_status_label()
                )
                self._previous_states[name] = current_state

        if state_changed:
            await self.broadcast_state_summary()

    async def broadcast_state_summary(self):
        if not self._container:
            return

        components = self._container.components
        app = self._container.provided_app()
        plugins = self._container.provided_plugins()
        libs = self._container.provided_libs()

        await self.broadcast({
            "type": "state_summary",
            "state": {
                "app_name": app.__metadata__.get("name", "unknown"),
                "app_version": app.__metadata__.get("version", "unknown"),
                "total_components": len(components),
                "initialized_components": sum(1 for c in components if component_internals(c).is_initialized),
                "plugins_count": len(plugins),
                "libraries_count": len(libs),
            }
        })

    async def start_monitoring(self, interval: float = 0.25):
        self._monitoring = True
        while self._monitoring:
            try:
                await self.check_state_changes()
            except Exception:
                pass
            await asyncio.sleep(interval)

    def stop_monitoring(self):
        self._monitoring = False

    async def handle_client(self, websocket: WebSocketServerProtocol):
        await self.register(websocket)
        try:
            await websocket.send(json.dumps(self._get_full_state()))
            if self._log_buffer:
                await websocket.send(json.dumps({"type": "logs_history", "logs": self._log_buffer.get_all()}))

            async for message in websocket:
                try:
                    await self._handle_message(websocket, json.loads(message))
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "error": "Invalid JSON"}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def _handle_message(self, websocket: WebSocketServerProtocol, data: dict):
        action = data.get("action")
        result = None

        if action == "refresh":
            await websocket.send(json.dumps(self._get_full_state()))
        elif action == "get_logs" and self._log_buffer:
            last_id = data.get("since_id", 0)
            logs = self._log_buffer.get_since(last_id) if last_id else self._log_buffer.get_all()
            await websocket.send(json.dumps({"type": "logs_history", "logs": logs}))
        elif action == "clear_logs" and self._log_buffer:
            self._log_buffer.clear()
            await websocket.send(json.dumps({"type": "success", "message": "Logs cleared"}))
            await self.broadcast({"type": "logs_cleared"})
        elif action == "enable_plugin":
            result = await self._enable_plugin(data.get("name"))
        elif action == "disable_plugin":
            result = await self._disable_plugin(data.get("name"))
        elif action == "register_plugin":
            result = await self._register_plugin_from_path(data.get("path"),
                                                           class_reference=data.get("class_reference"))
        elif action == "upload_plugin":
            upload_type = data.get("type")
            if upload_type == "file":
                result = await self._upload_plugin_file(data.get("filename"), data.get("content"))
            elif upload_type == "directory":
                result = await self._upload_plugin_directory(data.get("dirname"), data.get("files"))
            else:
                result = {"type": "error", "error": "Invalid upload type"}
        elif action == "save_config":
            result = await self._save_component_config(
                data.get("name"), data.get("config"),
                data.get("target_file", "yaml"), data.get("prefix")
            )
        elif action == "unregister_plugin":
            result = await self._unregister_plugin(data.get("name"))
        elif action == "save_plugins":
            result = await self._save_plugins_to_config()
        elif action == "sync_plugins":
            result = await self._sync_plugins_from_path()
        elif action == "remove_plugin":
            result = await self._remove_plugin_file(data.get("path"))
        elif action == "list_pots":
            result = await self._list_pots()
        elif action == "list_pot_components":
            result = await self._list_pot_components(data.get("pot_name"))
        elif action == "register_pot_component":
            result = await self._register_plugin_from_path(f"@{data.get('pot_name')}/{data.get('component_name')}")

        if result:
            await websocket.send(json.dumps(result))
            if result.get("type") == "success":
                await self.broadcast_state()

    def _run_in_main_loop(self, coro) -> Any:
        if self._main_loop is None:
            raise RuntimeError("Main event loop not set")
        return asyncio.run_coroutine_threadsafe(coro, self._main_loop).result(timeout=30)

    @inject
    async def _enable_plugin(self, plugin_name: str, logger=get_logger()) -> dict:
        if not plugin_name:
            return {"type": "error", "error": "Plugin name required"}

        plugin = self._container.provided_plugin(plugin_name)
        if plugin is None:
            return {"type": "error", "error": f"Plugin '{plugin_name}' not found"}

        internals = component_internals(plugin)
        if internals.is_initialized:
            return {"type": "info", "message": f"Plugin '{plugin_name}' is already enabled"}

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._run_in_main_loop(initialize_components(plugin))
            )
            return {"type": "success", "message": f"Plugin '{plugin_name}' enabled successfully"}
        except Exception as e:
            logger.error(f"Error enabling plugin '{plugin_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _disable_plugin(self, plugin_name: str, logger=get_logger()) -> dict:
        if not plugin_name:
            return {"type": "error", "error": "Plugin name required"}

        plugin = self._container.provided_plugin(plugin_name)
        if plugin is None:
            return {"type": "error", "error": f"Plugin '{plugin_name}' not found"}

        internals = component_internals(plugin)
        if not internals.is_initialized:
            return {"type": "info", "message": f"Plugin '{plugin_name}' is already disabled"}

        active_dependents = [r for r in internals.required_by if component_internals(r).is_initialized]
        if active_dependents:
            return {"type": "error",
                    "error": f"Cannot disable: required by {[r.__metadata__.get('name') for r in active_dependents]}"}

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._run_in_main_loop(shutdown_components(plugin))
            )
            return {"type": "success", "message": f"Plugin '{plugin_name}' disabled successfully"}
        except Exception as e:
            logger.error(f"Error disabling plugin '{plugin_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _register_plugin_from_path(
            self, plugin_path: str, class_reference: Optional[str] = None,
            auto_initialize: bool = False, logger=get_logger()
    ) -> dict:
        if not plugin_path:
            return {"type": "error", "error": "Plugin path required"}

        try:
            path = Path(plugin_path)
            if not path.exists() and not plugin_path.startswith("@"):
                return {"type": "error", "error": f"File not found: {plugin_path}"}

            if class_reference:
                ref = class_reference.strip()
                if not ref.startswith(":"):
                    ref = f":{ref}"
                if not ref.endswith("()"):
                    ref = f"{ref}()"
                component_ref = f"{path}:{ref[1:]}"
            elif plugin_path.startswith("@"):
                component_ref = plugin_path
            elif is_awioc_project(path):
                project = open_project(path)
                if project.components and project.components[0].class_name:
                    logger.info(f"Auto-detected: {project.components[0].class_name}")
                    component_ref = f"{path}:{project.components[0].class_name}()"
                else:
                    component_ref = path
            else:
                component_ref = path

            plugin = compile_component(component_ref)
            plugin_name = plugin.__metadata__.get("name", "unknown")

            if self._container.provided_plugin(plugin_name) is not None:
                return {"type": "info", "message": f"Plugin '{plugin_name}' is already registered"}

            async def register_only():
                await register_plugin(self._container, plugin)
                reconfigure_ioc_app(self._container, (plugin,))
                if auto_initialize:
                    await initialize_components(plugin)

            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._run_in_main_loop(register_only())
            )

            if self._log_buffer:
                module_name = getattr(plugin, '__name__', type(plugin).__name__)
                internals = component_internals(plugin)
                with self._log_buffer._lock:
                    self._log_buffer._component_info[module_name] = (plugin_name, internals.type.value)

            if not plugin_path.startswith("@"):
                self._discovered_plugins.pop(str(path.resolve()), None)

            return {"type": "success", "message": f"Plugin '{plugin_name}' registered successfully"}
        except Exception as e:
            logger.error(f"Error registering plugin from '{plugin_path}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _upload_plugin_file(
            self, filename: str, content: str,
            config=get_config(DashboardConfig), ioc_api=get_container_api(), logger=get_logger()
    ) -> dict:
        if not filename or not content:
            return {"type": "error", "error": "Filename and content required"}

        try:
            raw_bytes = base64.b64decode(content)
            upload_path = Path(config.plugin_upload_path)
            if not upload_path.is_absolute():
                ioc_config = ioc_api.ioc_config_model
                upload_path = (ioc_config.config_path.parent if ioc_config.config_path else Path.cwd()) / upload_path

            upload_path.mkdir(parents=True, exist_ok=True)
            plugin_path = upload_path / filename

            if plugin_path.exists():
                return {"type": "error", "error": f"Plugin file '{filename}' already exists"}

            plugin_path.write_bytes(raw_bytes)
            logger.info(f"Saved plugin file to {plugin_path}")
            return await self._register_plugin_from_path(str(plugin_path), auto_initialize=False)
        except Exception as e:
            logger.error(f"Error uploading plugin file '{filename}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _upload_plugin_directory(
            self, dirname: str, files: List[Dict[str, str]],
            config=get_config(DashboardConfig), ioc_api=get_container_api(), logger=get_logger()
    ) -> dict:
        if not dirname or not files:
            return {"type": "error", "error": "Directory name and files required"}

        try:
            upload_path = Path(config.plugin_upload_path)
            if not upload_path.is_absolute():
                ioc_config = ioc_api.ioc_config_model
                upload_path = (ioc_config.config_path.parent if ioc_config.config_path else Path.cwd()) / upload_path

            upload_path.mkdir(parents=True, exist_ok=True)
            plugin_dir = upload_path / dirname

            if plugin_dir.exists():
                return {"type": "error", "error": f"Plugin directory '{dirname}' already exists"}

            for file_info in files:
                relative_path, content_b64 = file_info.get("path", ""), file_info.get("content", "")
                if relative_path and content_b64:
                    file_path = upload_path / relative_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(base64.b64decode(content_b64))

            logger.info(f"Saved plugin directory to {plugin_dir}")
            return await self._register_plugin_from_path(str(plugin_dir), auto_initialize=False)
        except Exception as e:
            logger.error(f"Error uploading plugin directory '{dirname}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _save_component_config(
            self, component_name: str, config_values: Dict[str, Any],
            target_file: str = "yaml", config_prefix: Optional[str] = None,
            ioc_api=get_container_api(), logger=get_logger()
    ) -> dict:
        if not component_name:
            return {"type": "error", "error": "Component name required"}
        if not config_values:
            return {"type": "error", "error": "Configuration values required"}
        if target_file not in ("yaml", "env", "context_env"):
            return {"type": "error", "error": f"Invalid target file: {target_file}"}

        try:
            component = next((c for c in self._container.components if c.__metadata__.get("name") == component_name),
                             None)
            if component is None:
                return {"type": "error", "error": f"Component '{component_name}' not found"}

            config_models = component.__metadata__.get("config")
            if not config_models:
                return {"type": "error", "error": f"Component '{component_name}' has no configuration"}

            config_models = list(config_models) if isinstance(config_models, (list, tuple, set, frozenset)) else [
                config_models]

            config_model = None
            if config_prefix:
                config_model = next((m for m in config_models if getattr(m, "__prefix__", None) == config_prefix), None)
                if not config_model:
                    return {"type": "error", "error": f"No config with prefix '{config_prefix}' found"}
            else:
                config_model = config_models[0]

            prefix = getattr(config_model, "__prefix__", None)
            if not prefix:
                return {"type": "error", "error": f"Configuration model has no prefix"}

            ioc_config = ioc_api.ioc_config_model
            SECRET_MASK = "**********"

            def filter_masked(obj):
                if isinstance(obj, dict):
                    return {k: filter_masked(v) for k, v in obj.items() if v != SECRET_MASK}
                elif isinstance(obj, list):
                    return [filter_masked(v) for v in obj if v != SECRET_MASK]
                return obj

            def serialize(obj):
                if isinstance(obj, dict):
                    return {k: serialize(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize(v) for v in obj]
                elif isinstance(obj, Path):
                    return str(obj)
                return obj

            filtered_values = serialize(filter_masked(config_values))
            if not filtered_values:
                return {"type": "info", "message": "No changes to save"}

            if target_file == "yaml":
                config_path = ioc_config.config_path
                if not config_path or not config_path.exists():
                    return {"type": "error", "error": "IOC configuration file not found"}

                with open(config_path, 'r', encoding='utf-8') as f:
                    existing = yaml.safe_load(f) or {}

                def deep_merge(base, updates):
                    result = base.copy()
                    for k, v in updates.items():
                        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                            result[k] = deep_merge(result[k], v)
                        else:
                            result[k] = v
                    return result

                existing[prefix] = deep_merge(existing.get(prefix, {}), filtered_values)

                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(existing, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

                target_display = str(config_path)
            else:
                config_path = ioc_config.config_path
                if not config_path:
                    return {"type": "error", "error": "IOC configuration path not set"}

                config_dir = config_path.parent
                if target_file == "env":
                    env_path = config_dir / ".env"
                else:
                    context = ioc_config.context
                    if not context:
                        return {"type": "error", "error": "No context configured"}
                    env_path = config_dir / f".{context}.env"

                existing_env = {}
                if env_path.exists():
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, _, value = line.partition('=')
                                existing_env[key.strip()] = value.strip()

                prefix_upper = prefix.upper()
                for key, value in filtered_values.items():
                    env_key = f"{prefix_upper}_{key.upper()}"
                    if isinstance(value, bool):
                        existing_env[env_key] = str(value).lower()
                    elif isinstance(value, (dict, list)):
                        existing_env[env_key] = json.dumps(value)
                    else:
                        existing_env[env_key] = str(value)

                with open(env_path, 'w', encoding='utf-8') as f:
                    for key, value in existing_env.items():
                        f.write(f"{key}={value}\n")

                target_display = str(env_path)

            try:
                reconfigure_ioc_app(self._container, components=(component,))
            except Exception as e:
                logger.warning(f"Could not reconfigure '{component_name}': {e}")

            return {"type": "success", "message": f"Saved {len(filtered_values)} field(s) to {target_display}"}

        except Exception as e:
            logger.error(f"Error saving config for '{component_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _unregister_plugin(self, plugin_name: str, logger=get_logger()) -> dict:
        if not plugin_name:
            return {"type": "error", "error": "Plugin name required"}

        plugin = self._container.provided_plugin(plugin_name)
        if plugin is None:
            return {"type": "error", "error": f"Plugin '{plugin_name}' not found"}

        internals = component_internals(plugin)
        if internals.is_initialized:
            return {"type": "error", "error": f"Cannot unregister active plugin '{plugin_name}'. Disable it first."}

        if internals.required_by:
            return {"type": "error",
                    "error": f"Cannot unregister: required by {[r.__metadata__.get('name') for r in internals.required_by]}"}

        try:
            self._container.unregister_plugins(plugin)

            if self._log_buffer:
                module_name = getattr(plugin, '__name__', type(plugin).__name__)
                with self._log_buffer._lock:
                    self._log_buffer._component_info.pop(module_name, None)

            self._previous_states.pop(plugin_name, None)
            return {"type": "success", "message": f"Plugin '{plugin_name}' unregistered successfully"}
        except Exception as e:
            logger.error(f"Error unregistering plugin '{plugin_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _sync_plugins_from_path(self, logger=get_logger()) -> dict:
        if not self._plugin_upload_path:
            return {"type": "error", "error": "Plugin upload path not configured"}

        if not self._plugin_upload_path.exists():
            self._plugin_upload_path.mkdir(parents=True, exist_ok=True)
            return {"type": "info", "message": f"Created plugin directory: {self._plugin_upload_path}"}

        try:
            plugin_paths_on_disk: Set[Path] = set()
            for item in self._plugin_upload_path.iterdir():
                if item.name.startswith('_') or item.name.startswith('.'):
                    continue
                if item.is_file() and item.suffix == '.py':
                    plugin_paths_on_disk.add(item.resolve())
                elif item.is_dir() and (item / '__init__.py').exists():
                    plugin_paths_on_disk.add(item.resolve())

            registered_paths: Set[Path] = set()
            registered_names: Set[str] = set()

            for plugin in self._container.provided_plugins():
                plugin_meta_name = plugin.__metadata__.get("name", "")
                if plugin_meta_name:
                    registered_names.add(plugin_meta_name)

                plugin_file = _get_component_file(plugin)
                if plugin_file:
                    plugin_path = Path(plugin_file).resolve()
                    registered_paths.add(plugin_path)
                    if plugin_path.suffix == '.py':
                        parent = plugin_path.parent
                        registered_paths.add(parent)
                        if (parent / '__init__.py').exists():
                            registered_paths.add(parent)

            self._discovered_plugins.clear()
            for path in plugin_paths_on_disk:
                is_registered = path in registered_paths
                if not is_registered and path.is_dir():
                    is_registered = (path / "__init__.py") in registered_paths

                if not is_registered:
                    if not is_awioc_project(path):
                        continue

                    try:
                        project = open_project(path)
                    except Exception:
                        continue

                    unregistered = [c for c in project.components if c.name not in registered_names]
                    if not unregistered:
                        continue

                    self._discovered_plugins[str(path)] = {
                        "name": project.name,
                        "path": str(path),
                        "is_directory": path.is_dir(),
                        "manifest_version": project.manifest_version,
                        "manifest_description": project.description or "",
                        "component_classes": [
                            {"class_name": c.class_name or "", "metadata_name": c.name,
                             "reference": f":{c.class_name}()" if c.class_name else ""}
                            for c in unregistered
                        ],
                    }

            if self._discovered_plugins:
                return {"type": "success", "message": f"Found {len(self._discovered_plugins)} unregistered plugin(s)"}
            return {"type": "info", "message": "No unregistered plugins found"}

        except Exception as e:
            logger.error("Error discovering plugins", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _remove_plugin_file(self, plugin_path: str, logger=get_logger()) -> dict:
        import shutil

        if not plugin_path:
            return {"type": "error", "error": "Plugin path required"}

        path = Path(plugin_path).resolve()

        if not self._plugin_upload_path:
            return {"type": "error", "error": "Plugin upload path not configured"}

        try:
            path.relative_to(self._plugin_upload_path.resolve())
        except ValueError:
            return {"type": "error", "error": "Cannot remove plugins outside upload directory"}

        if not path.exists():
            self._discovered_plugins.pop(str(path), None)
            return {"type": "error", "error": "Plugin file not found"}

        try:
            plugin_name = path.stem if path.is_file() else path.name
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

            self._discovered_plugins.pop(str(path), None)
            return {"type": "success", "message": f"Plugin '{plugin_name}' removed"}
        except Exception as e:
            logger.error(f"Error removing plugin '{plugin_path}'", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _save_plugins_to_config(self, ioc_api=get_container_api(), logger=get_logger()) -> dict:
        try:
            ioc_config = ioc_api.ioc_config_model
            config_path = ioc_config.config_path

            if not config_path or not config_path.exists():
                return {"type": "error", "error": "IOC configuration file not found"}

            with open(config_path, 'r', encoding='utf-8') as f:
                existing = yaml.safe_load(f) or {}

            config_dir = config_path.parent
            plugin_paths = []

            for plugin in self._container.provided_plugins():
                source_ref = plugin.__metadata__.get("_source_ref")
                if source_ref and source_ref.startswith("@"):
                    plugin_paths.append(source_ref)
                    continue

                plugin_file = _get_component_file(plugin)
                if plugin_file:
                    plugin_path = Path(plugin_file)
                    is_class_based = not hasattr(plugin, '__file__')

                    try:
                        path_str = str(plugin_path.relative_to(config_dir))
                    except ValueError:
                        path_str = str(plugin_path)

                    if plugin_path.name == "__init__.py":
                        path_str = str(Path(path_str).parent)

                    if is_class_based:
                        path_str = f"{path_str}:{type(plugin).__name__}()"

                    plugin_paths.append(path_str)

            existing.setdefault("components", {})["plugins"] = plugin_paths

            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            return {"type": "success", "message": f"Saved {len(plugin_paths)} plugin(s) to {config_path.name}"}
        except Exception as e:
            logger.error("Error saving plugins", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _list_pots(self, logger=get_logger()) -> dict:
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
                pots.append({
                    "name": pot_path.name,
                    "version": manifest.get("version", "?"),
                    "description": manifest.get("description", ""),
                    "component_count": len(manifest.get("components", {})),
                })

            return {"type": "success", "pots": pots}
        except Exception as e:
            logger.error("Error listing pots", exc_info=e)
            return {"type": "error", "error": str(e)}

    @inject
    async def _list_pot_components(self, pot_name: str, logger=get_logger()) -> dict:
        try:
            if not pot_name:
                return {"type": "error", "error": "Pot name required"}

            from awioc.commands.pot import get_pot_path, load_pot_manifest

            pot_path = get_pot_path(pot_name)
            if not pot_path.exists():
                return {"type": "error", "error": f"Pot not found: {pot_name}"}

            manifest = load_pot_manifest(pot_path)
            components_data = manifest.get("components", {})

            registered_refs = {p.__metadata__.get("_source_ref", "") for p in self._container.provided_plugins() if
                               p.__metadata__.get("_source_ref", "").startswith("@")}

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
                "type": "success", "pot_name": pot_name,
                "pot_version": manifest.get("version", "?"),
                "pot_description": manifest.get("description", ""),
                "components": components,
            }
        except Exception as e:
            logger.error(f"Error listing components in pot '{pot_name}'", exc_info=e)
            return {"type": "error", "error": str(e)}


# Global WebSocket manager instance
ws_manager = WebSocketManager()


@as_component(
    name="Management Dashboard",
    version="1.3.0",
    description="Management Dashboard App Component",
    wirings=("http_handler",),
    config=DashboardConfig,
)
class ManagementDashboardApp:
    """Management Dashboard App Component."""

    def __init__(self):
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[Thread] = None
        self._ws_thread: Optional[Thread] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._monitor_interval: float = 0.25
        self._log_handler: Optional[DashboardLogHandler] = None

    def _run_ws_server(self, host: str, port: int):
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)
        ws_manager.set_ws_loop(self._ws_loop)

        async def serve():
            monitor_task = asyncio.create_task(ws_manager.start_monitoring(self._monitor_interval))
            async with websockets.serve(ws_manager.handle_client, host, port):
                while self._running:
                    await asyncio.sleep(0.1)
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
            self, logger=get_logger(), config=get_config(DashboardConfig), container=get_container_api()
    ) -> None:
        self._shutdown_event = asyncio.Event()
        self._running = True
        self._monitor_interval = config.monitor_interval

        DashboardRequestHandler.container = container
        ws_manager.set_container(container)
        ws_manager.set_main_loop(asyncio.get_running_loop())

        log_buffer._buffer = deque(maxlen=config.log_buffer_size)
        component_info = {}
        for comp in container.components:
            display_name = comp.__metadata__.get("name", "unknown")
            internals = component_internals(comp)
            component_info[display_name] = (display_name, internals.type.value)
        log_buffer.set_component_info(component_info)

        ws_manager.set_log_buffer(log_buffer)
        self._log_handler = DashboardLogHandler(log_buffer, broadcast_callback=ws_manager.on_new_log)
        self._log_handler.setLevel(logging.DEBUG)
        logger.parent.addHandler(self._log_handler)

        logger.info(f"Starting Dashboard on {config.host}:{config.port}")
        self._server = ThreadingHTTPServer((config.host, config.port), DashboardRequestHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        upload_path = Path(config.plugin_upload_path)
        if not upload_path.is_absolute():
            ioc_config = container.ioc_config_model
            upload_path = (ioc_config.config_path.parent if ioc_config.config_path else Path.cwd()) / upload_path
        ws_manager.set_plugin_upload_path(upload_path)

        sync_result = await ws_manager._sync_plugins_from_path()
        if sync_result.get("type") in ("success", "info"):
            logger.info(sync_result.get("message"))

        logger.info(f"Starting WebSocket on {config.host}:{config.ws_port}")
        self._ws_thread = Thread(target=self._run_ws_server, args=(config.host, config.ws_port), daemon=True)
        self._ws_thread.start()

        logger.info(f"Dashboard running at http://{config.host}:{config.port}")

    async def wait(self) -> None:
        if self._shutdown_event:
            await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        self._running = False
        ws_manager.stop_monitoring()

        if self._shutdown_event:
            self._shutdown_event.set()

        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
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
