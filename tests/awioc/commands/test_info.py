"""Tests for the info command."""

import pytest
import yaml

from src.awioc.commands.base import CommandContext
from src.awioc.commands.info import InfoCommand
from src.awioc.loader.manifest import AWIOC_DIR, MANIFEST_FILENAME


class TestInfoCommand:
    """Tests for InfoCommand class."""

    @pytest.fixture
    def command(self):
        """Create InfoCommand instance."""
        return InfoCommand()

    @pytest.fixture
    def sample_ioc_yaml(self, temp_dir):
        """Create a sample ioc.yaml file."""
        config = {
            "components": {
                "app": "app.py:MyApp()",
                "libraries": {
                    "db": "libs/db.py",
                    "cache": "libs/cache.py",
                },
                "plugins": [
                    "plugins/plugin_a.py",
                    "plugins/plugin_b.py",
                ],
            },
        }
        config_path = temp_dir / "ioc.yaml"
        config_path.write_text(yaml.dump(config))
        return config_path

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "info"
        assert "project" in command.description.lower()
        assert "--show-manifest" in command.help_text

    @pytest.mark.asyncio
    async def test_execute_no_config(self, command, temp_dir, monkeypatch):
        """Test execute when no config file exists."""
        monkeypatch.chdir(temp_dir)
        ctx = CommandContext(command="info", args=[])

        result = await command.execute(ctx)

        assert result == 1  # Error exit code

    @pytest.mark.asyncio
    async def test_execute_with_config(self, command, temp_dir, sample_ioc_yaml, monkeypatch):
        """Test execute with valid config."""
        monkeypatch.chdir(temp_dir)
        ctx = CommandContext(command="info", args=[])

        result = await command.execute(ctx)

        assert result == 0

    @pytest.mark.asyncio
    async def test_execute_with_custom_config_path(self, command, temp_dir):
        """Test execute with custom config path."""
        config = {"components": {"app": "app.py"}}
        config_path = temp_dir / "custom.yaml"
        config_path.write_text(yaml.dump(config))

        ctx = CommandContext(
            command="info",
            args=[],
            config_path=str(config_path),
        )

        result = await command.execute(ctx)

        assert result == 0

    @pytest.mark.asyncio
    async def test_execute_detects_manifest(self, command, temp_dir, monkeypatch):
        """Test that info command detects manifest files."""
        # Create config
        plugins_dir = temp_dir / "plugins"
        plugins_dir.mkdir()

        # Use relative path like in real ioc.yaml
        config = {
            "components": {
                "app": "app.py",
                "plugins": ["plugins"],
            },
        }
        config_path = temp_dir / "ioc.yaml"
        config_path.write_text(yaml.dump(config))

        # Create manifest in plugins directory's .awioc folder
        manifest = {
            "manifest_version": "1.0",
            "components": [
                {"name": "plugin1", "file": "plugin1.py"},
            ],
        }
        awioc_dir = plugins_dir / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text(yaml.dump(manifest))

        monkeypatch.chdir(temp_dir)
        ctx = CommandContext(command="info", args=[])

        result = await command.execute(ctx)

        assert result == 0

    @pytest.mark.asyncio
    async def test_execute_show_manifest_flag(self, command, temp_dir, monkeypatch, capsys):
        """Test that --show-manifest displays manifest details."""
        # Create config
        plugins_dir = temp_dir / "plugins"
        plugins_dir.mkdir()

        # Use relative path like in real ioc.yaml
        config = {
            "components": {
                "app": "app.py",
                "plugins": ["plugins"],
            },
        }
        config_path = temp_dir / "ioc.yaml"
        config_path.write_text(yaml.dump(config))

        # Create manifest in .awioc folder
        manifest = {
            "manifest_version": "1.0",
            "components": [
                {"name": "test_plugin", "version": "1.0.0", "file": "test.py"},
            ],
        }
        awioc_dir = plugins_dir / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text(yaml.dump(manifest))

        monkeypatch.chdir(temp_dir)
        ctx = CommandContext(command="info", args=["--show-manifest"])

        result = await command.execute(ctx)

        assert result == 0
        captured = capsys.readouterr()
        assert "test_plugin" in captured.out

    @pytest.mark.asyncio
    async def test_execute_with_verbose(self, command, temp_dir, monkeypatch):
        """Test execute with verbose flag."""
        config = {
            "components": {"app": "app.py"},
            "database": {"host": "localhost", "port": 5432},
        }
        config_path = temp_dir / "ioc.yaml"
        config_path.write_text(yaml.dump(config))

        monkeypatch.chdir(temp_dir)
        ctx = CommandContext(command="info", args=[], verbose=1)

        result = await command.execute(ctx)

        assert result == 0


class TestInfoCommandHelpers:
    """Tests for InfoCommand helper methods."""

    @pytest.fixture
    def command(self):
        """Create InfoCommand instance."""
        return InfoCommand()

    def test_check_path_existing_file(self, command, temp_dir):
        """Test _check_path with existing file."""
        file_path = temp_dir / "component.py"
        file_path.write_text("# component")

        result = command._check_path("component.py", temp_dir)

        assert result is True

    def test_check_path_nonexistent(self, command, temp_dir):
        """Test _check_path with non-existent file."""
        result = command._check_path("nonexistent.py", temp_dir)

        assert result is False

    def test_check_path_with_class_reference(self, command, temp_dir):
        """Test _check_path with path:ClassName syntax."""
        file_path = temp_dir / "component.py"
        file_path.write_text("# component")

        result = command._check_path("component.py:MyClass()", temp_dir)

        assert result is True

    def test_check_path_local_reference(self, command, temp_dir):
        """Test _check_path with local :Reference syntax."""
        result = command._check_path(":MyClass()", temp_dir)

        assert result is True  # Local references always return True

    def test_check_path_with_manifest_existing(self, command, temp_dir):
        """Test _check_path_with_manifest with manifest."""
        plugins_dir = temp_dir / "plugins"
        plugins_dir.mkdir()
        awioc_dir = plugins_dir / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text("manifest_version: '1.0'")

        # Use relative path like in actual ioc.yaml
        exists, manifest_path = command._check_path_with_manifest(
            "plugins", temp_dir
        )

        assert exists is True
        assert manifest_path is not None

    def test_check_path_with_manifest_no_manifest(self, command, temp_dir):
        """Test _check_path_with_manifest without manifest."""
        plugins_dir = temp_dir / "plugins"
        plugins_dir.mkdir()

        # Use relative path like in actual ioc.yaml
        exists, manifest_path = command._check_path_with_manifest(
            "plugins", temp_dir
        )

        assert exists is True
        assert manifest_path is None

    def test_check_path_with_manifest_pot_reference(self, command, temp_dir):
        """Test _check_path_with_manifest with pot reference."""
        exists, manifest_path = command._check_path_with_manifest(
            "@my-pot/component", temp_dir
        )

        assert exists is True
        assert manifest_path is None

    def test_get_config_path_default(self, command):
        """Test _get_config_path with default path."""
        ctx = CommandContext(command="info", args=[])

        result = command._get_config_path(ctx)

        assert result.name == "ioc.yaml"

    def test_get_config_path_custom(self, command, temp_dir):
        """Test _get_config_path with custom path."""
        ctx = CommandContext(
            command="info",
            args=[],
            config_path=str(temp_dir / "custom.yaml"),
        )

        result = command._get_config_path(ctx)

        assert result.name == "custom.yaml"
