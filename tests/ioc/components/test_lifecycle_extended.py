import pytest
import logging

from src.ioc.components.lifecycle import (
    register_plugin,
    unregister_plugin,
)
from src.ioc.components.metadata import Internals
from src.ioc.container import AppContainer, ContainerInterface


class TestRegisterPlugin:
    """Tests for register_plugin function."""

    def test_register_plugin_function_exists(self):
        """Test that register_plugin function exists."""
        assert callable(register_plugin)


class TestUnregisterPlugin:
    """Tests for unregister_plugin function."""

    @pytest.fixture
    def container_interface(self):
        """Create a container interface for testing."""
        container = AppContainer()
        interface = ContainerInterface(container)
        interface.raw_container().wire = lambda *args, **kwargs: None
        return interface

    @pytest.fixture
    def mock_plugin(self):
        """Create a mock plugin."""
        class MockPlugin:
            __name__ = "mock_plugin"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "mock_plugin",
                "version": "1.0.0",
                "description": "Mock plugin",
                "requires": set(),
                "wire": False
            }
            initialize = None
            shutdown = None

        return MockPlugin()

    @pytest.mark.asyncio
    async def test_unregister_not_registered(self, container_interface, mock_plugin):
        """Test unregistering a plugin that's not registered."""
        class MockApp:
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "requires": set()
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        container_interface.set_app(MockApp())
        mock_plugin.__metadata__["_internals"] = Internals()

        # Should not raise, just log warning
        await unregister_plugin(
            container_interface,
            mock_plugin
        )

    @pytest.mark.asyncio
    async def test_unregister_still_required(self, container_interface):
        """Test unregistering a plugin that's still required."""
        class MockApp:
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "requires": set()
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        container_interface.set_app(MockApp())

        # Create a plugin with a requirer
        class Requirer:
            __metadata__ = {
                "name": "requirer",
                "_internals": Internals(is_initialized=True)
            }

        class RequiredPlugin:
            __name__ = "required_plugin"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "required_plugin",
                "version": "1.0.0",
                "description": "Required plugin",
                "requires": set(),
                "wire": False,
                "_internals": Internals(required_by={Requirer()})
            }
            initialize = None
            shutdown = None

        plugin = RequiredPlugin()

        # Register the plugin
        container_interface._plugins_map["required_plugin"] = lambda: plugin

        with pytest.raises(RuntimeError, match="still required"):
            await unregister_plugin(
                container_interface,
                plugin
            )


class TestInitializeComponentsExtended:
    """Extended tests for initialize_components."""

    @pytest.mark.asyncio
    async def test_initialize_multiple_components(self):
        """Test initializing multiple components."""
        from src.ioc.components.lifecycle import initialize_components

        class Comp1:
            __metadata__ = {
                "name": "comp1",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }
            initialized = False

            async def initialize(self):
                self.initialized = True

            shutdown = None

        class Comp2:
            __metadata__ = {
                "name": "comp2",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }
            initialized = False

            async def initialize(self):
                self.initialized = True

            shutdown = None

        comp1 = Comp1()
        comp2 = Comp2()

        result = await initialize_components(comp1, comp2)

        assert comp1.initialized
        assert comp2.initialized


class TestShutdownComponentsExtended:
    """Extended tests for shutdown_components."""

    @pytest.mark.asyncio
    async def test_shutdown_multiple_components(self):
        """Test shutting down multiple components."""
        from src.ioc.components.lifecycle import shutdown_components

        class Comp1:
            __metadata__ = {
                "name": "comp1",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(is_initialized=True)
            }
            shutdown_called = False

            async def shutdown(self):
                self.shutdown_called = True

        class Comp2:
            __metadata__ = {
                "name": "comp2",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(is_initialized=True)
            }
            shutdown_called = False

            async def shutdown(self):
                self.shutdown_called = True

        comp1 = Comp1()
        comp2 = Comp2()

        result = await shutdown_components(comp1, comp2)

        assert comp1.shutdown_called
        assert comp2.shutdown_called
