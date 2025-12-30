"""Tests for the config command."""

import pytest
import yaml

from src.awioc.commands.base import CommandContext
from src.awioc.commands.config import ConfigCommand


class TestConfigCommand:
    """Tests for ConfigCommand class."""

    @pytest.fixture
    def command(self):
        """Create a ConfigCommand instance."""
        return ConfigCommand()

    @pytest.fixture
    def config_file(self, tmp_path):
        """Create a temporary config file."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text(yaml.dump({
            "components": {
                "app": "my_app:MyApp()"
            },
            "server": {
                "host": "127.0.0.1",
                "port": 8080,
                "debug": True
            },
            "features": {
                "enabled": False
            }
        }), encoding="utf-8")
        return config_path

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "config"
        assert "configuration" in command.description
        assert "awioc config" in command.help_text

    @pytest.mark.asyncio
    async def test_show_config(self, command, config_file, monkeypatch, capsys):
        """Test showing all configuration."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=[])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "server:" in captured.out
        assert "port: 8080" in captured.out

    @pytest.mark.asyncio
    async def test_show_config_file_not_found(self, command, tmp_path, monkeypatch):
        """Test show config when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=[])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_show_config_invalid_yaml(self, command, tmp_path, monkeypatch):
        """Test show config with invalid YAML."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text("invalid: yaml: content: {[", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=[])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_get_config_no_key(self, command, config_file, monkeypatch):
        """Test get config without key."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["get"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_get_config_simple_key(self, command, config_file, monkeypatch, capsys):
        """Test get config with simple key."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["get", "server.port"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "8080" in captured.out

    @pytest.mark.asyncio
    async def test_get_config_nested_dict(self, command, config_file, monkeypatch, capsys):
        """Test get config with nested dict result."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["get", "server"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "host:" in captured.out
        assert "port:" in captured.out

    @pytest.mark.asyncio
    async def test_get_config_key_not_found(self, command, config_file, monkeypatch):
        """Test get config with key not found."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["get", "nonexistent.key"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_get_config_file_not_found(self, command, tmp_path, monkeypatch):
        """Test get config when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=["get", "server.port"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_get_config_invalid_yaml(self, command, tmp_path, monkeypatch):
        """Test get config with invalid YAML."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text("invalid: yaml: {[", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=["get", "key"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_set_config_no_args(self, command, config_file, monkeypatch):
        """Test set config without enough args."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_set_config_only_key(self, command, config_file, monkeypatch):
        """Test set config with only key."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "key"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_set_config_integer(self, command, config_file, monkeypatch):
        """Test set config with integer value."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "server.port", "9000"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["server"]["port"] == 9000

    @pytest.mark.asyncio
    async def test_set_config_float(self, command, config_file, monkeypatch):
        """Test set config with float value."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "server.timeout", "1.5"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["server"]["timeout"] == 1.5

    @pytest.mark.asyncio
    async def test_set_config_boolean_true(self, command, config_file, monkeypatch):
        """Test set config with boolean true value."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "features.enabled", "true"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["features"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_set_config_boolean_false(self, command, config_file, monkeypatch):
        """Test set config with boolean false value."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "server.debug", "false"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["server"]["debug"] is False

    @pytest.mark.asyncio
    async def test_set_config_boolean_yes(self, command, config_file, monkeypatch):
        """Test set config with yes/no values."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "features.enabled", "yes"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["features"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_set_config_boolean_no(self, command, config_file, monkeypatch):
        """Test set config with no value."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "features.enabled", "no"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["features"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_set_config_string_quoted(self, command, config_file, monkeypatch):
        """Test set config with quoted string."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "server.host", '"localhost"'])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["server"]["host"] == "localhost"

    @pytest.mark.asyncio
    async def test_set_config_string_single_quoted(self, command, config_file, monkeypatch):
        """Test set config with single quoted string."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "server.host", "'localhost'"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["server"]["host"] == "localhost"

    @pytest.mark.asyncio
    async def test_set_config_json_array(self, command, config_file, monkeypatch):
        """Test set config with JSON array."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "server.hosts", '["a", "b"]'])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["server"]["hosts"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_set_config_new_nested_key(self, command, config_file, monkeypatch):
        """Test set config creates nested structure."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["set", "new.nested.key", "value"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert config["new"]["nested"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_set_config_file_not_found(self, command, tmp_path, monkeypatch):
        """Test set config when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=["set", "key", "value"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_set_config_invalid_yaml(self, command, tmp_path, monkeypatch):
        """Test set config with invalid YAML."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text("invalid: yaml: {[", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=["set", "key", "value"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_unset_config_no_key(self, command, config_file, monkeypatch):
        """Test unset config without key."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["unset"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_unset_config_success(self, command, config_file, monkeypatch):
        """Test unset config successfully."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["unset", "server.debug"])
        result = await command.execute(ctx)
        assert result == 0

        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert "debug" not in config["server"]

    @pytest.mark.asyncio
    async def test_unset_config_key_not_found(self, command, config_file, monkeypatch):
        """Test unset config with key not found."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["unset", "nonexistent.key"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_unset_config_nested_not_found(self, command, config_file, monkeypatch):
        """Test unset config with nested path not found."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["unset", "server.missing.key"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_unset_config_file_not_found(self, command, tmp_path, monkeypatch):
        """Test unset config when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=["unset", "key"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_unset_config_invalid_yaml(self, command, tmp_path, monkeypatch):
        """Test unset config with invalid YAML."""
        config_path = tmp_path / "ioc.yaml"
        config_path.write_text("invalid: yaml: {[", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        ctx = CommandContext(command="config", args=["unset", "key"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_unknown_subcommand(self, command, config_file, monkeypatch):
        """Test unknown subcommand."""
        monkeypatch.chdir(config_file.parent)
        ctx = CommandContext(command="config", args=["unknown"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_with_config_path(self, command, config_file, capsys):
        """Test with explicit config path."""
        ctx = CommandContext(
            command="config",
            args=["get", "server.port"],
            config_path=str(config_file)
        )
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "8080" in captured.out

    def test_parse_value_on_off(self, command):
        """Test _parse_value with on/off values."""
        assert command._parse_value("on") is True
        assert command._parse_value("off") is False

    def test_parse_value_plain_string(self, command):
        """Test _parse_value with plain string."""
        assert command._parse_value("hello world") == "hello world"

    def test_get_nested_non_dict(self, command):
        """Test _get_nested with non-dict intermediate value."""
        obj = {"server": "not a dict"}
        result = command._get_nested(obj, "server.port")
        assert result is None

    def test_set_nested_overwrite_non_dict(self, command):
        """Test _set_nested overwrites non-dict value."""
        obj = {"server": "not a dict"}
        command._set_nested(obj, "server.port", 8080)
        assert obj["server"]["port"] == 8080
