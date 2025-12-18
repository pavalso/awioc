"""
Simple HTTP Server App Component

A minimal HTTP server demonstrating the IOC framework.
"""

import asyncio
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Optional

import pydantic
from ioc import get_config, get_logger, inject


class ServerConfig(pydantic.BaseModel):
    """HTTP Server configuration."""
    __prefix__ = "server"

    host: str = "127.0.0.1"
    port: int = 8080

__metadata__ = {
    "name": "http_server_app",
    "version": "1.0.0",
    "description": "Simple HTTP Server Application",
    "wire": True,
    "config": ServerConfig
}

class RequestHandler(BaseHTTPRequestHandler):
    """Simple HTTP request handler."""

    @inject
    def do_GET(
            self,
            logger=get_logger()
    ):
        """Handle GET requests."""
        logger.info(f"GET {self.path} FROM {self.client_address[0]}:{self.client_address[1]}")
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
<!DOCTYPE html>
<html>
<head><title>IOC Test Server</title></head>
<body>
    <h1>IOC Framework Test Server</h1>
    <p>The server is running successfully!</p>
    <ul>
        <li><a href="/health">Health Check</a></li>
        <li><a href="/info">Server Info</a></li>
    </ul>
</body>
</html>
""")
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy"}')
        elif self.path == "/info":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"name": "IOC Test Server", "version": "1.0.0"}')
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class HttpServerApp:
    """
    HTTP Server App Component.

    This is an AppComponent that runs a simple HTTP server.
    AppComponents require both initialize() and shutdown() methods.
    """

    def __init__(self):
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[Thread] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None

    @inject
    async def initialize(
            self,
            logger = get_logger(),
            config = get_config(ServerConfig)
    ) -> None:
        """Start the HTTP server."""
        self._shutdown_event = asyncio.Event()

        logger.info(f"Starting HTTP server on {config.host}:{config.port}")

        self._server = ThreadingHTTPServer((config.host, config.port), RequestHandler)
        self._running = True

        # Use serve_forever in a thread - it handles shutdown properly
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info(f"HTTP server running at http://{config.host}:{config.port}")

    async def wait(self) -> None:
        """Wait until shutdown is requested."""
        if self._shutdown_event:
            await self._shutdown_event.wait()

    async def shutdown(
            self
    ) -> None:
        """Stop the HTTP server."""
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

http_server_app = HttpServerApp()
initialize = http_server_app.initialize
shutdown = http_server_app.shutdown
wait = http_server_app.wait
