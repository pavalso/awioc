"""Tests for the base command module."""

import pytest

from src.awioc.commands.base import (
    CommandContext,
    Command,
    BaseCommand,
    register_command,
    get_registered_commands,
)


class TestCommandContext:
    """Tests for CommandContext dataclass."""

    def test_default_values(self):
        """Test CommandContext default values."""
        ctx = CommandContext(command="test")
        assert ctx.command == "test"
        assert ctx.args == []
        assert ctx.verbose == 0
        assert ctx.config_path is None
        assert ctx.context is None
        assert ctx.extra == {}

    def test_with_all_values(self):
        """Test CommandContext with all values specified."""
        ctx = CommandContext(
            command="test",
            args=["arg1", "arg2"],
            verbose=2,
            config_path="/path/to/config.yaml",
            context="production",
            extra={"key": "value"}
        )
        assert ctx.command == "test"
        assert ctx.args == ["arg1", "arg2"]
        assert ctx.verbose == 2
        assert ctx.config_path == "/path/to/config.yaml"
        assert ctx.context == "production"
        assert ctx.extra == {"key": "value"}

    def test_is_dataclass(self):
        """Test that CommandContext is a dataclass."""
        ctx = CommandContext(command="test")
        assert hasattr(ctx, "__dataclass_fields__")


class TestCommandProtocol:
    """Tests for Command protocol."""

    def test_protocol_is_runtime_checkable(self):
        """Test that Command protocol is runtime checkable."""

        class ValidCommand:
            @property
            def name(self) -> str:
                return "valid"

            @property
            def description(self) -> str:
                return "Valid command"

            @property
            def help_text(self) -> str:
                return "Help text"

            async def execute(self, ctx: CommandContext) -> int:
                return 0

        cmd = ValidCommand()
        assert isinstance(cmd, Command)


class TestBaseCommand:
    """Tests for BaseCommand abstract class."""

    def test_help_text_default(self):
        """Test that help_text defaults to description."""

        class TestCommand(BaseCommand):
            @property
            def name(self) -> str:
                return "test"

            @property
            def description(self) -> str:
                return "Test description"

            async def execute(self, ctx: CommandContext) -> int:
                return 0

        cmd = TestCommand()
        assert cmd.help_text == "Test description"

    def test_custom_help_text(self):
        """Test that help_text can be overridden."""

        class TestCommand(BaseCommand):
            @property
            def name(self) -> str:
                return "test"

            @property
            def description(self) -> str:
                return "Test description"

            @property
            def help_text(self) -> str:
                return "Custom help text"

            async def execute(self, ctx: CommandContext) -> int:
                return 0

        cmd = TestCommand()
        assert cmd.help_text == "Custom help text"

    @pytest.mark.asyncio
    async def test_execute_implementation(self):
        """Test that execute can be implemented."""

        class TestCommand(BaseCommand):
            @property
            def name(self) -> str:
                return "test"

            @property
            def description(self) -> str:
                return "Test description"

            async def execute(self, ctx: CommandContext) -> int:
                return 42

        cmd = TestCommand()
        ctx = CommandContext(command="test")
        result = await cmd.execute(ctx)
        assert result == 42


class TestCommandRegistry:
    """Tests for command registry functions."""

    def test_register_command_decorator(self):
        """Test that register_command decorator works."""
        initial_count = len(get_registered_commands())

        @register_command("test_unique_command")
        class TestUniqueCommand(BaseCommand):
            @property
            def name(self) -> str:
                return "test_unique_command"

            @property
            def description(self) -> str:
                return "Test"

            async def execute(self, ctx: CommandContext) -> int:
                return 0

        registry = get_registered_commands()
        assert "test_unique_command" in registry
        assert registry["test_unique_command"] == TestUniqueCommand

    def test_get_registered_commands_returns_copy(self):
        """Test that get_registered_commands returns a copy."""
        registry1 = get_registered_commands()
        registry2 = get_registered_commands()

        # Should be equal but not the same object
        assert registry1 == registry2
        assert registry1 is not registry2

        # Modifying one shouldn't affect the other
        registry1["fake"] = None
        assert "fake" not in get_registered_commands()
