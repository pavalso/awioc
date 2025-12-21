"""
Management Dashboard App Component

A web server that exposes endpoints for:
- Listing all activated components
- Enabling/disabling plugins
- Showing overall application state
"""

import asyncio
import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Optional
from urllib.parse import urlparse

# Path to the web assets directory
WEB_DIR = Path(__file__).parent / "web"

import pydantic

from awioc import (
    get_config,
    get_logger,
    get_container_api,
    inject,
    ContainerInterface,
    component_internals,
    initialize_components,
    shutdown_components,
)


class DashboardConfig(pydantic.BaseModel):
    """Dashboard Server configuration."""
    __prefix__ = "dashboard"

    host: str = "127.0.0.1"
    port: int = 8090


__metadata__ = {
    "name": "management_dashboard_app",
    "version": "1.0.0",
    "description": "Management Dashboard for IOC Components",
    "wire": True,
    "config": DashboardConfig
}


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

        # Run initialization in event loop
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

        # Run shutdown in event loop
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
    """

    def __init__(self):
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[Thread] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None

    @inject
    async def initialize(
            self,
            logger=get_logger(),
            config=get_config(DashboardConfig),
            container=get_container_api()
    ) -> None:
        """Start the management dashboard server."""
        self._shutdown_event = asyncio.Event()

        # Store container reference in handler class
        DashboardRequestHandler.container = container

        logger.info(f"Starting Management Dashboard on {config.host}:{config.port}")

        self._server = ThreadingHTTPServer(
            (config.host, config.port),
            DashboardRequestHandler
        )
        self._running = True

        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info(f"Management Dashboard running at http://{config.host}:{config.port}")

    async def wait(self) -> None:
        """Wait until shutdown is requested."""
        if self._shutdown_event:
            await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        """Stop the management dashboard server."""
        self._running = False

        if self._shutdown_event:
            self._shutdown_event.set()

        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None


management_dashboard_app = ManagementDashboardApp()
initialize = management_dashboard_app.initialize
shutdown = management_dashboard_app.shutdown
wait = management_dashboard_app.wait
