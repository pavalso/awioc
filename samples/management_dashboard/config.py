"""Dashboard configuration models."""

from pathlib import Path

import pydantic


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
        description="Directory path where uploaded plugins will be saved"
    )


# Path to the web assets directory
WEB_DIR = Path(__file__).parent / "static"
