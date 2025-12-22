"""
HTTP File Server App Component

A full-featured HTTP file server similar to `python -m http.server` with:
- Directory browsing
- File upload
- Folder download as ZIP
- File/folder deletion
"""

import asyncio
import html
import io
import mimetypes
import os
import shutil
import urllib.parse
import zipfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Optional

import pydantic

from awioc import get_config, get_logger, inject


class ServerConfig(pydantic.BaseModel):
    """HTTP Server configuration."""
    __prefix__ = "server"

    host: str = "127.0.0.1"
    port: int = 8080
    root_dir: Path = Path("./public")
    allow_upload: bool = False
    allow_delete: bool = False
    allow_zip_download: bool = False


__metadata__ = {
    "name": "HTTP File Server",
    "version": "2.0.0",
    "description": "HTTP File Server with upload, download, and delete capabilities",
    "wire": True,
    "config": ServerConfig
}

# Global config reference (set during initialization)
_server_config: Optional[ServerConfig] = None


class FileServerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for file server operations."""

    @property
    def root_dir(self) -> Path:
        return _server_config.root_dir.resolve() if _server_config else Path(".").resolve()

    def _get_fs_path(self, url_path: str) -> Optional[Path]:
        """Convert URL path to filesystem path, ensuring it's within root."""
        # Decode URL and normalize
        decoded = urllib.parse.unquote(url_path)
        # Remove leading slash and normalize
        clean_path = decoded.lstrip("/")
        # Resolve to absolute path
        fs_path = (self.root_dir / clean_path).resolve()
        # Security check: ensure path is within root
        try:
            fs_path.relative_to(self.root_dir)
        except ValueError:
            return None
        return fs_path

    def _send_error_page(self, code: int, message: str):
        """Send an error page."""
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"""<!DOCTYPE html>
<html>
<head><title>Error {code}</title></head>
<body>
<h1>Error {code}</h1>
<p>{html.escape(message)}</p>
<a href="/">Back to root</a>
</body>
</html>""".encode("utf-8"))

    def _send_json(self, data: dict, code: int = 200):
        """Send a JSON response."""
        import json
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @inject
    def do_GET(self, logger=get_logger()):
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        url_path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        logger.info(f"GET {self.path} FROM {self.client_address[0]}:{self.client_address[1]}")

        # Handle ZIP download request
        if "zip" in query and _server_config and _server_config.allow_zip_download:
            self._handle_zip_download(url_path)
            return

        fs_path = self._get_fs_path(url_path)

        if fs_path is None:
            self._send_error_page(403, "Access denied: Path outside root directory")
            return

        if not fs_path.exists():
            self._send_error_page(404, f"Path not found: {url_path}")
            return

        if fs_path.is_dir():
            self._serve_directory(url_path, fs_path)
        else:
            self._serve_file(fs_path)

    def _serve_directory(self, url_path: str, fs_path: Path):
        """Serve a directory listing."""
        # Ensure URL path ends with /
        if not url_path.endswith("/"):
            self.send_response(301)
            self.send_header("Location", url_path + "/")
            self.end_headers()
            return

        entries = []
        try:
            for entry in sorted(fs_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size if entry.is_file() else 0,
                    "mtime": stat.st_mtime,
                })
        except PermissionError:
            self._send_error_page(403, "Permission denied")
            return

        # Generate HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        parent_link = ""
        if url_path != "/":
            parent = str(Path(url_path).parent)
            if not parent.endswith("/"):
                parent += "/"
            parent_link = f'<tr><td colspan="4"><a href="{html.escape(parent)}">📁 ..</a></td></tr>'

        rows = []
        for e in entries:
            name = html.escape(e["name"])
            href = html.escape(urllib.parse.quote(e["name"]))
            if e["is_dir"]:
                icon = "📁"
                href += "/"
                size_str = "-"
                zip_link = f'<a href="{href}?zip=1" title="Download as ZIP">📦</a>' if _server_config and _server_config.allow_zip_download else ""
            else:
                icon = "📄"
                size_str = self._format_size(e["size"])
                zip_link = ""

            delete_btn = ""
            if _server_config and _server_config.allow_delete:
                delete_btn = f'<button onclick="deleteItem(\'{href.rstrip("/")}\')">🗑️</button>'

            rows.append(f"""
                <tr>
                    <td><a href="{href}">{icon} {name}</a></td>
                    <td>{size_str}</td>
                    <td>{zip_link}</td>
                    <td>{delete_btn}</td>
                </tr>
            """)

        upload_form = ""
        if _server_config and _server_config.allow_upload:
            upload_form = """
            <div class="upload-section">
                <h3>Upload Files</h3>
                <form id="uploadForm" enctype="multipart/form-data">
                    <input type="file" id="fileInput" name="files" multiple>
                    <button type="submit">Upload</button>
                </form>
                <div id="uploadStatus"></div>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Index of {html.escape(url_path)}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #00d9ff; }}
        table {{ border-collapse: collapse; width: 100%; max-width: 900px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background: #16213e; color: #00d9ff; }}
        a {{ color: #00d9ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        tr:hover {{ background: rgba(0, 217, 255, 0.05); }}
        button {{ background: #ff5252; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; }}
        button:hover {{ background: #ff1744; }}
        .upload-section {{ margin-top: 30px; padding: 20px; background: #16213e; border-radius: 10px; max-width: 900px; }}
        .upload-section h3 {{ color: #00d9ff; margin-top: 0; }}
        .upload-section input[type="file"] {{ margin-right: 10px; }}
        .upload-section button {{ background: #00c853; }}
        .upload-section button:hover {{ background: #00e676; }}
        #uploadStatus {{ margin-top: 10px; color: #888; }}
        .success {{ color: #00c853 !important; }}
        .error {{ color: #ff5252 !important; }}
    </style>
</head>
<body>
    <h1>Index of {html.escape(url_path)}</h1>
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Size</th>
                <th>ZIP</th>
                <th>Delete</th>
            </tr>
        </thead>
        <tbody>
            {parent_link}
            {"".join(rows)}
        </tbody>
    </table>
    {upload_form}
    <script>
        async function deleteItem(path) {{
            if (!confirm('Are you sure you want to delete this item?')) return;
            try {{
                const resp = await fetch(path, {{ method: 'DELETE' }});
                const data = await resp.json();
                if (resp.ok) {{
                    location.reload();
                }} else {{
                    alert('Error: ' + (data.error || 'Failed to delete'));
                }}
            }} catch (e) {{
                alert('Error: ' + e.message);
            }}
        }}

        document.getElementById('uploadForm')?.addEventListener('submit', async (e) => {{
            e.preventDefault();
            const fileInput = document.getElementById('fileInput');
            const status = document.getElementById('uploadStatus');

            if (!fileInput.files.length) {{
                status.textContent = 'Please select files to upload';
                status.className = 'error';
                return;
            }}

            const formData = new FormData();
            for (const file of fileInput.files) {{
                formData.append('files', file);
            }}

            status.textContent = 'Uploading...';
            status.className = '';

            try {{
                const resp = await fetch(window.location.pathname, {{
                    method: 'POST',
                    body: formData
                }});
                const data = await resp.json();
                if (resp.ok) {{
                    status.textContent = data.message || 'Upload successful!';
                    status.className = 'success';
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    status.textContent = 'Error: ' + (data.error || 'Upload failed');
                    status.className = 'error';
                }}
            }} catch (e) {{
                status.textContent = 'Error: ' + e.message;
                status.className = 'error';
            }}
        }});
    </script>
</body>
</html>"""
        self.wfile.write(html_content.encode("utf-8"))

    def _serve_file(self, fs_path: Path):
        """Serve a file."""
        try:
            content_type, _ = mimetypes.guess_type(str(fs_path))
            if content_type is None:
                content_type = "application/octet-stream"

            stat = fs_path.stat()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(stat.st_size))
            self.send_header("Content-Disposition", f'inline; filename="{fs_path.name}"')
            self.end_headers()

            with open(fs_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        except PermissionError:
            self._send_error_page(403, "Permission denied")
        except Exception as e:
            self._send_error_page(500, str(e))

    def _handle_zip_download(self, url_path: str):
        """Handle downloading a directory as ZIP."""
        fs_path = self._get_fs_path(url_path)

        if fs_path is None:
            self._send_error_page(403, "Access denied")
            return

        if not fs_path.exists() or not fs_path.is_dir():
            self._send_error_page(404, "Directory not found")
            return

        try:
            # Create ZIP in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(fs_path):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(fs_path)
                        try:
                            zf.write(file_path, arcname)
                        except PermissionError:
                            pass  # Skip files we can't read

            zip_data = zip_buffer.getvalue()
            zip_name = fs_path.name or "root"

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(zip_data)))
            self.send_header("Content-Disposition", f'attachment; filename="{zip_name}.zip"')
            self.end_headers()
            self.wfile.write(zip_data)
        except Exception as e:
            self._send_error_page(500, str(e))

    @inject
    def do_POST(self, logger=get_logger()):
        """Handle POST requests (file upload)."""
        logger.info(f"POST {self.path} FROM {self.client_address[0]}:{self.client_address[1]}")

        if not _server_config or not _server_config.allow_upload:
            self._send_json({"error": "Upload not allowed"}, 403)
            return

        fs_path = self._get_fs_path(self.path)
        if fs_path is None or not fs_path.is_dir():
            self._send_json({"error": "Invalid upload destination"}, 400)
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"error": "Invalid content type"}, 400)
            return

        try:
            # Parse multipart form data
            boundary = content_type.split("boundary=")[1].strip()
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            files_saved = []
            parts = body.split(f"--{boundary}".encode())

            for part in parts:
                if b"filename=" not in part:
                    continue

                # Extract filename
                header_end = part.find(b"\r\n\r\n")
                if header_end == -1:
                    continue

                header = part[:header_end].decode("utf-8", errors="ignore")
                file_content = part[header_end + 4:]
                if file_content.endswith(b"\r\n"):
                    file_content = file_content[:-2]

                # Parse filename from Content-Disposition
                for line in header.split("\r\n"):
                    if "filename=" in line:
                        start = line.find('filename="') + 10
                        end = line.find('"', start)
                        if end > start:
                            filename = line[start:end]
                            # Security: only use basename
                            filename = Path(filename).name
                            if filename:
                                dest = fs_path / filename
                                with open(dest, "wb") as f:
                                    f.write(file_content)
                                files_saved.append(filename)
                                logger.info(f"Uploaded: {dest}")

            if files_saved:
                self._send_json({"message": f"Uploaded {len(files_saved)} file(s): {', '.join(files_saved)}"})
            else:
                self._send_json({"error": "No files uploaded"}, 400)

        except Exception as e:
            logger.error(f"Upload error: {e}")
            self._send_json({"error": str(e)}, 500)

    @inject
    def do_DELETE(self, logger=get_logger()):
        """Handle DELETE requests."""
        logger.info(f"DELETE {self.path} FROM {self.client_address[0]}:{self.client_address[1]}")

        if not _server_config or not _server_config.allow_delete:
            self._send_json({"error": "Delete not allowed"}, 403)
            return

        fs_path = self._get_fs_path(self.path)
        if fs_path is None:
            self._send_json({"error": "Access denied"}, 403)
            return

        if not fs_path.exists():
            self._send_json({"error": "Path not found"}, 404)
            return

        # Prevent deleting the root directory
        if fs_path == self.root_dir:
            self._send_json({"error": "Cannot delete root directory"}, 403)
            return

        try:
            if fs_path.is_dir():
                shutil.rmtree(fs_path)
                logger.info(f"Deleted directory: {fs_path}")
            else:
                fs_path.unlink()
                logger.info(f"Deleted file: {fs_path}")

            self._send_json({"message": "Deleted successfully"})
        except PermissionError:
            self._send_json({"error": "Permission denied"}, 403)
        except Exception as e:
            logger.error(f"Delete error: {e}")
            self._send_json({"error": str(e)}, 500)

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class HttpServerApp:
    """
    HTTP File Server App Component.

    Provides a web-based file browser with upload, download, and delete capabilities.
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
            config=get_config(ServerConfig)
    ) -> None:
        """Start the HTTP server."""
        global _server_config
        _server_config = config

        self._shutdown_event = asyncio.Event()

        # Resolve and validate root directory
        root = config.root_dir.resolve()
        if not root.exists():
            logger.warning(f"Root directory does not exist, creating: {root}")
            root.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting HTTP File Server on {config.host}:{config.port}")
        logger.info(f"Serving files from: {root}")
        logger.info(f"Upload: {'enabled' if config.allow_upload else 'disabled'}")
        logger.info(f"Delete: {'enabled' if config.allow_delete else 'disabled'}")
        logger.info(f"ZIP download: {'enabled' if config.allow_zip_download else 'disabled'}")

        self._server = ThreadingHTTPServer((config.host, config.port), FileServerHandler)
        self._running = True

        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info(f"HTTP File Server running at http://{config.host}:{config.port}")

    async def wait(self) -> None:
        """Wait until shutdown is requested."""
        if self._shutdown_event:
            await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        """Stop the HTTP server."""
        global _server_config
        _server_config = None

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
