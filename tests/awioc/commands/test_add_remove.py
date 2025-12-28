"""Tests for the add and remove commands."""

import pytest
import yaml

from src.awioc.commands.add import AddCommand
from src.awioc.commands.base import CommandContext
from src.awioc.commands.remove import RemoveCommand


class TestAddCommand:
    """Tests for AddCommand class."""

    @pytest.fixture
    def command(self):
        """Create an AddCommand instance."""
        return AddCommand()

    @pytest.fixture
    def config_file(self, tmp_path):
        """Create a temporary config file."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({
            "components": {
                "app": "my_app:MyApp()",
                "plugins": [],
                "libraries": {}
            }
        }), encoding="utf-8")
        return config_path

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "add"
        assert "plugins or libraries" in command.description
        assert "awioc add" in command.help_text

    @pytest.mark.asyncio
    async def test_execute_no_args(self, command):
        """Test execute with no args."""
        ctx = CommandContext(command="add", args=[])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_execute_unknown_type(self, command):
        """Test execute with unknown component type."""
        ctx = CommandContext(command="add", args=["unknown", "path"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_add_plugin_no_path(self, command, config_file, monkeypatch):
        """Test add plugin without path."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="add", args=["plugin"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_add_plugin_config_not_found(self, command, tmp_path, monkeypatch):
        """Test add plugin when config doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="add", args=["plugin", "my_plugin.py"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_add_plugin_success(self, command, config_file, monkeypatch):
        """Test add plugin successfully."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="add", args=["plugin", "plugins/my_plugin.py"])
        result = await command.execute(ctx)
        assert result == 0

        # Verify plugin was added
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert "plugins/my_plugin.py" in config["components"]["plugins"]

    @pytest.mark.asyncio
    async def test_add_plugin_already_exists(self, command, config_file, monkeypatch):
        """Test add plugin that already exists."""
        monkeypatch.chdir(config_file.parent)

        # Add plugin first
        ctx = CommandContext(command="add", args=["plugin", "my_plugin.py"])
        await command.execute(ctx)

        # Try to add again
        result = await command.execute(ctx)
        assert result == 0  # Should succeed but warn

    @pytest.mark.asyncio
    async def test_add_plugin_creates_plugins_section(self, command, tmp_path, monkeypatch):
        """Test add plugin creates plugins section if missing."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({"components": {"app": "app:App()"}}))
        monkeypatch.chdir(tmp_path)

        ctx = CommandContext(command="add", args=["plugin", "my_plugin.py"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "plugins" in config["components"]

    @pytest.mark.asyncio
    async def test_add_plugin_creates_components_section(self, command, tmp_path, monkeypatch):
        """Test add plugin creates components section if missing."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({}))
        monkeypatch.chdir(tmp_path)

        ctx = CommandContext(command="add", args=["plugin", "my_plugin.py"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "components" in config
        assert "plugins" in config["components"]

    @pytest.mark.asyncio
    async def test_add_plugin_with_config_path(self, command, config_file):
        """Test add plugin with explicit config path."""
        ctx = CommandContext(
            command="add",
            args=["plugin", "my_plugin.py"],
            config_path=str(config_file)
        )
        result = await command.execute(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_add_library_no_args(self, command, config_file, monkeypatch):
        """Test add library without enough args."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="add", args=["library"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_add_library_only_name(self, command, config_file, monkeypatch):
        """Test add library with only name."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="add", args=["library", "db"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_add_library_config_not_found(self, command, tmp_path, monkeypatch):
        """Test add library when config doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="add", args=["library", "db", "database.py"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_add_library_success(self, command, config_file, monkeypatch):
        """Test add library successfully."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="add", args=["library", "db", "libs/database.py"])
        result = await command.execute(ctx)
        assert result == 0

        # Verify library was added
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["components"]["libraries"]["db"] == "libs/database.py"

    @pytest.mark.asyncio
    async def test_add_library_update_existing(self, command, config_file, monkeypatch):
        """Test add library updates existing entry."""
        monkeypatch.chdir(config_file.parent)

        # Add library first
        ctx = CommandContext(command="add", args=["library", "db", "old_path.py"])
        await command.execute(ctx)

        # Update with new path
        ctx = CommandContext(command="add", args=["library", "db", "new_path.py"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["components"]["libraries"]["db"] == "new_path.py"

    @pytest.mark.asyncio
    async def test_add_library_creates_sections(self, command, tmp_path, monkeypatch):
        """Test add library creates missing sections."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({}))
        monkeypatch.chdir(tmp_path)

        ctx = CommandContext(command="add", args=["library", "db", "database.py"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "components" in config
        assert "libraries" in config["components"]


class TestRemoveCommand:
    """Tests for RemoveCommand class."""

    @pytest.fixture
    def command(self):
        """Create a RemoveCommand instance."""
        return RemoveCommand()

    @pytest.fixture
    def config_file(self, tmp_path):
        """Create a temporary config file with plugins and libraries."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({
            "components": {
                "app": "my_app:MyApp()",
                "plugins": ["plugin1.py", "plugin2.py", "plugin3.py"],
                "libraries": {
                    "db": "libs/database.py",
                    "cache": "libs/cache.py"
                }
            }
        }), encoding="utf-8")
        return config_path

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "remove"
        assert "plugins or libraries" in command.description
        assert "awioc remove" in command.help_text

    @pytest.mark.asyncio
    async def test_execute_no_args(self, command):
        """Test execute with no args."""
        ctx = CommandContext(command="remove", args=[])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_execute_unknown_type(self, command):
        """Test execute with unknown component type."""
        ctx = CommandContext(command="remove", args=["unknown", "path"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_plugin_no_identifier(self, command, config_file, monkeypatch):
        """Test remove plugin without identifier."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["plugin"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_plugin_config_not_found(self, command, tmp_path, monkeypatch):
        """Test remove plugin when config doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="remove", args=["plugin", "my_plugin.py"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_plugin_no_plugins(self, command, tmp_path, monkeypatch):
        """Test remove plugin when no plugins are configured."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({"components": {}}))
        monkeypatch.chdir(tmp_path)

        ctx = CommandContext(command="remove", args=["plugin", "my_plugin.py"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_plugin_by_path(self, command, config_file, monkeypatch):
        """Test remove plugin by path."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["plugin", "plugin2.py"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert "plugin2.py" not in config["components"]["plugins"]
        assert len(config["components"]["plugins"]) == 2

    @pytest.mark.asyncio
    async def test_remove_plugin_by_index(self, command, config_file, monkeypatch):
        """Test remove plugin by index."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["plugin", "0"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert "plugin1.py" not in config["components"]["plugins"]
        assert len(config["components"]["plugins"]) == 2

    @pytest.mark.asyncio
    async def test_remove_plugin_index_out_of_range(self, command, config_file, monkeypatch):
        """Test remove plugin with index out of range."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["plugin", "99"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_plugin_not_found(self, command, config_file, monkeypatch):
        """Test remove plugin that doesn't exist."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["plugin", "nonexistent.py"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_library_no_name(self, command, config_file, monkeypatch):
        """Test remove library without name."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["library"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_library_config_not_found(self, command, tmp_path, monkeypatch):
        """Test remove library when config doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="remove", args=["library", "db"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_library_no_libraries(self, command, tmp_path, monkeypatch):
        """Test remove library when no libraries are configured."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({"components": {}}))
        monkeypatch.chdir(tmp_path)

        ctx = CommandContext(command="remove", args=["library", "db"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_library_success(self, command, config_file, monkeypatch):
        """Test remove library successfully."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["library", "db"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert "db" not in config["components"]["libraries"]
        assert "cache" in config["components"]["libraries"]

    @pytest.mark.asyncio
    async def test_remove_library_not_found(self, command, config_file, monkeypatch):
        """Test remove library that doesn't exist."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="remove", args=["library", "nonexistent"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_remove_plugin_with_config_path(self, command, config_file):
        """Test remove plugin with explicit config path."""
        ctx = CommandContext(
            command="remove",
            args=["plugin", "plugin1.py"],
            config_path=str(config_file)
        )
        result = await command.execute(ctx)
        assert result == 0
