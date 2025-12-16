import pytest
import logging
from unittest.mock import MagicMock, patch
from pathlib import Path

from dependency_injector import providers

from src.ioc.container import AppContainer, ContainerInterface
from src.ioc.config.base import Settings
from src.ioc.config.models import IOCBaseConfig


class TestCreateContainer:
    """Tests for create_container function."""

    def test_create_container_returns_interface(self):
        """Test create_container returns a ContainerInterface."""
        from src.ioc.bootstrap import create_container
        interface = create_container()

        assert isinstance(interface, ContainerInterface)

    def test_create_container_has_raw_container(self):
        """Test create_container interface has a raw container."""
        from src.ioc.bootstrap import create_container
        interface = create_container()

        assert interface.raw_container() is not None

    def test_create_container_sets_api(self):
        """Test create_container sets api provider."""
        from src.ioc.bootstrap import create_container
        interface = create_container()

        assert interface.raw_container().api() is interface


class TestBootstrapIntegration:
    """Integration tests for bootstrap functions."""

    def test_container_interface_full_flow(self):
        """Test full container interface flow."""
        container = AppContainer()
        interface = ContainerInterface(container)

        # Set up app
        class TestApp:
            __metadata__ = {
                "name": "test",
                "version": "1.0.0",
                "requires": set(),
                "base_config": Settings
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        interface.set_app(TestApp())
        interface.set_config(Settings())
        interface.set_logger(logging.getLogger("test"))

        # Verify everything is set up
        assert interface.provided_app() is not None
        assert interface.provided_config() is not None
        assert interface.provided_logger() is not None

    def test_container_with_libraries(self):
        """Test container with library registration."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class TestLib:
            __metadata__ = {
                "name": "test_lib",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        interface.register_libraries(("test_lib", TestLib()))

        libs = interface.provided_libs()
        assert len(libs) == 1

    def test_ioc_base_config_model(self):
        """Test IOCBaseConfig model."""
        config = IOCBaseConfig()
        assert config.config_path is None
        assert config.context is None

    def test_ioc_base_config_with_values(self, temp_dir):
        """Test IOCBaseConfig with config_path."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("")

        config = IOCBaseConfig(config_path=str(config_file))
        assert config.config_path == config_file
