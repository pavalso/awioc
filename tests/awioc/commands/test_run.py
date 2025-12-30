"""Tests for the run command."""

import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from src.awioc.commands.base import CommandContext
from src.awioc.commands.run import RunCommand


class TestRunCommand:
    """Tests for RunCommand class."""

    @pytest.fixture
    def command(self):
        """Create a RunCommand instance."""
        return RunCommand()

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "run"
        assert "AWIOC application" in command.description
        assert "awioc run" in command.help_text

    @pytest.mark.asyncio
    async def test_execute_sets_config_path_env(self, command):
        """Test execute sets CONFIG_PATH environment variable."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = []
        mock_api.provided_plugins.return_value = []

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock), \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock), \
                patch.dict(os.environ, {}, clear=True):
            mock_init.return_value = []

            ctx = CommandContext(command="run", args=[], config_path="/path/to/config.yaml")
            await command.execute(ctx)

            assert os.environ.get("CONFIG_PATH") == "/path/to/config.yaml"

    @pytest.mark.asyncio
    async def test_execute_sets_context_env(self, command):
        """Test execute sets CONTEXT environment variable."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = []
        mock_api.provided_plugins.return_value = []

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock), \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock), \
                patch.dict(os.environ, {}, clear=True):
            mock_init.return_value = []

            ctx = CommandContext(command="run", args=[], context="production")
            await command.execute(ctx)

            assert os.environ.get("CONTEXT") == "production"

    @pytest.mark.asyncio
    async def test_execute_initializes_app(self, command):
        """Test execute initializes the application."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = []
        mock_api.provided_plugins.return_value = []

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api) as mock_bootstrap, \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock) as mock_wait, \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock) as mock_shutdown:
            mock_init.return_value = []

            ctx = CommandContext(command="run", args=[])
            result = await command.execute(ctx)

            assert result == 0
            mock_bootstrap.assert_called_once()
            mock_wait.assert_called_once_with(mock_app)
            mock_shutdown.assert_called_once_with(mock_app)

    @pytest.mark.asyncio
    async def test_execute_initializes_libs(self, command):
        """Test execute initializes libraries."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_lib1 = MagicMock()
        mock_lib2 = MagicMock()
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = [mock_lib1, mock_lib2]
        mock_api.provided_plugins.return_value = []

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock), \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock):
            mock_init.return_value = []

            ctx = CommandContext(command="run", args=[])
            result = await command.execute(ctx)

            assert result == 0
            # Called for app, libs, and plugins
            assert mock_init.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_library_initialization_error(self, command):
        """Test execute returns error on library initialization failure."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = [MagicMock()]
        mock_api.provided_plugins.return_value = []

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock), \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock):
            # First call for app succeeds, second call for libs returns exception
            mock_init.side_effect = [
                None,  # App initialization
                [Exception("Library init failed")],  # Library initialization
            ]

            ctx = CommandContext(command="run", args=[])
            result = await command.execute(ctx)

            assert result == 1

    @pytest.mark.asyncio
    async def test_execute_plugin_initialization_error_continues(self, command):
        """Test execute continues on plugin initialization failure."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = []
        mock_api.provided_plugins.return_value = [MagicMock()]

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock), \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock):
            # First call for app, second for libs succeeds, third for plugins returns exception
            mock_init.side_effect = [
                None,  # App initialization
                [],  # Library initialization (no exceptions)
                [Exception("Plugin init failed")],  # Plugin initialization (but we continue)
            ]

            ctx = CommandContext(command="run", args=[])
            result = await command.execute(ctx)

            # Plugin errors are logged but don't stop execution
            assert result == 0

    @pytest.mark.asyncio
    async def test_execute_shutdown_called_on_success(self, command):
        """Test shutdown is called on successful completion."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = []
        mock_api.provided_plugins.return_value = []

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock), \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock) as mock_shutdown:
            mock_init.return_value = []

            ctx = CommandContext(command="run", args=[])
            await command.execute(ctx)

            mock_shutdown.assert_called_once_with(mock_app)

    @pytest.mark.asyncio
    async def test_execute_shutdown_called_on_exception(self, command):
        """Test shutdown is called even when exception occurs."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = []
        mock_api.provided_plugins.return_value = []

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock) as mock_wait, \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock) as mock_shutdown:
            mock_init.return_value = []
            mock_wait.side_effect = Exception("Wait failed")

            ctx = CommandContext(command="run", args=[])

            with pytest.raises(Exception, match="Wait failed"):
                await command.execute(ctx)

            # Shutdown should still be called
            mock_shutdown.assert_called_once_with(mock_app)

    @pytest.mark.asyncio
    async def test_execute_no_config_or_context(self, command):
        """Test execute without config_path or context."""
        mock_api = MagicMock()
        mock_app = MagicMock()
        mock_app.wait = None
        mock_api.provided_app.return_value = mock_app
        mock_api.provided_libs.return_value = []
        mock_api.provided_plugins.return_value = []

        original_env = os.environ.copy()

        with patch('src.awioc.commands.run.initialize_ioc_app', return_value=mock_api), \
                patch('src.awioc.commands.run.initialize_components', new_callable=AsyncMock) as mock_init, \
                patch('src.awioc.commands.run.wait_for_components', new_callable=AsyncMock), \
                patch('src.awioc.commands.run.shutdown_components', new_callable=AsyncMock):
            mock_init.return_value = []

            # Clear relevant env vars
            os.environ.pop("CONFIG_PATH", None)
            os.environ.pop("CONTEXT", None)

            ctx = CommandContext(command="run", args=[])
            result = await command.execute(ctx)

            assert result == 0
            # Environment should not have these set since they weren't provided
            assert "CONFIG_PATH" not in os.environ or os.environ.get("CONFIG_PATH") == original_env.get("CONFIG_PATH")
