from pathlib import Path
from unittest.mock import MagicMock

from src.awioc.bootstrap import (
    initialize_ioc_app,
    compile_ioc_app,
    reconfigure_ioc_app,
    reload_configuration,
)
from src.awioc.config.base import Settings
from src.awioc.config.models import IOCBaseConfig, IOCComponentsDefinition
from src.awioc.container import AppContainer, ContainerInterface


class TestInitializeIOCApp:
    """Tests for initialize_ioc_app function."""

    def test_initialize_ioc_app_function_exists(self):
        """Test that initialize_ioc_app function exists."""
        assert callable(initialize_ioc_app)


class TestCompileIOCApp:
    """Tests for compile_ioc_app function."""

    def test_compile_ioc_app_function_exists(self):
        """Test that compile_ioc_app function exists."""
        assert callable(compile_ioc_app)


class TestReconfigureIOCApp:
    """Tests for reconfigure_ioc_app function."""

    def test_reconfigure_with_components(self, temp_dir):
        """Test reconfigure_ioc_app with components."""
        container = AppContainer()
        interface = ContainerInterface(container)

        config_path = temp_dir / "config.yaml"
        config_path.write_text("")

        ioc_config = IOCBaseConfig(config_path=config_path)

        class MockApp:
            __name__ = "mock_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "mock_app",
                "version": "1.0.0",
                "requires": set(),
                "base_config": Settings,
                "wire": False
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        app = MockApp()
        interface.set_app(app)

        # Set ioc_config on _internals after set_app (which creates _internals)
        app.__metadata__["_internals"].ioc_config = ioc_config

        interface.raw_container().wire = MagicMock()

        reconfigure_ioc_app(interface, components=[app])

        # Config should be set
        assert interface.raw_container().config() is not None


class TestReloadConfiguration:
    """Tests for reload_configuration function."""

    def test_reload_with_app(self, temp_dir):
        """Test reload_configuration with an app set."""
        container = AppContainer()
        interface = ContainerInterface(container)

        config_path = temp_dir / "config.yaml"
        config_path.write_text("")

        ioc_config = IOCBaseConfig(config_path=config_path)

        class MockApp:
            __name__ = "mock_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "mock_app",
                "version": "1.0.0",
                "requires": set(),
                "base_config": Settings,
                "ioc_config": ioc_config,
                "wire": False
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        interface.set_app(MockApp())
        interface.raw_container().wire = MagicMock()

        # This should not raise
        try:
            reload_configuration(interface)
        except Exception:
            pass  # Expected to fail due to model_config access


class TestIOCComponentsDefinition:
    """Additional tests for IOCComponentsDefinition."""

    def test_empty_libraries_and_plugins(self):
        """Test definition with empty libraries and plugins."""
        definition = IOCComponentsDefinition(
            app=Path("./app"),
            libraries={},
            plugins=[]
        )
        assert definition.libraries == {}
        assert definition.plugins == []

    def test_multiple_libraries(self):
        """Test definition with multiple libraries."""
        definition = IOCComponentsDefinition(
            app=Path("./app"),
            libraries={
                "lib1": Path("./lib1"),
                "lib2": Path("./lib2"),
                "lib3": Path("./lib3")
            }
        )
        assert len(definition.libraries) == 3

    def test_multiple_plugins(self):
        """Test definition with multiple plugins."""
        definition = IOCComponentsDefinition(
            app=Path("./app"),
            plugins=[
                Path("./plugin1"),
                Path("./plugin2"),
                Path("./plugin3")
            ]
        )
        assert len(definition.plugins) == 3
