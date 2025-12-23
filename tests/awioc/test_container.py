import logging

import pytest
from dependency_injector import providers

from src.awioc.components.metadata import Internals, ComponentTypes
from src.awioc.config.base import Settings
from src.awioc.config.models import IOCBaseConfig
from src.awioc.container import AppContainer, ContainerInterface


class TestAppContainer:
    """Tests for AppContainer class."""

    def test_container_has_self_provider(self):
        """Test container has __self__ provider."""
        container = AppContainer()
        assert container.__self__() is container

    def test_container_has_api_provider(self):
        """Test container has api provider."""
        container = AppContainer()
        assert container.api() is None  # Default is None

    def test_container_has_config_provider(self):
        """Test container has config provider."""
        container = AppContainer()
        assert container.config() is None

    def test_container_has_logger_provider(self):
        """Test container has logger provider."""
        container = AppContainer()
        assert container.logger() is None

    def test_container_has_components_provider(self):
        """Test container has components provider."""
        container = AppContainer()
        assert container.components() == {}

    def test_container_override_config(self):
        """Test overriding config provider."""
        container = AppContainer()
        settings = Settings()
        container.config.override(providers.Object(settings))

        assert container.config() is settings


class TestContainerInterface:
    """Tests for ContainerInterface class."""

    @pytest.fixture
    def container(self):
        """Create a container for testing."""
        return AppContainer()

    @pytest.fixture
    def interface(self, container):
        """Create a ContainerInterface for testing."""
        return ContainerInterface(container)

    @pytest.fixture
    def mock_app(self):
        """Create a mock app component."""
        class MockApp:
            __metadata__ = {
                "name": "test_app",
                "version": "1.0.0",
                "description": "Test app",
                "requires": set()
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        return MockApp()

    @pytest.fixture
    def mock_library(self):
        """Create a mock library component."""
        class MockLibrary:
            __metadata__ = {
                "name": "test_lib",
                "version": "1.0.0",
                "description": "Test library",
                "requires": set()
            }
            initialize = None
            shutdown = None

        return MockLibrary()

    @pytest.fixture
    def mock_plugin(self):
        """Create a mock plugin component."""
        class MockPlugin:
            __metadata__ = {
                "name": "test_plugin",
                "version": "1.0.0",
                "description": "Test plugin",
                "requires": set()
            }
            initialize = None
            shutdown = None

        return MockPlugin()

    def test_interface_initializes_api(self, interface, container):
        """Test interface sets itself as api in container."""
        assert container.api() is interface

    def test_raw_container(self, interface, container):
        """Test raw_container returns the container."""
        assert interface.raw_container() is container

    def test_set_app(self, interface, mock_app):
        """Test setting the app component."""
        interface.set_app(mock_app)

        assert interface.provided_app() is mock_app
        assert "_internals" in mock_app.__metadata__

    def test_provided_app_raises_when_not_set(self, interface):
        """Test provided_app raises when no app is set."""
        with pytest.raises(RuntimeError, match="App component not set"):
            interface.provided_app()

    def test_set_logger(self, interface, container):
        """Test setting the logger."""
        logger = logging.getLogger("test")
        interface.set_logger(logger)

        assert container.logger() is logger

    def test_provided_logger(self, interface):
        """Test provided_logger returns the logger."""
        logger = logging.getLogger("test")
        interface.set_logger(logger)

        assert interface.provided_logger() is logger

    def test_set_config(self, interface, container):
        """Test setting the config."""
        config = Settings()
        interface.set_config(config)

        assert container.config() is config

    def test_provided_config_no_model(self, interface):
        """Test provided_config without model returns full config."""
        config = Settings()
        interface.set_config(config)

        result = interface.provided_config()
        assert result is config

    def test_register_libraries(self, interface, mock_library):
        """Test registering libraries."""
        interface.register_libraries(("test_lib", mock_library))

        libs = interface.provided_libs()
        assert mock_library in libs

    def test_provided_lib(self, interface):
        """Test provided_lib returns specific library."""
        class TestLib:
            __metadata__ = {
                "name": "test_lib",
                "version": "1.0.0",
                "description": "Test library",
                "requires": set()
            }
            initialize = None
            shutdown = None

        lib_instance = TestLib()
        interface.register_libraries((TestLib.__qualname__, lib_instance))

        result = interface.provided_lib(TestLib)
        assert result is lib_instance

    def test_provided_libs_empty(self, interface):
        """Test provided_libs with no libraries."""
        libs = interface.provided_libs()
        assert libs == set()

    def test_register_libraries_sets_type(self, interface, mock_library):
        """Test that registering library sets component type."""
        interface.register_libraries(("lib", mock_library))

        internals = mock_library.__metadata__["_internals"]
        assert internals.type == ComponentTypes.LIBRARY

    def test_components_property(self, interface, mock_app):
        """Test components property returns list."""
        interface.set_app(mock_app)

        components = interface.components
        assert mock_app in components

    def test_app_config_model(self, interface, mock_app):
        """Test app_config_model property."""
        interface.set_app(mock_app)

        config_model = interface.app_config_model
        assert config_model is IOCBaseConfig

    def test_app_config_model_returns_default_when_not_defined(self, interface):
        """Test app_config_model raises when not defined."""
        class AppNoConfig:
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "requires": set()
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        interface.set_app(AppNoConfig())

        assert interface.app_config_model == IOCBaseConfig

    def test_ioc_config_model(self, interface):
        """Test ioc_config_model property."""
        from src.awioc.config.models import IOCBaseConfig

        class AppWithIOCConfig:
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        app = AppWithIOCConfig()
        interface.set_app(app)

        # Set ioc_config on _internals after set_app (which creates _internals)
        app.__metadata__["_internals"].ioc_config = IOCBaseConfig()

        config = interface.ioc_config_model
        assert isinstance(config, IOCBaseConfig)

    def test_ioc_config_model_raises_when_not_defined(self, interface, mock_app):
        """Test ioc_config_model raises when not defined."""
        interface.set_app(mock_app)

        with pytest.raises(ValueError, match="IOC configuration model is not defined"):
            interface.ioc_config_model

    def test_provided_plugins_empty(self, interface):
        """Test provided_plugins with no plugins."""
        plugins = interface.provided_plugins()
        assert plugins == set()


class TestContainerInterfacePrivateMethods:
    """Tests for ContainerInterface private methods."""

    @pytest.fixture
    def interface(self):
        """Create a ContainerInterface for testing."""
        return ContainerInterface(AppContainer())

    def test_init_component_creates_internals(self, interface):
        """Test __init_component creates _internals."""
        class Component:
            __metadata__ = {
                "name": "comp",
                "version": "1.0.0",
                "requires": set()
            }

        comp = Component()
        interface._ContainerInterface__init_component(comp)

        assert "_internals" in comp.__metadata__
        assert isinstance(comp.__metadata__["_internals"], Internals)

    def test_init_component_with_requirements(self, interface):
        """Test __init_component initializes requirements."""
        dep = type("Dep", (), {
            "__metadata__": {
                "name": "dep",
                "version": "1.0.0",
                "requires": set()
            }
        })()

        comp = type("Comp", (), {
            "__metadata__": {
                "name": "comp",
                "version": "1.0.0",
                "requires": {dep}
            }
        })()

        interface._ContainerInterface__init_component(comp)

        assert "_internals" in dep.__metadata__
        assert comp in dep.__metadata__["_internals"].required_by

    def test_deinit_component_removes_internals(self, interface):
        """Test __deinit_component removes _internals."""
        comp = type("Comp", (), {
            "__metadata__": {
                "name": "comp",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }
        })()

        interface._ContainerInterface__deinit_component(comp)

        assert comp.__metadata__["_internals"] is None
