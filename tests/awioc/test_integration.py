"""
Comprehensive integration tests for the IOC framework.

These tests verify the full workflow of the framework including:
- Container lifecycle management
- Component registration and dependency chains
- Plugin registration/unregistration
- Configuration loading and injection
- Module loading and wiring
"""
import logging
from unittest.mock import MagicMock, AsyncMock

import pydantic
import pytest
from pydantic_settings import YamlConfigSettingsSource

from src.awioc.bootstrap import reconfigure_ioc_app
from src.awioc.components.lifecycle import (
    initialize_components,
    shutdown_components,
    register_plugin,
    unregister_plugin,
)
from src.awioc.components.metadata import Internals
from src.awioc.components.registry import (
    as_component,
    component_requires,
    component_internals,
    component_str,
)
from src.awioc.config.base import Settings
from src.awioc.config.models import IOCBaseConfig
from src.awioc.config.registry import clear_configurations
from src.awioc.container import AppContainer, ContainerInterface
from src.awioc.di.wiring import wire, inject_dependencies
from src.awioc.loader.module_loader import compile_component


class TestFullApplicationLifecycle:
    """Integration tests for the complete application lifecycle."""

    @pytest.fixture
    def app_component(self):
        """Create an app component for testing."""
        class TestApp:
            __name__ = "test_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "test_app",
                "version": "1.0.0",
                "description": "Test application",
                "requires": set(),
                "base_config": Settings,
                "wire": False,
            }
            initialized = False
            shutdown_called = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                self.shutdown_called = True

        return TestApp()

    @pytest.fixture
    def library_component(self):
        """Create a library component for testing."""
        class TestLibrary:
            __metadata__ = {
                "name": "test_library",
                "version": "1.0.0",
                "description": "Test library",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None
            data = {"key": "value"}

        return TestLibrary()

    @pytest.fixture
    def plugin_component(self):
        """Create a plugin component for testing."""
        class TestPlugin:
            __name__ = "test_plugin"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "test_plugin",
                "version": "1.0.0",
                "description": "Test plugin",
                "requires": set(),
                "wire": False,
            }
            initialized = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                pass

        return TestPlugin()

    async def test_full_lifecycle(self, app_component, library_component, plugin_component):
        """Test complete application lifecycle from setup to shutdown."""
        # Step 1: Create container
        container = AppContainer()
        interface = ContainerInterface(container)

        # Step 2: Register app
        interface.set_app(app_component)
        assert interface.provided_app() is app_component
        assert "_internals" in app_component.__metadata__

        # Step 3: Register library
        interface.register_libraries(("TestLibrary", library_component))
        libs = interface.provided_libs()
        assert library_component in libs

        # Step 4: Register plugin
        interface.register_plugins(plugin_component)
        plugins = interface.provided_plugins()
        assert plugin_component in plugins

        # Step 5: Set up logger and config
        logger = logging.getLogger("test")
        interface.set_logger(logger)
        config = Settings()
        interface.set_config(config)

        assert interface.provided_logger() is logger
        assert interface.provided_config() is config

        # Step 6: Initialize components
        components = [app_component, plugin_component]
        await initialize_components(*components)

        assert app_component.initialized is True
        assert plugin_component.initialized is True
        assert component_internals(app_component).is_initialized is True
        assert component_internals(plugin_component).is_initialized is True

        # Step 7: Shutdown components
        await shutdown_components(*components)

        assert app_component.shutdown_called is True
        assert component_internals(app_component).is_initialized is False
        assert component_internals(plugin_component).is_initialized is False

    async def test_components_property_lists_all(self, app_component, library_component, plugin_component):
        """Test that components property returns all registered components."""
        container = AppContainer()
        interface = ContainerInterface(container)

        interface.set_app(app_component)
        interface.register_libraries(("lib", library_component))
        interface.register_plugins(plugin_component)

        components = interface.components
        assert app_component in components
        assert library_component in components
        assert plugin_component in components
        assert len(components) == 3


class TestDependencyChains:
    """Integration tests for component dependency handling."""

    @pytest.fixture
    def base_component(self):
        """Create a base component with no dependencies."""
        class BaseComponent:
            __metadata__ = {
                "name": "base",
                "version": "1.0.0",
                "requires": set(),
            }
            initialized = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                pass

        return BaseComponent()

    @pytest.fixture
    def dependent_component(self, base_component):
        """Create a component that depends on base_component."""
        class DependentComponent:
            __metadata__ = {
                "name": "dependent",
                "version": "1.0.0",
                "requires": {base_component},
            }
            initialized = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                pass

        return DependentComponent()

    async def test_dependency_chain_initialization(self, base_component, dependent_component):
        """Test that components with dependencies are properly linked."""
        container = AppContainer()
        interface = ContainerInterface(container)

        # Register dependent first (has base as requirement)
        interface.set_app(dependent_component)

        # Check that base_component's internals were created and linked
        assert "_internals" in base_component.__metadata__
        assert "_internals" in dependent_component.__metadata__

        # Check required_by relationship
        base_internals = component_internals(base_component)
        assert dependent_component in base_internals.required_by

        # Get requirements using component_requires
        requires = component_requires(dependent_component)
        assert base_component in requires

    async def test_recursive_dependency_resolution(self):
        """Test recursive dependency chain resolution."""
        # Create a chain: level3 -> level2 -> level1
        level1 = type("Level1", (), {
            "__metadata__": {"name": "level1", "version": "1.0.0", "requires": set()}
        })()

        level2 = type("Level2", (), {
            "__metadata__": {"name": "level2", "version": "1.0.0", "requires": {level1}}
        })()

        level3 = type("Level3", (), {
            "__metadata__": {"name": "level3", "version": "1.0.0", "requires": {level2}}
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(level3)

        # Get all dependencies recursively
        all_deps = component_requires(level3, recursive=True)
        assert level2 in all_deps
        assert level1 in all_deps

        # Verify required_by chain
        assert level3 in component_internals(level2).required_by
        assert level2 in component_internals(level1).required_by

    async def test_shutdown_blocked_by_dependency(self):
        """Test that shutdown is blocked when component is still required."""
        base = type("Base", (), {
            "__metadata__": {"name": "base", "version": "1.0.0", "requires": set()},
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        dependent = type("Dependent", (), {
            "__metadata__": {"name": "dependent", "version": "1.0.0", "requires": {base}},
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(dependent)

        # Initialize both
        await initialize_components(base, dependent)

        # Try to shutdown base while dependent is still initialized
        # Should not actually shutdown because dependent is still using it
        await shutdown_components(base)

        # Base should NOT be shutdown because dependent still requires it
        assert component_internals(base).is_initialized is True


class TestPluginManagement:
    """Integration tests for plugin registration and lifecycle."""

    @pytest.fixture
    def container_with_app(self):
        """Create a container with an app already set."""
        container = AppContainer()
        interface = ContainerInterface(container)

        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        interface.set_app(app)
        interface.raw_container().wire = MagicMock()
        return interface

    @pytest.fixture
    def plugin(self):
        """Create a test plugin."""
        return type("Plugin", (), {
            "__name__": "plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "test_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

    async def test_plugin_registration_flow(self, container_with_app, plugin):
        """Test full plugin registration flow."""
        interface = container_with_app

        # Register plugin
        interface.register_plugins(plugin)

        # Verify plugin is registered
        assert plugin in interface.provided_plugins()
        assert "_internals" in plugin.__metadata__

        # Initialize plugin
        await initialize_components(plugin)
        assert component_internals(plugin).is_initialized is True

    async def test_plugin_unregistration_flow(self, container_with_app, plugin):
        """Test full plugin unregistration flow."""
        interface = container_with_app

        # Register and initialize plugin
        interface.register_plugins(plugin)
        await initialize_components(plugin)

        # Unregister plugin
        interface.unregister_plugins(plugin)

        # Verify plugin is unregistered
        assert plugin not in interface.provided_plugins()

    async def test_unregister_plugin_when_required_raises(self, container_with_app):
        """Test that unregistering a required plugin raises error."""
        interface = container_with_app

        # Create both plugins without dependency in metadata
        base_plugin = type("BasePlugin", (), {
            "__name__": "base_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "base_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        dependent_plugin = type("DependentPlugin", (), {
            "__name__": "dependent_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "dependent_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        # Register both plugins
        interface.register_plugins(base_plugin, dependent_plugin)

        # Manually set up the required_by relationship to simulate dependency
        base_internals = component_internals(base_plugin)
        base_internals.required_by.add(dependent_plugin)

        # Mock internals set initialized to True
        component_internals(base_plugin).is_initialized = True
        component_internals(dependent_plugin).is_initialized = True

        # Try to unregister base_plugin while it's still required
        with pytest.raises(RuntimeError, match="still required"):
            await unregister_plugin(interface, base_plugin)

    async def test_register_plugin_already_registered_returns_existing(self, container_with_app):
        """Test registering an already registered plugin returns it without re-registering."""
        interface = container_with_app

        plugin = type("DuplicatePlugin", (), {
            "__name__": "duplicate_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "duplicate_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        # Register plugin first time
        result1 = await register_plugin(interface, plugin)
        assert result1 is plugin
        assert plugin in interface.provided_plugins()

        # Reset wire mock to track second call
        interface.raw_container().wire.reset_mock()

        # Try to register same plugin again
        result2 = await register_plugin(interface, plugin)

        # Should return the same plugin without re-wiring
        assert result2 is plugin
        interface.raw_container().wire.assert_not_called()

    async def test_register_multiple_plugins_sequentially(self, container_with_app):
        """Test registering multiple plugins one by one."""
        interface = container_with_app

        plugins = []
        for i in range(3):
            plugin = type(f"Plugin{i}", (), {
                "__name__": f"plugin_{i}",
                "__module__": "test",
                "__package__": None,
                "__metadata__": {
                    "name": f"plugin_{i}",
                    "version": "1.0.0",
                    "requires": set(),
                    "wire": False,
                },
                "initialize": AsyncMock(return_value=True),
                "shutdown": AsyncMock()
            })()
            plugins.append(plugin)

        # Register each plugin
        for plugin in plugins:
            await register_plugin(interface, plugin)

        # All plugins should be registered
        registered = interface.provided_plugins()
        for plugin in plugins:
            assert plugin in registered

    async def test_unregister_plugin_not_registered_does_nothing(self, container_with_app):
        """Test unregistering a non-registered plugin does nothing."""
        interface = container_with_app

        plugin = type("NonRegisteredPlugin", (), {
            "__name__": "non_registered",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "non_registered",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        # Add _internals manually since it's not registered
        plugin.__metadata__["_internals"] = Internals()

        # Should not raise, just return
        await unregister_plugin(interface, plugin)

        # Plugin should still not be in the list
        assert plugin not in interface.provided_plugins()

    async def test_unregister_plugin_shuts_down_initialized_plugin(self, container_with_app):
        """Test unregistering an initialized plugin shuts it down first."""
        interface = container_with_app

        shutdown_mock = AsyncMock()
        plugin = type("InitializedPlugin", (), {
            "__name__": "initialized_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "initialized_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": shutdown_mock
        })()

        # Register and initialize
        await register_plugin(interface, plugin)
        await initialize_components(plugin)

        assert component_internals(plugin).is_initialized is True

        # Unregister should shutdown first
        await unregister_plugin(interface, plugin)

        # Verify shutdown was called
        shutdown_mock.assert_called_once()
        assert plugin not in interface.provided_plugins()

    async def test_unregister_plugin_not_initialized_skips_shutdown(self, container_with_app):
        """Test unregistering a non-initialized plugin skips shutdown."""
        interface = container_with_app

        shutdown_mock = AsyncMock()
        plugin = type("NotInitializedPlugin", (), {
            "__name__": "not_initialized_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "not_initialized_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": shutdown_mock
        })()

        # Register but don't initialize
        await register_plugin(interface, plugin)

        assert component_internals(plugin).is_initialized is False

        # Unregister
        await unregister_plugin(interface, plugin)

        # Shutdown should not be called
        shutdown_mock.assert_not_called()
        assert plugin not in interface.provided_plugins()

    async def test_plugin_register_unregister_cycle(self, container_with_app):
        """Test full register-initialize-shutdown-unregister cycle."""
        interface = container_with_app
        lifecycle_events = []

        class CyclePlugin:
            __name__ = "cycle_plugin"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "cycle_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }

            async def initialize(self):
                lifecycle_events.append("initialized")
                return True

            async def shutdown(self):
                lifecycle_events.append("shutdown")

        plugin = CyclePlugin()

        # Step 1: Register
        await register_plugin(interface, plugin)
        assert plugin in interface.provided_plugins()
        assert len(lifecycle_events) == 0

        # Step 2: Initialize
        await initialize_components(plugin)
        assert component_internals(plugin).is_initialized is True
        assert lifecycle_events == ["initialized"]

        # Step 3: Unregister (should trigger shutdown)
        await unregister_plugin(interface, plugin)
        assert plugin not in interface.provided_plugins()
        assert lifecycle_events == ["initialized", "shutdown"]

    async def test_register_plugin_with_dependencies(self, container_with_app):
        """Test registering a plugin that has dependencies via interface.register_plugins."""
        interface = container_with_app

        # Create base plugin
        base_plugin = type("BasePlugin", (), {
            "__name__": "base_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "base_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        # Create dependent plugin that requires base_plugin
        dependent_plugin = type("DependentPlugin", (), {
            "__name__": "dependent_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "dependent_plugin",
                "version": "1.0.0",
                "requires": {base_plugin},
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        # Register dependent plugin (this will also init base_plugin's internals)
        interface.register_plugins(dependent_plugin)

        # Both should have internals
        assert "_internals" in base_plugin.__metadata__
        assert "_internals" in dependent_plugin.__metadata__

        # base_plugin should have dependent_plugin in required_by
        base_internals = component_internals(base_plugin)
        assert dependent_plugin in base_internals.required_by

        # dependent_plugin should be registered
        assert dependent_plugin in interface.provided_plugins()

    async def test_unregister_plugins_in_correct_order(self, container_with_app):
        """Test unregistering plugins respects dependency order."""
        interface = container_with_app

        base_plugin = type("BasePlugin", (), {
            "__name__": "base_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "base_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        dependent_plugin = type("DependentPlugin", (), {
            "__name__": "dependent_plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "dependent_plugin",
                "version": "1.0.0",
                "requires": {base_plugin},
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        # Register dependent plugin first (this initializes base_plugin's internals via dependency resolution)
        interface.register_plugins(dependent_plugin)

        # Manually add base_plugin to plugins map (its internals are already created)
        from dependency_injector import providers
        interface._plugins_map[base_plugin.__metadata__["name"]] = providers.Object(base_plugin)

        # Initialize both
        await initialize_components(base_plugin, dependent_plugin)

        # Try to unregister base first - should fail because dependent requires it
        with pytest.raises(RuntimeError, match="still required"):
            await unregister_plugin(interface, base_plugin)

        # Unregister dependent first
        await unregister_plugin(interface, dependent_plugin)
        assert dependent_plugin not in interface.provided_plugins()

        # Now base can be unregistered
        await unregister_plugin(interface, base_plugin)
        assert base_plugin not in interface.provided_plugins()

    async def test_register_plugin_batch(self, container_with_app):
        """Test registering multiple plugins at once via interface."""
        interface = container_with_app

        plugin1 = type("BatchPlugin1", (), {
            "__name__": "batch_plugin_1",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "batch_plugin_1",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        plugin2 = type("BatchPlugin2", (), {
            "__name__": "batch_plugin_2",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "batch_plugin_2",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        # Register both at once
        interface.register_plugins(plugin1, plugin2)

        assert plugin1 in interface.provided_plugins()
        assert plugin2 in interface.provided_plugins()

    async def test_unregister_plugins_batch(self, container_with_app):
        """Test unregistering multiple plugins at once via interface."""
        interface = container_with_app

        plugin1 = type("UnregBatchPlugin1", (), {
            "__name__": "unreg_batch_plugin_1",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "unreg_batch_plugin_1",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        plugin2 = type("UnregBatchPlugin2", (), {
            "__name__": "unreg_batch_plugin_2",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "unreg_batch_plugin_2",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        # Register both
        interface.register_plugins(plugin1, plugin2)
        assert plugin1 in interface.provided_plugins()
        assert plugin2 in interface.provided_plugins()

        # Unregister both at once
        interface.unregister_plugins(plugin1, plugin2)

        assert plugin1 not in interface.provided_plugins()
        assert plugin2 not in interface.provided_plugins()


class TestConfigurationFlow:
    """Integration tests for configuration loading and injection."""

    @pytest.fixture
    def app_with_config(self):
        """Create an app with configuration."""

        class AppConfig(IOCBaseConfig):
            app_name: str = "test_app"
            debug: bool = False

        class TestApp:
            __name__ = "test_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "test_app",
                "version": "1.0.0",
                "requires": set(),
                "base_config": AppConfig,
                "wire": False,
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        return TestApp(), AppConfig

    def test_configuration_injection(self, app_with_config):
        """Test configuration injection flow."""
        app, AppConfig = app_with_config

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        # Set up configuration
        config = AppConfig()
        interface.set_config(config)

        # Verify config is accessible
        retrieved_config = interface.provided_config()
        assert retrieved_config is config
        assert retrieved_config.app_name == "test_app"
        assert retrieved_config.debug is False

    def test_app_config_model_property(self, app_with_config):
        """Test app_config_model returns the config class."""
        app, AppConfig = app_with_config

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        assert interface.app_config_model == AppConfig

    def test_ioc_config_model_property(self, app_with_config):
        """Test ioc_config_model returns the IOC config."""
        app, _ = app_with_config

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        # Set IOC config on internals
        ioc_config = IOCBaseConfig()
        app.__metadata__["_internals"].ioc_config = ioc_config

        assert interface.ioc_config_model is ioc_config


class TestComponentRegistry:
    """Integration tests for component registry functions."""

    def test_as_component_adds_metadata(self):
        """Test as_component adds metadata to plain objects."""
        class PlainObject:
            """A plain Python object."""
            pass

        obj = PlainObject()
        result = as_component(obj)

        assert hasattr(result, "__metadata__")
        # Name uses __qualname__ which includes class hierarchy
        assert "PlainObject" in result.__metadata__["name"]
        assert result.__metadata__["version"] == "0.0.0"
        assert hasattr(result, "initialize")
        assert hasattr(result, "shutdown")

    def test_as_component_preserves_existing_metadata(self):
        """Test as_component preserves existing metadata."""
        class ComponentWithMeta:
            __metadata__ = {
                "name": "custom_name",
                "version": "2.0.0",
            }

        obj = ComponentWithMeta()
        result = as_component(obj)

        assert result.__metadata__["name"] == "custom_name"
        assert result.__metadata__["version"] == "2.0.0"

    def test_component_str_format(self):
        """Test component_str returns correct format."""
        comp = type("Comp", (), {
            "__metadata__": {"name": "my_component", "version": "1.2.3"}
        })()

        result = component_str(comp)
        assert result == "my_component v1.2.3"


class TestModuleLoading:
    """Integration tests for module loading."""

    def test_compile_component_from_file(self, sample_component_module, reset_sys_modules):
        """Test loading component from a Python file."""
        component = compile_component(sample_component_module)

        assert hasattr(component, "__metadata__")
        assert component.__metadata__["name"] == "sample_component"
        assert component.__metadata__["version"] == "1.0.0"

    def test_compile_component_from_package(self, sample_component_package, reset_sys_modules):
        """Test loading component from a package directory."""
        component = compile_component(sample_component_package)

        assert hasattr(component, "__metadata__")
        assert component.__metadata__["name"] == "sample_package"
        assert component.__metadata__["version"] == "2.0.0"

    def test_compile_component_with_py_extension(self, temp_dir, reset_sys_modules):
        """Test loading component without .py extension."""
        module_path = temp_dir / "no_ext_component.py"
        module_path.write_text("""
__metadata__ = {
    "name": "no_ext_component",
    "version": "1.0.0",
}
initialize = None
shutdown = None
""")

        # Load using path without .py extension
        component = compile_component(temp_dir / "no_ext_component")

        assert component.__metadata__["name"] == "no_ext_component"

    def test_compile_component_not_found_raises(self, temp_dir):
        """Test that loading non-existent component raises error."""
        with pytest.raises(FileNotFoundError, match="Module not found"):
            compile_component(temp_dir / "nonexistent")


class TestContainerBootstrap:
    """Integration tests for container bootstrap functions."""

    def test_reconfigure_ioc_app_flow(self, temp_dir):
        """Test reconfigure_ioc_app configures all components."""
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
                "wire": False,
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        app = MockApp()
        interface.set_app(app)
        app.__metadata__["_internals"].ioc_config = ioc_config
        interface.raw_container().wire = MagicMock()

        reconfigure_ioc_app(interface, components=[app])

        # Verify config was set
        assert interface.raw_container().config() is not None


class TestWiringIntegration:
    """Integration tests for dependency wiring."""

    def test_inject_dependencies_registers_configs(self):
        """Test inject_dependencies registers component configurations."""
        import pydantic

        class ComponentConfig(pydantic.BaseModel):
            setting: str = "default"

        class ComponentWithConfig:
            __name__ = "component_with_config"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "component_with_config",
                "version": "1.0.0",
                "requires": set(),
                "config": {ComponentConfig},
                "wire": False,
            }
            initialize = None
            shutdown = None

        container = AppContainer()
        interface = ContainerInterface(container)

        component = ComponentWithConfig()
        interface.set_app(component)

        inject_dependencies(interface, components=[component])

        # Configuration should be registered now
        from src.awioc.config.registry import _CONFIGURATIONS
        assert "component_with_config" in _CONFIGURATIONS

    def test_wire_collects_module_names(self):
        """Test wire collects modules for wiring."""
        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        class TestComponent:
            __name__ = "test_component"
            __module__ = "test.module"
            __package__ = "test"
            __metadata__ = {
                "name": "test_component",
                "version": "1.0.0",
                "requires": set(),
                "wire": True,
                "wirings": {"submodule"},
            }
            initialize = None
            shutdown = None

        component = TestComponent()
        interface.set_app(component)

        wire(interface, components=[component])

        # Verify wire was called
        container.wire.assert_called_once()
        call_args = container.wire.call_args
        modules = call_args.kwargs.get("modules") or call_args.args[0]

        assert "test.module" in modules
        assert "test.submodule" in modules


class TestComponentLifecycleEdgeCases:
    """Integration tests for component lifecycle edge cases."""

    async def test_initialize_already_initialized_skips(self):
        """Test that initializing an already initialized component is skipped."""
        comp = type("Comp", (), {
            "__metadata__": {"name": "comp", "version": "1.0.0", "requires": set()},
            "initialize": AsyncMock(return_value=True)
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(comp)

        # Initialize once
        await initialize_components(comp)
        first_call_count = comp.initialize.call_count

        # Initialize again
        await initialize_components(comp)

        # Should not have called initialize again
        assert comp.initialize.call_count == first_call_count

    async def test_initialize_returns_components(self):
        """Test that initialize_components returns the components."""
        comp = type("Comp", (), {
            "__metadata__": {"name": "comp", "version": "1.0.0", "requires": set()},
            "initialize": AsyncMock(return_value=True)
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(comp)

        result = await initialize_components(comp)

        assert comp in result

    async def test_shutdown_not_initialized_skips(self):
        """Test that shutdown on non-initialized component is skipped."""
        comp = type("Comp", (), {
            "__metadata__": {"name": "comp", "version": "1.0.0", "requires": set()},
            "initialize": None,
            "shutdown": AsyncMock()
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(comp)

        # Shutdown without initialization
        await shutdown_components(comp)

        # Should not have called shutdown
        comp.shutdown.assert_not_called()

    async def test_initialize_with_return_exceptions(self):
        """Test initialize with return_exceptions=True."""
        comp = type("Comp", (), {
            "__metadata__": {"name": "comp", "version": "1.0.0", "requires": set()},
            "initialize": AsyncMock(side_effect=ValueError("test error"))
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(comp)

        exceptions = await initialize_components(comp, return_exceptions=True)

        assert len(exceptions) == 1
        assert isinstance(exceptions[0], ValueError)

    async def test_shutdown_with_return_exceptions(self):
        """Test shutdown with return_exceptions=True."""
        comp = type("Comp", (), {
            "__metadata__": {"name": "comp", "version": "1.0.0", "requires": set()},
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock(side_effect=ValueError("shutdown error"))
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(comp)

        await initialize_components(comp)
        exceptions = await shutdown_components(comp, return_exceptions=True)

        assert len(exceptions) == 1
        assert isinstance(exceptions[0], ValueError)


class TestCompleteLifecycle:
    """Test complete lifecycle with env, config files, and reconfiguration."""

    @pytest.fixture
    def env_and_config_files(self, tmp_path):
        """Create env and config files for testing."""
        # Create .env file
        env_file = tmp_path / ".env"
        env_file.write_text(
            "APP_NAME=test_from_env\n"
            "DEBUG=true\n"
            "DATABASE_HOST=localhost\n"
            "DATABASE_PORT=5432\n"
        )

        # Create config.yaml file
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "app_name: test_from_yaml\n"
            "database:\n"
            "  host: db.example.com\n"
            "  port: 3306\n"
        )

        return env_file, config_file

    async def test_complete_lifecycle_with_env_and_config_reconfiguration(self, tmp_path, env_and_config_files):
        """
        Test complete application lifecycle:
        1. Initialize app from environment variables and config file
        2. App reconfigures config at runtime
        3. Verify config changes are applied
        4. Clean shutdown
        """
        env_file, config_file = env_and_config_files
        clear_configurations()

        # Define a custom configuration model for the app
        class DatabaseConfig(pydantic.BaseModel):
            host: str = "default_host"
            port: int = 5432

        class AppConfig(Settings):
            app_name: str = "default_app"
            debug: bool = False
            database: DatabaseConfig = pydantic.Field(default_factory=DatabaseConfig)

        # Track initialization and reconfiguration events
        lifecycle_events = []

        class ReconfigurableApp:
            """An app that can reconfigure its own config."""
            __name__ = "reconfigurable_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "reconfigurable_app",
                "version": "1.0.0",
                "description": "App that reconfigures its config",
                "requires": set(),
                "base_config": AppConfig,
                "wire": False,
            }

            def __init__(self):
                self.container_interface = None
                self.initialized = False
                self.reconfigured = False

            async def initialize(self):
                lifecycle_events.append("app_initialized")
                self.initialized = True
                return True

            async def shutdown(self):
                lifecycle_events.append("app_shutdown")

            def reconfigure(self, new_config_data: dict):
                """Reconfigure the app with new config values."""
                lifecycle_events.append("app_reconfigured")
                self.reconfigured = True

                # Get current config and create updated version
                current_config = self.container_interface.provided_config()
                updated_data = current_config.model_dump()
                updated_data.update(new_config_data)

                # Create and set new config
                new_config = type(current_config).model_validate(updated_data)
                self.container_interface.set_config(new_config)

        # Step 1: Create container and register app
        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        app = ReconfigurableApp()
        app.container_interface = interface
        interface.set_app(app)

        # Step 2: Set up IOC config (simulating loading from env)
        ioc_config = IOCBaseConfig()
        object.__setattr__(ioc_config, 'config_path', config_file)
        app.__metadata__["_internals"].ioc_config = ioc_config

        # Step 3: Initial configuration (simulating reconfigure_ioc_app)
        initial_config = AppConfig(
            app_name="initial_app",
            debug=False,
            database=DatabaseConfig(host="initial_host", port=5432)
        )
        interface.set_config(initial_config)
        interface.set_logger(logging.getLogger("test"))

        # Step 4: Initialize the app
        await initialize_components(app)

        assert app.initialized is True
        assert "app_initialized" in lifecycle_events

        # Step 5: Verify initial config
        config = interface.provided_config()
        assert config.app_name == "initial_app"
        assert config.database.host == "initial_host"
        assert config.database.port == 5432

        # Step 6: App reconfigures its own config at runtime
        app.reconfigure({
            "app_name": "reconfigured_app",
            "debug": True,
            "database": {"host": "new_host", "port": 3307}
        })

        assert app.reconfigured is True
        assert "app_reconfigured" in lifecycle_events

        # Step 7: Verify reconfigured config
        new_config = interface.provided_config()
        assert new_config.app_name == "reconfigured_app"
        assert new_config.debug is True
        assert new_config.database.host == "new_host"
        assert new_config.database.port == 3307

        # Step 8: Shutdown
        await shutdown_components(app)

        assert "app_shutdown" in lifecycle_events
        assert component_internals(app).is_initialized is False

        # Verify lifecycle order
        assert lifecycle_events == ["app_initialized", "app_reconfigured", "app_shutdown"]

    async def test_full_bootstrap_reconfigure_cycle(self, tmp_path):
        """Test the full bootstrap and reconfigure cycle with real config loading."""
        clear_configurations()

        # Create config file
        config_file = tmp_path / "app_config.yaml"
        config_file.write_text(
            "service_name: my_service\n"
            "max_connections: 100\n"
        )

        # Define app config
        class ServiceConfig(IOCBaseConfig):
            service_name: str = "default_service"
            max_connections: int = 10

        class ServiceApp:
            __name__ = "service_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "service_app",
                "version": "2.0.0",
                "requires": set(),
                "base_config": ServiceConfig,
                "wire": False,
            }
            config_history = []

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

            def record_config(self, interface):
                """Record current config state."""
                cfg = interface.provided_config()
                self.config_history.append({
                    "service_name": cfg.service_name,
                    "max_connections": cfg.max_connections
                })

        # Setup
        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        app = ServiceApp()
        interface.set_app(app)

        # Configure IOC
        ioc_config = IOCBaseConfig()
        app.__metadata__["_internals"].ioc_config = ioc_config

        # Initial config from defaults
        interface.set_config(ServiceConfig())
        interface.set_logger(logging.getLogger("test"))

        # Record initial state
        app.record_config(interface)
        assert app.config_history[0]["service_name"] == "default_service"
        assert app.config_history[0]["max_connections"] == 10

        # Simulate reconfigure_ioc_app behavior
        ioc_config.add_sources(lambda x: YamlConfigSettingsSource(
            x,
            yaml_file=config_file
        ))
        reconfigure_ioc_app(interface, components=[app])

        # Record after reconfigure
        app.record_config(interface)

        # Config should now reflect file values
        final_config = interface.provided_config()
        assert final_config.service_name == "my_service"
        assert final_config.max_connections == 100

        # History shows the progression
        assert len(app.config_history) == 2
        assert app.config_history[1]["service_name"] == "my_service"

    async def test_multiple_reconfiguration_cycles(self, tmp_path):
        """Test multiple reconfiguration cycles during app lifetime."""
        clear_configurations()

        class DynamicConfig(Settings):
            feature_flags: dict = pydantic.Field(default_factory=dict)
            rate_limit: int = 100

        class DynamicApp:
            __name__ = "dynamic_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "dynamic_app",
                "version": "1.0.0",
                "requires": set(),
                "base_config": DynamicConfig,
                "wire": False,
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        app = DynamicApp()
        interface.set_app(app)

        # Set up minimal IOC config
        ioc_config = IOCBaseConfig()
        app.__metadata__["_internals"].ioc_config = ioc_config
        interface.set_logger(logging.getLogger("test"))

        # Cycle 1: Initial config
        config_v1 = DynamicConfig(
            feature_flags={"feature_a": True},
            rate_limit=100
        )
        interface.set_config(config_v1)

        await initialize_components(app)

        assert interface.provided_config().rate_limit == 100
        assert interface.provided_config().feature_flags["feature_a"] is True

        # Cycle 2: First reconfiguration
        config_v2 = DynamicConfig(
            feature_flags={"feature_a": True, "feature_b": True},
            rate_limit=200
        )
        interface.set_config(config_v2)

        assert interface.provided_config().rate_limit == 200
        assert interface.provided_config().feature_flags["feature_b"] is True

        # Cycle 3: Second reconfiguration
        config_v3 = DynamicConfig(
            feature_flags={"feature_a": False, "feature_b": True, "feature_c": True},
            rate_limit=50
        )
        interface.set_config(config_v3)

        assert interface.provided_config().rate_limit == 50
        assert interface.provided_config().feature_flags["feature_a"] is False
        assert interface.provided_config().feature_flags["feature_c"] is True

        # Shutdown after multiple reconfigs
        await shutdown_components(app)
        assert component_internals(app).is_initialized is False


class TestEndToEndScenarios:
    """End-to-end integration tests simulating real usage patterns."""

    async def test_microservice_setup_pattern(self, temp_dir):
        """Test a typical microservice setup pattern."""
        # Create components representing a microservice
        class DatabaseLibrary:
            __metadata__ = {
                "name": "database",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None
            connected = True

            def query(self, sql):
                return [{"id": 1, "name": "test"}]

        class CacheLibrary:
            __metadata__ = {
                "name": "cache",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None
            data = {}

            def get(self, key):
                return self.data.get(key)

            def set(self, key, value):
                self.data[key] = value

        db = DatabaseLibrary()
        cache = CacheLibrary()

        class AuthPlugin:
            __name__ = "auth_plugin"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "auth_plugin",
                "version": "1.0.0",
                "requires": set(),  # No direct dependency to avoid registration order issues
                "wire": False,
            }
            initialized = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                pass

        auth = AuthPlugin()

        class Application:
            __name__ = "app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "microservice",
                "version": "1.0.0",
                "requires": set(),  # Dependencies tracked at app level
                "base_config": Settings,
                "wire": False,
            }
            initialized = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                pass

        app = Application()

        # Setup container
        container = AppContainer()
        interface = ContainerInterface(container)

        # Register in order: libraries first, then plugins, then app
        interface.register_libraries(
            ("DatabaseLibrary", db),
            ("CacheLibrary", cache)
        )
        interface.register_plugins(auth)
        interface.set_app(app)

        # Setup config
        interface.set_config(Settings())
        interface.set_logger(logging.getLogger("microservice"))

        # Verify all components are accessible
        assert db in interface.provided_libs()
        assert cache in interface.provided_libs()
        assert auth in interface.provided_plugins()
        assert interface.provided_app() is app

        # Initialize components (libraries don't have initialize methods)
        await initialize_components(auth, app)

        # Verify initialized
        assert auth.initialized is True
        assert app.initialized is True

        # Use the services
        result = db.query("SELECT * FROM users")
        assert len(result) == 1

        cache.set("key", "value")
        assert cache.get("key") == "value"

        # Shutdown
        await shutdown_components(app, auth)

    async def test_plugin_hot_reload_pattern(self):
        """Test hot-reloading plugins at runtime."""
        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        interface.set_app(app)
        await initialize_components(app)

        # Create and register plugin v1
        plugin_v1 = type("PluginV1", (), {
            "__name__": "plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "my_plugin",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        interface.register_plugins(plugin_v1)
        await initialize_components(plugin_v1)

        assert plugin_v1 in interface.provided_plugins()

        # Shutdown and unregister plugin v1
        await shutdown_components(plugin_v1)
        interface.unregister_plugins(plugin_v1)

        assert plugin_v1 not in interface.provided_plugins()

        # Register plugin v2 (simulating hot reload)
        plugin_v2 = type("PluginV2", (), {
            "__name__": "plugin",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "my_plugin",
                "version": "2.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        interface.register_plugins(plugin_v2)
        await initialize_components(plugin_v2)

        assert plugin_v2 in interface.provided_plugins()
        assert component_internals(plugin_v2).is_initialized is True

    async def test_graceful_shutdown_with_dependencies(self):
        """Test graceful shutdown respects dependency order."""
        # Create components with dependencies
        base = type("Base", (), {
            "__metadata__": {"name": "base", "version": "1.0.0", "requires": set()},
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        middle = type("Middle", (), {
            "__metadata__": {"name": "middle", "version": "1.0.0", "requires": {base}},
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        top = type("Top", (), {
            "__metadata__": {"name": "top", "version": "1.0.0", "requires": {middle}},
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(top)

        # Initialize all
        await initialize_components(base, middle, top)

        # Shutdown from top to base (correct order)
        await shutdown_components(top)
        assert component_internals(top).is_initialized is False

        await shutdown_components(middle)
        assert component_internals(middle).is_initialized is False

        await shutdown_components(base)
        assert component_internals(base).is_initialized is False
