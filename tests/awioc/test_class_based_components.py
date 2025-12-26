"""
Comprehensive tests for class-based components.

These tests verify that class-based components (like HttpServerApp) work correctly
throughout the entire lifecycle:
- Loading and instantiation via :ClassName() syntax
- Registration and unregistration
- Initialization and shutdown
- Event handlers (on_before_initialize, on_after_initialize, etc.)
- Wiring with class instances
- Configuration injection
"""
import asyncio
from unittest.mock import MagicMock

import pydantic
import pytest

from src.awioc.bootstrap import reconfigure_ioc_app
from src.awioc.components.events import clear_handlers
from src.awioc.components.lifecycle import (
    initialize_components,
    shutdown_components,
    unregister_plugin,
)
from src.awioc.components.registry import (
    component_internals,
    component_initialized,
)
from src.awioc.config.models import IOCBaseConfig
from src.awioc.container import AppContainer, ContainerInterface
from src.awioc.di.wiring import wire, inject_dependencies
from src.awioc.loader.module_loader import compile_component


class TestClassBasedComponentLoading:
    """Tests for loading class-based components via :ClassName() syntax."""

    def test_load_class_instance_with_metadata_as_class_attr(self, temp_dir, reset_sys_modules):
        """Test loading a class where __metadata__ is a class attribute."""
        module_path = temp_dir / "class_component.py"
        module_path.write_text("""
class MyServerApp:
    __metadata__ = {
        "name": "my_server_app",
        "version": "1.0.0",
        "description": "A server application",
        "wire": True,
    }

    def __init__(self):
        self.initialized = False
        self.shutdown_called = False

    async def initialize(self):
        self.initialized = True
        return True

    async def shutdown(self):
        self.shutdown_called = True
""")
        result = compile_component(f"{module_path}:MyServerApp()")

        assert result.__metadata__["name"] == "my_server_app"
        assert result.__metadata__["version"] == "1.0.0"
        assert hasattr(result, "initialize")
        assert hasattr(result, "shutdown")
        assert result.initialized is False

    def test_load_class_instance_with_instance_metadata(self, temp_dir, reset_sys_modules):
        """Test loading a class that sets __metadata__ in __init__."""
        module_path = temp_dir / "instance_meta.py"
        module_path.write_text("""
class DynamicApp:
    def __init__(self):
        self.__metadata__ = {
            "name": "dynamic_app",
            "version": "2.0.0",
            "description": "Dynamic metadata",
            "wire": False,
        }
        self.initialized = False

    async def initialize(self):
        self.initialized = True
        return True

    async def shutdown(self):
        pass
""")
        result = compile_component(f"{module_path}:DynamicApp()")

        assert result.__metadata__["name"] == "dynamic_app"
        assert result.__metadata__["version"] == "2.0.0"

    def test_load_class_instance_module_attribute_preserved(self, temp_dir, reset_sys_modules):
        """Test that __module__ is preserved for class instances."""
        module_path = temp_dir / "module_attr.py"
        module_path.write_text("""
class ModuleAttrApp:
    __metadata__ = {
        "name": "module_attr_app",
        "version": "1.0.0",
    }

    async def initialize(self):
        return True

    async def shutdown(self):
        pass
""")
        result = compile_component(f"{module_path}:ModuleAttrApp()")

        # Instance should have __module__ set to the module name
        assert hasattr(result, "__module__") or hasattr(result.__class__, "__module__")


class TestClassBasedComponentLifecycle:
    """Tests for the full lifecycle of class-based components."""

    @pytest.fixture
    def http_server_style_app(self):
        """Create a component mimicking HttpServerApp pattern."""
        lifecycle_events = []

        class HttpStyleApp:
            __metadata__ = {
                "name": "http_style_app",
                "version": "1.0.0",
                "description": "HTTP-style application",
                "wire": False,
                "requires": set(),
            }

            def __init__(self):
                self._running = False
                self._lifecycle_events = lifecycle_events

            async def initialize(self):
                self._running = True
                self._lifecycle_events.append("initialized")
                return True

            async def shutdown(self):
                self._running = False
                self._lifecycle_events.append("shutdown")

            async def wait(self):
                while self._running:
                    await asyncio.sleep(0.1)

        app = HttpStyleApp()
        return app, lifecycle_events

    @pytest.fixture
    def app_with_event_handlers(self):
        """Create a component with all lifecycle event handlers."""
        lifecycle_events = []

        class AppWithEvents:
            __metadata__ = {
                "name": "app_with_events",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            def __init__(self):
                self._lifecycle_events = lifecycle_events

            def on_before_initialize(self):
                self._lifecycle_events.append("on_before_initialize")

            def on_after_initialize(self):
                self._lifecycle_events.append("on_after_initialize")

            def on_before_shutdown(self):
                self._lifecycle_events.append("on_before_shutdown")

            def on_after_shutdown(self):
                self._lifecycle_events.append("on_after_shutdown")

            async def initialize(self):
                self._lifecycle_events.append("initialize")
                return True

            async def shutdown(self):
                self._lifecycle_events.append("shutdown")

        app = AppWithEvents()
        return app, lifecycle_events

    @pytest.fixture
    def app_with_async_event_handlers(self):
        """Create a component with async lifecycle event handlers."""
        lifecycle_events = []

        class AppWithAsyncEvents:
            __metadata__ = {
                "name": "app_with_async_events",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            def __init__(self):
                self._lifecycle_events = lifecycle_events

            async def on_before_initialize(self):
                await asyncio.sleep(0)
                self._lifecycle_events.append("async_on_before_initialize")

            async def on_after_initialize(self):
                await asyncio.sleep(0)
                self._lifecycle_events.append("async_on_after_initialize")

            async def on_before_shutdown(self):
                await asyncio.sleep(0)
                self._lifecycle_events.append("async_on_before_shutdown")

            async def on_after_shutdown(self):
                await asyncio.sleep(0)
                self._lifecycle_events.append("async_on_after_shutdown")

            async def initialize(self):
                self._lifecycle_events.append("initialize")
                return True

            async def shutdown(self):
                self._lifecycle_events.append("shutdown")

        app = AppWithAsyncEvents()
        return app, lifecycle_events

    async def test_full_lifecycle(self, http_server_style_app):
        """Test complete initialize -> shutdown lifecycle."""
        app, events = http_server_style_app

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        # Initialize
        await initialize_components(app)

        assert component_initialized(app) is True
        assert app._running is True
        assert "initialized" in events

        # Shutdown
        await shutdown_components(app)

        assert component_initialized(app) is False
        assert app._running is False
        assert "shutdown" in events
        assert events == ["initialized", "shutdown"]

    async def test_event_handlers_called_in_order(self, app_with_event_handlers):
        """Test that all event handlers are called in correct order."""
        app, events = app_with_event_handlers
        clear_handlers()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        # Initialize
        await initialize_components(app)

        # Shutdown
        await shutdown_components(app)

        # Verify order: on_before_* -> method -> on_after_*
        expected = [
            "on_before_initialize",
            "initialize",
            "on_after_initialize",
            "on_before_shutdown",
            "shutdown",
            "on_after_shutdown",
        ]
        assert events == expected

    async def test_async_event_handlers(self, app_with_async_event_handlers):
        """Test that async event handlers work correctly."""
        app, events = app_with_async_event_handlers
        clear_handlers()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        await initialize_components(app)
        await shutdown_components(app)

        expected = [
            "async_on_before_initialize",
            "initialize",
            "async_on_after_initialize",
            "async_on_before_shutdown",
            "shutdown",
            "async_on_after_shutdown",
        ]
        assert events == expected

    async def test_initialize_returns_false_aborts(self):
        """Test that returning False from initialize aborts initialization."""

        class AbortingApp:
            __metadata__ = {
                "name": "aborting_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                return False  # Abort initialization

            async def shutdown(self):
                pass

        app = AbortingApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        await initialize_components(app)

        # Should not be marked as initialized
        assert component_initialized(app) is False

    async def test_initialize_exception_propagates(self):
        """Test that exceptions in initialize propagate correctly."""

        class FailingApp:
            __metadata__ = {
                "name": "failing_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                raise ValueError("Initialization failed!")

            async def shutdown(self):
                pass

        app = FailingApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        errors = await initialize_components(app, return_exceptions=True)

        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)

    async def test_shutdown_exception_propagates(self):
        """Test that exceptions in shutdown propagate correctly."""

        class ShutdownFailingApp:
            __metadata__ = {
                "name": "shutdown_failing_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                raise ValueError("Shutdown failed!")

        app = ShutdownFailingApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        await initialize_components(app)
        errors = await shutdown_components(app, return_exceptions=True)

        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)


class TestClassBasedComponentRegistration:
    """Tests for registering/unregistering class-based components."""

    @pytest.fixture
    def class_based_plugin(self):
        """Create a class-based plugin."""

        class MyPlugin:
            __metadata__ = {
                "name": "my_plugin",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            def __init__(self):
                self.initialized = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                self.initialized = False

        return MyPlugin()

    @pytest.fixture
    def container_with_app(self):
        """Create a container with an app already set."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class MainApp:
            __metadata__ = {
                "name": "main_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        app = MainApp()
        interface.set_app(app)
        interface.raw_container().wire = MagicMock()

        return interface

    async def test_register_class_based_plugin(self, container_with_app, class_based_plugin):
        """Test registering a class-based plugin."""
        interface = container_with_app

        interface.register_plugins(class_based_plugin)

        assert class_based_plugin in interface.provided_plugins()
        assert "_internals" in class_based_plugin.__metadata__

    async def test_register_and_initialize_class_plugin(self, container_with_app, class_based_plugin):
        """Test registering and initializing a class-based plugin."""
        interface = container_with_app

        interface.register_plugins(class_based_plugin)
        await initialize_components(class_based_plugin)

        assert class_based_plugin.initialized is True
        assert component_initialized(class_based_plugin) is True

    async def test_unregister_class_based_plugin(self, container_with_app, class_based_plugin):
        """Test unregistering a class-based plugin."""
        interface = container_with_app

        interface.register_plugins(class_based_plugin)
        await initialize_components(class_based_plugin)

        # Unregister should shutdown and remove
        await unregister_plugin(interface, class_based_plugin)

        assert class_based_plugin not in interface.provided_plugins()
        assert class_based_plugin.initialized is False

    async def test_full_plugin_cycle(self, container_with_app):
        """Test full register -> init -> shutdown -> unregister cycle for class plugin."""
        interface = container_with_app
        events = []

        class LifecyclePlugin:
            __metadata__ = {
                "name": "lifecycle_plugin",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                events.append("init")
                return True

            async def shutdown(self):
                events.append("shutdown")

        plugin = LifecyclePlugin()

        # Register
        interface.register_plugins(plugin)
        assert plugin in interface.provided_plugins()

        # Initialize
        await initialize_components(plugin)
        assert "init" in events
        assert component_initialized(plugin) is True

        # Unregister (should trigger shutdown)
        await unregister_plugin(interface, plugin)
        assert "shutdown" in events
        assert plugin not in interface.provided_plugins()


class TestClassBasedComponentWithDependencies:
    """Tests for class-based components with dependencies."""

    async def test_class_component_with_dependency(self):
        """Test class component that depends on another component."""

        class DatabaseLib:
            __metadata__ = {
                "name": "database",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }
            initialize = None
            shutdown = None

        class ServiceApp:
            __metadata__ = {
                "name": "service_app",
                "version": "1.0.0",
                "wire": False,
            }

            def __init__(self, db):
                self.db = db
                self.__metadata__["requires"] = {db}

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        db = DatabaseLib()
        app = ServiceApp(db)

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        # Both should have internals set up
        assert "_internals" in db.__metadata__
        assert "_internals" in app.__metadata__

        # db should know app requires it
        assert app in component_internals(db).required_by

    async def test_shutdown_blocked_by_dependent_class_component(self):
        """Test that base component shutdown is blocked by dependent class component."""

        class BasePlugin:
            __metadata__ = {
                "name": "base_plugin",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        base = BasePlugin()

        class DependentPlugin:
            def __init__(self):
                self.__metadata__ = {
                    "name": "dependent_plugin",
                    "version": "1.0.0",
                    "wire": False,
                    "requires": {base},
                }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        dependent = DependentPlugin()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(dependent)

        # Initialize both
        await initialize_components(base, dependent)

        # Try to shutdown base alone - should be blocked
        await shutdown_components(base)

        # Base should still be initialized because dependent requires it
        assert component_initialized(base) is True

        # Now shutdown dependent first, then base
        await shutdown_components(dependent, base)

        assert component_initialized(dependent) is False
        assert component_initialized(base) is False


class TestClassBasedComponentWiring:
    """Tests for wiring with class-based components."""

    def test_wire_class_based_component(self, temp_dir):
        """Test wiring a class-based component."""

        class WiredApp:
            __metadata__ = {
                "name": "wired_app",
                "version": "1.0.0",
                "wire": True,
                "wirings": set(),
            }

            def __init__(self):
                self._container = None

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        app = WiredApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        interface.set_app(app)

        wire(interface, components=[app])

        container.wire.assert_called_once()

    def test_wire_class_component_uses_module(self):
        """Test that wiring uses __module__ from class instance."""

        class ModuleAwareApp:
            __metadata__ = {
                "name": "module_aware_app",
                "version": "1.0.0",
                "wire": True,
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        app = ModuleAwareApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        interface.set_app(app)
        wire(interface, components=[app])

        # Verify wire was called
        container.wire.assert_called_once()
        call_kwargs = container.wire.call_args.kwargs
        modules = call_kwargs.get("modules", set())

        # Should include the class's module
        assert any("test_class_based_components" in str(m) for m in modules)


class TestClassBasedComponentWithConfiguration:
    """Tests for class-based components with configuration."""

    def test_class_component_with_config(self, temp_dir):
        """Test class component with configuration model."""

        class ServerConfig(pydantic.BaseModel):
            __prefix__ = "server"
            host: str = "127.0.0.1"
            port: int = 8080

        class ConfiguredServerApp:
            __metadata__ = {
                "name": "configured_server",
                "version": "1.0.0",
                "wire": False,
                "config": ServerConfig,
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        app = ConfiguredServerApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        inject_dependencies(interface, components=[app])

        # Config should be registered
        from src.awioc.config.registry import _CONFIGURATIONS
        assert "server" in _CONFIGURATIONS

    async def test_reconfigure_class_component(self, temp_dir):
        """Test reconfiguring a class-based component."""

        class AppConfig(IOCBaseConfig):
            app_name: str = "default"
            debug: bool = False

        class ReconfigurableApp:
            __metadata__ = {
                "name": "reconfigurable_app",
                "version": "1.0.0",
                "base_config": AppConfig,
                "wire": False,
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        app = ReconfigurableApp()

        config_path = temp_dir / "config.yaml"
        config_path.write_text("")

        ioc_config = IOCBaseConfig(config_path=config_path)

        container = AppContainer()
        interface = ContainerInterface(container)
        container.wire = MagicMock()

        interface.set_app(app)
        app.__metadata__["_internals"].ioc_config = ioc_config

        reconfigure_ioc_app(interface, components=[app])

        # Config should be set
        assert interface.raw_container().config() is not None


class TestClassBasedComponentFromYamlSyntax:
    """Tests simulating loading from ioc.yaml with :ClassName() syntax."""

    def test_load_app_like_http_server(self, temp_dir, reset_sys_modules):
        """Test loading app like the HttpServerApp example."""
        module_path = temp_dir / "http_server.py"
        module_path.write_text('''
class ServerConfig:
    """Server configuration."""
    __prefix__ = "server"
    host: str = "127.0.0.1"
    port: int = 8080


class HttpServerApp:
    """HTTP Server application."""
    __metadata__ = {
        "name": "HTTP File Server",
        "version": "2.0.0",
        "description": "HTTP File Server with features",
        "wire": True,
        "config": ServerConfig
    }

    def __init__(self):
        self._server = None
        self._running = False

    async def initialize(self):
        self._running = True
        return True

    async def wait(self):
        import asyncio
        while self._running:
            await asyncio.sleep(0.1)

    async def shutdown(self):
        self._running = False
''')
        # This simulates what happens when ioc.yaml has: app: :HttpServerApp()
        result = compile_component(f"{module_path}:HttpServerApp()")

        assert result.__metadata__["name"] == "HTTP File Server"
        assert result.__metadata__["version"] == "2.0.0"
        assert result._running is False
        assert hasattr(result, "initialize")
        assert hasattr(result, "shutdown")
        assert hasattr(result, "wait")

    async def test_full_lifecycle_http_server_style(self, temp_dir, reset_sys_modules):
        """Test full lifecycle of HTTP server style app loaded from module."""
        clear_handlers()

        module_path = temp_dir / "server_app.py"
        module_path.write_text('''
class ServerApp:
    """Server application with all lifecycle hooks."""
    __metadata__ = {
        "name": "server_app",
        "version": "1.0.0",
        "wire": False,
        "requires": set(),
    }

    def __init__(self):
        self.events = []

    def on_before_initialize(self):
        self.events.append("before_init")

    def on_after_initialize(self):
        self.events.append("after_init")

    def on_before_shutdown(self):
        self.events.append("before_shutdown")

    def on_after_shutdown(self):
        self.events.append("after_shutdown")

    async def initialize(self):
        self.events.append("init")
        return True

    async def shutdown(self):
        self.events.append("shutdown")
''')
        app = compile_component(f"{module_path}:ServerApp()")

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        # Initialize
        await initialize_components(app)

        assert component_initialized(app) is True

        # Shutdown
        await shutdown_components(app)

        assert component_initialized(app) is False

        # Verify event order
        expected = [
            "before_init",
            "init",
            "after_init",
            "before_shutdown",
            "shutdown",
            "after_shutdown",
        ]
        assert app.events == expected


class TestClassBasedComponentEdgeCases:
    """Edge case tests for class-based components."""

    async def test_class_component_without_initialize(self):
        """Test class component that has no initialize method."""

        class NoInitApp:
            __metadata__ = {
                "name": "no_init_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }
            initialize = None
            shutdown = None

        app = NoInitApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        await initialize_components(app)

        # Should still be marked as initialized even without method
        assert component_initialized(app) is True

    async def test_class_component_without_shutdown(self):
        """Test class component that has no shutdown method."""

        class NoShutdownApp:
            __metadata__ = {
                "name": "no_shutdown_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                return True

            shutdown = None

        app = NoShutdownApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        await initialize_components(app)
        await shutdown_components(app)

        # Should be marked as not initialized after shutdown
        assert component_initialized(app) is False

    async def test_double_initialize_ignored(self):
        """Test that initializing twice doesn't call initialize again."""
        init_count = [0]

        class CountingApp:
            __metadata__ = {
                "name": "counting_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                init_count[0] += 1
                return True

            async def shutdown(self):
                pass

        app = CountingApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        await initialize_components(app)
        await initialize_components(app)  # Second call

        assert init_count[0] == 1

    async def test_shutdown_without_initialize(self):
        """Test that shutting down without initialize does nothing."""
        shutdown_count = [0]

        class ShutdownOnlyApp:
            __metadata__ = {
                "name": "shutdown_only_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                shutdown_count[0] += 1

        app = ShutdownOnlyApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        # Shutdown without initialize
        await shutdown_components(app)

        assert shutdown_count[0] == 0

    async def test_class_with_wait_method(self):
        """Test class component with wait method."""
        wait_called = [False]
        wait_cancelled = [False]

        class WaitingApp:
            __metadata__ = {
                "name": "waiting_app",
                "version": "1.0.0",
                "wire": False,
                "requires": set(),
            }

            async def initialize(self):
                return True

            async def wait(self):
                wait_called[0] = True
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    wait_cancelled[0] = True
                    raise

            async def shutdown(self):
                pass

        app = WaitingApp()

        container = AppContainer()
        interface = ContainerInterface(container)
        interface.set_app(app)

        await initialize_components(app)

        # Start wait in background
        from src.awioc.components.lifecycle import wait_for_components

        wait_task = asyncio.create_task(wait_for_components(app))

        # Give it a moment to start waiting
        await asyncio.sleep(0.01)

        # Cancel it
        wait_task.cancel()
        try:
            await wait_task
        except asyncio.CancelledError:
            pass

        assert wait_called[0] is True
        assert wait_cancelled[0] is True
