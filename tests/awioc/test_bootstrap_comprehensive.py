"""Comprehensive tests for the bootstrap module."""

import logging
from pathlib import Path

from src.awioc.bootstrap import _is_manifest_directory
from src.awioc.config.base import Settings
from src.awioc.config.models import IOCBaseConfig, IOCComponentsDefinition
from src.awioc.container import AppContainer, ContainerInterface


class TestIsManifestDirectory:
    """Tests for _is_manifest_directory function."""

    def test_pot_reference_returns_false(self):
        """Test pot references return False."""
        assert _is_manifest_directory("@pot/component") is False
        assert _is_manifest_directory("@my-pot/my-component") is False

    def test_file_reference_returns_false(self, tmp_path):
        """Test file references return False."""
        file = tmp_path / "component.py"
        file.write_text("x = 1")
        assert _is_manifest_directory(str(file)) is False

    def test_directory_without_manifest_returns_false(self, tmp_path):
        """Test directory without manifest returns False."""
        dir_path = tmp_path / "component"
        dir_path.mkdir()
        assert _is_manifest_directory(str(dir_path)) is False

    def test_directory_with_manifest_returns_true(self, tmp_path):
        """Test directory with .awioc/manifest.yaml returns True."""
        dir_path = tmp_path / "component"
        awioc_dir = dir_path / ".awioc"
        awioc_dir.mkdir(parents=True)
        (awioc_dir / "manifest.yaml").write_text("manifest_version: '1.0'")

        assert _is_manifest_directory(str(dir_path)) is True

    def test_nonexistent_path_returns_false(self):
        """Test nonexistent path returns False."""
        assert _is_manifest_directory("/nonexistent/path") is False


class TestIOCComponentsDefinition:
    """Tests for IOCComponentsDefinition."""

    def test_basic_creation(self):
        """Test basic IOCComponentsDefinition creation."""
        comp_def = IOCComponentsDefinition(
            app="app:App()",
            plugins=["plugin1.py"],
            libraries={"db": "db.py"}
        )
        assert comp_def.app == "app:App()"
        assert comp_def.plugins == ["plugin1.py"]
        assert comp_def.libraries == {"db": "db.py"}

    def test_default_values(self):
        """Test default values for IOCComponentsDefinition."""
        comp_def = IOCComponentsDefinition(app="app:App()")
        assert comp_def.plugins == []
        assert comp_def.libraries == {}

    def test_with_multiple_plugins(self):
        """Test with multiple plugins."""
        comp_def = IOCComponentsDefinition(
            app="app:App()",
            plugins=["plugin1.py", "plugin2.py", "@pot/plugin3"]
        )
        assert len(comp_def.plugins) == 3

    def test_with_multiple_libraries(self):
        """Test with multiple libraries."""
        comp_def = IOCComponentsDefinition(
            app="app:App()",
            libraries={"db": "db.py", "cache": "cache.py", "queue": "queue.py"}
        )
        assert len(comp_def.libraries) == 3


class TestIOCBaseConfigModel:
    """Tests for IOCBaseConfig model."""

    def test_default_config_path(self):
        """Test default config_path."""
        config = IOCBaseConfig()
        assert config.config_path == Path("ioc.yaml")

    def test_default_context(self):
        """Test default context is None."""
        config = IOCBaseConfig()
        assert config.context is None

    def test_with_custom_config_path(self, tmp_path):
        """Test with custom config_path."""
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("")

        config = IOCBaseConfig(config_path=str(config_file))
        assert config.config_path == config_file

    def test_with_context(self):
        """Test with context."""
        config = IOCBaseConfig(context="production")
        assert config.context == "production"


class TestContainerInterface:
    """Tests for ContainerInterface integration."""

    def test_create_container_interface(self):
        """Test creating a ContainerInterface."""
        container = AppContainer()
        interface = ContainerInterface(container)
        assert interface is not None

    def test_container_interface_set_app(self):
        """Test setting app on ContainerInterface."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class TestApp:
            __metadata__ = {
                "name": "test",
                "version": "1.0.0",
                "requires": set(),
            }

            async def initialize(self): pass

            async def shutdown(self): pass

        interface.set_app(TestApp())
        assert interface.provided_app() is not None

    def test_container_interface_set_config(self):
        """Test setting config on ContainerInterface."""
        container = AppContainer()
        interface = ContainerInterface(container)

        interface.set_config(Settings())
        assert interface.provided_config() is not None

    def test_container_interface_set_logger(self):
        """Test setting logger on ContainerInterface."""
        container = AppContainer()
        interface = ContainerInterface(container)

        interface.set_logger(logging.getLogger("test"))
        assert interface.provided_logger() is not None

    def test_container_interface_register_plugins(self):
        """Test registering plugins on ContainerInterface."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class TestPlugin:
            __metadata__ = {
                "name": "test_plugin",
                "version": "1.0.0",
                "requires": set(),
            }
            initialize = None
            shutdown = None

        interface.register_plugins(TestPlugin())
        assert len(interface.provided_plugins()) == 1

    def test_container_interface_register_libraries(self):
        """Test registering libraries on ContainerInterface."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class TestLib:
            __metadata__ = {
                "name": "test_lib",
                "version": "1.0.0",
                "requires": set(),
            }
            initialize = None
            shutdown = None

        interface.register_libraries(("test_lib", TestLib()))
        assert len(interface.provided_libs()) == 1
