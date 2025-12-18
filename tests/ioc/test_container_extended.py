import pytest
from dependency_injector import providers
from src.ioc.components.metadata import Internals
from src.ioc.config.base import Settings
from src.ioc.config.models import IOCBaseConfig
from src.ioc.container import AppContainer, ContainerInterface


class TestContainerInterfaceExtended:
    """Extended tests for ContainerInterface."""

    @pytest.fixture
    def container(self):
        """Create a container for testing."""
        return AppContainer()

    @pytest.fixture
    def interface(self, container):
        """Create a ContainerInterface for testing."""
        return ContainerInterface(container)

    def test_provided_config_with_model(self, interface):
        """Test provided_config with a specific model."""
        import pydantic

        class ConfigModel(pydantic.BaseModel):
            value: str = "test"

        # Create a settings object with the config as an attribute
        settings = Settings()
        # Manually add the config attribute
        object.__setattr__(settings, 'ConfigModel', ConfigModel())

        interface.set_config(settings)

        result = interface.provided_config(ConfigModel)
        assert isinstance(result, ConfigModel)
        assert result.value == "test"

    def test_app_config_model_with_none_base_config(self, interface):
        """Test app_config_model when base_config is explicitly None."""
        class AppWithNoneConfig:
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "base_config": None
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        interface.set_app(AppWithNoneConfig())

        assert interface.app_config_model == IOCBaseConfig

    def test_register_multiple_libraries(self, interface):
        """Test registering multiple libraries at once."""
        class Lib1:
            __metadata__ = {
                "name": "lib1",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        class Lib2:
            __metadata__ = {
                "name": "lib2",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        lib1 = Lib1()
        lib2 = Lib2()

        interface.register_libraries(("lib1", lib1), ("lib2", lib2))

        libs = interface.provided_libs()
        assert len(libs) == 2
        assert lib1 in libs
        assert lib2 in libs

    def test_register_library_with_type_key(self, interface):
        """Test registering library with type as key."""
        class TypedLib:
            __metadata__ = {
                "name": "typed_lib",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        lib = TypedLib()

        interface.register_libraries((TypedLib, lib))

        result = interface.provided_lib(TypedLib)
        assert result is lib

    def test_components_property_with_multiple_components(self, interface):
        """Test components property with multiple registered components."""
        class App:
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "requires": set()
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        class Lib:
            __metadata__ = {
                "name": "lib",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        app = App()
        lib = Lib()

        interface.set_app(app)
        interface.register_libraries(("lib", lib))

        components = interface.components
        assert len(components) >= 2

    def test_monotonic_id_increments(self, interface):
        """Test that monotonic_id is properly initialized."""
        assert interface._monotonic_id == 0


class TestContainerInterfacePlugins:
    """Tests for plugin-related ContainerInterface methods."""

    @pytest.fixture
    def interface(self):
        """Create a ContainerInterface for testing."""
        return ContainerInterface(AppContainer())

    def test_provided_plugins_returns_set(self, interface):
        """Test provided_plugins returns a set."""
        plugins = interface.provided_plugins()
        assert isinstance(plugins, set)


class TestAppContainerExtended:
    """Extended tests for AppContainer."""

    def test_container_components_singleton(self):
        """Test that components provider returns singleton dict."""
        container = AppContainer()

        comp1 = container.components()
        comp1["test"] = "value"

        comp2 = container.components()
        assert comp2["test"] == "value"
        assert comp1 is comp2

    def test_container_multiple_overrides(self):
        """Test multiple overrides on container."""
        container = AppContainer()

        config1 = Settings()
        config2 = Settings()

        container.config.override(providers.Object(config1))
        assert container.config() is config1

        container.config.override(providers.Object(config2))
        assert container.config() is config2

    def test_container_reset_override(self):
        """Test resetting overrides."""
        container = AppContainer()

        config = Settings()
        container.config.override(providers.Object(config))
        assert container.config() is config

        container.config.reset_override()
        # After reset, should return None (default)
        assert container.config() is None


class TestContainerInterfaceErrors:
    """Test error handling in ContainerInterface."""

    @pytest.fixture
    def interface(self):
        """Create a ContainerInterface for testing."""
        return ContainerInterface(AppContainer())

    def test_provided_lib_not_found(self, interface):
        """Test provided_lib raises KeyError for unknown library."""
        class UnknownLib:
            pass

        with pytest.raises(KeyError):
            interface.provided_lib(UnknownLib)


class TestContainerPluginRegistration:
    """Tests for plugin registration and unregistration."""

    @pytest.fixture
    def interface(self):
        """Create a ContainerInterface for testing."""
        return ContainerInterface(AppContainer())

    def test_register_plugins(self, interface):
        """Test registering plugins."""
        class MockPlugin:
            __metadata__ = {
                "name": "mock_plugin",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        plugin = MockPlugin()
        interface.register_plugins(plugin)

        # Plugin should be in provided_plugins
        plugins = interface.provided_plugins()
        assert plugin in plugins

    def test_register_multiple_plugins(self, interface):
        """Test registering multiple plugins."""
        class Plugin1:
            __metadata__ = {
                "name": "plugin1",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        class Plugin2:
            __metadata__ = {
                "name": "plugin2",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        p1 = Plugin1()
        p2 = Plugin2()
        interface.register_plugins(p1, p2)

        plugins = interface.provided_plugins()
        assert p1 in plugins
        assert p2 in plugins

    def test_unregister_plugins(self, interface):
        """Test unregistering plugins."""
        class MockPlugin:
            __metadata__ = {
                "name": "mock_plugin",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        plugin = MockPlugin()
        interface.register_plugins(plugin)

        # Verify plugin is registered
        assert plugin in interface.provided_plugins()

        # Unregister
        interface.unregister_plugins(plugin)

        # Plugin should no longer be in provided_plugins
        assert plugin not in interface.provided_plugins()

    def test_unregister_nonexistent_plugin(self, interface):
        """Test unregistering a plugin that's not registered."""
        class MockPlugin:
            __metadata__ = {
                "name": "mock_plugin",
                "version": "1.0.0",
                "requires": set()
            }
            initialize = None
            shutdown = None

        plugin = MockPlugin()
        # Add _internals manually to avoid __init_component
        plugin.__metadata__["_internals"] = Internals()

        # Should not raise, just silently skip
        interface.unregister_plugins(plugin)

