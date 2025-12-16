import pytest
import asyncio
import logging

from src.ioc.components.lifecycle import (
    initialize_components,
    shutdown_components,
)
from src.ioc.components.metadata import Internals


class TestInitializeComponents:
    """Tests for initialize_components function."""

    @pytest.fixture
    def simple_component(self):
        """Create a simple component for testing."""
        class SimpleComponent:
            __metadata__ = {
                "name": "simple",
                "version": "1.0.0",
                "description": "Simple test component",
                "requires": set(),
                "_internals": Internals()
            }
            initialized = False

            async def initialize(self):
                self.initialized = True
                return True

            async def shutdown(self):
                self.initialized = False

        return SimpleComponent()

    @pytest.fixture
    def component_without_init(self):
        """Create a component without initialize method."""
        class NoInit:
            __metadata__ = {
                "name": "no_init",
                "version": "1.0.0",
                "description": "",
                "requires": set(),
                "_internals": Internals()
            }
            initialize = None
            shutdown = None

        return NoInit()

    @pytest.mark.asyncio
    async def test_initialize_single_component(self, simple_component):
        """Test initializing a single component."""
        result = await initialize_components(simple_component)

        assert simple_component.initialized is True
        assert simple_component.__metadata__["_internals"].is_initialized is True

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self, simple_component):
        """Test initializing an already initialized component."""
        simple_component.__metadata__["_internals"].is_initialized = True

        result = await initialize_components(simple_component)

        # Should not run initialize again
        assert simple_component.initialized is False  # Wasn't called

    @pytest.mark.asyncio
    async def test_initialize_component_being_initialized(self, simple_component):
        """Test component that is currently initializing."""
        simple_component.__metadata__["_internals"].is_initializing = True

        result = await initialize_components(simple_component)

        # Should skip
        assert simple_component.initialized is False

    @pytest.mark.asyncio
    async def test_initialize_without_init_method(self, component_without_init):
        """Test initializing component without initialize method."""
        result = await initialize_components(component_without_init)

        assert component_without_init.__metadata__["_internals"].is_initialized is True

    @pytest.mark.asyncio
    async def test_initialize_returns_components(self, simple_component):
        """Test that initialize_components returns the components."""
        result = await initialize_components(simple_component)

        assert simple_component in result

    @pytest.mark.asyncio
    async def test_initialize_with_dependency(self):
        """Test initializing component with uninitialized dependency."""
        dep = type("Dep", (), {
            "__metadata__": {
                "name": "dep",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(is_initialized=False)
            },
            "initialize": None,
            "shutdown": None
        })()

        comp = type("Comp", (), {
            "__metadata__": {
                "name": "comp",
                "version": "1.0.0",
                "requires": {dep},
                "_internals": Internals()
            },
            "initialize": None,
            "shutdown": None
        })()

        # Dependency not initialized, so comp shouldn't initialize
        result = await initialize_components(comp)

        # Should not be initialized because dep is not initialized
        assert comp.__metadata__["_internals"].is_initialized is False

    @pytest.mark.asyncio
    async def test_initialize_aborted(self):
        """Test component that aborts initialization."""
        class AbortingComponent:
            __metadata__ = {
                "name": "aborting",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def initialize(self):
                return False  # Abort

            shutdown = None

        comp = AbortingComponent()
        result = await initialize_components(comp)

        assert comp.__metadata__["_internals"].is_initialized is False

    @pytest.mark.asyncio
    async def test_initialize_with_exception(self):
        """Test component that raises exception during initialization."""
        class FailingComponent:
            __metadata__ = {
                "name": "failing",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def initialize(self):
                raise ValueError("Init failed")

            shutdown = None

        comp = FailingComponent()

        with pytest.raises((ExceptionGroup, ValueError)):
            await initialize_components(comp)

    @pytest.mark.asyncio
    async def test_initialize_return_exceptions(self):
        """Test return_exceptions parameter."""
        class FailingComponent:
            __metadata__ = {
                "name": "failing",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def initialize(self):
                raise ValueError("Init failed")

            shutdown = None

        comp = FailingComponent()
        result = await initialize_components(
            comp,
            return_exceptions=True
        )

        assert len(result) == 1
        assert isinstance(result[0], ValueError)


class TestShutdownComponents:
    """Tests for shutdown_components function."""

    @pytest.fixture
    def initialized_component(self):
        """Create an initialized component for testing."""
        class InitializedComponent:
            __metadata__ = {
                "name": "initialized",
                "version": "1.0.0",
                "description": "",
                "requires": set(),
                "_internals": Internals(is_initialized=True)
            }
            shutdown_called = False

            async def initialize(self):
                return True

            async def shutdown(self):
                self.shutdown_called = True

        return InitializedComponent()

    @pytest.mark.asyncio
    async def test_shutdown_single_component(self, initialized_component):
        """Test shutting down a single component."""
        result = await shutdown_components(initialized_component)

        assert initialized_component.shutdown_called is True
        assert initialized_component.__metadata__["_internals"].is_initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_not_initialized(self):
        """Test shutting down a non-initialized component."""
        class NotInit:
            __metadata__ = {
                "name": "not_init",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(is_initialized=False)
            }
            shutdown_called = False

            async def shutdown(self):
                self.shutdown_called = True

        comp = NotInit()
        result = await shutdown_components(comp)

        assert comp.shutdown_called is False

    @pytest.mark.asyncio
    async def test_shutdown_without_method(self):
        """Test shutting down component without shutdown method."""
        class NoShutdown:
            __metadata__ = {
                "name": "no_shutdown",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(is_initialized=True)
            }
            initialize = None
            shutdown = None

        comp = NoShutdown()
        result = await shutdown_components(comp)

        assert comp.__metadata__["_internals"].is_initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_still_required(self):
        """Test component that is still required by others."""
        requirer = type("Requirer", (), {
            "__metadata__": {
                "name": "requirer",
                "_internals": Internals(is_initialized=True)
            }
        })()

        comp = type("Comp", (), {
            "__metadata__": {
                "name": "comp",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(
                    is_initialized=True,
                    required_by={requirer}
                )
            },
            "shutdown": None
        })()

        result = await shutdown_components(comp)

        # Should not shutdown because still required
        assert comp.__metadata__["_internals"].is_initialized is True

    @pytest.mark.asyncio
    async def test_shutdown_with_exception(self):
        """Test component that raises exception during shutdown."""
        class FailingShutdown:
            __metadata__ = {
                "name": "failing",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(is_initialized=True)
            }

            async def shutdown(self):
                raise ValueError("Shutdown failed")

        comp = FailingShutdown()

        with pytest.raises((ExceptionGroup, ValueError)):
            await shutdown_components(comp)

    @pytest.mark.asyncio
    async def test_shutdown_return_exceptions(self):
        """Test return_exceptions parameter for shutdown."""
        class FailingShutdown:
            __metadata__ = {
                "name": "failing",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals(is_initialized=True)
            }

            async def shutdown(self):
                raise ValueError("Shutdown failed")

        comp = FailingShutdown()
        result = await shutdown_components(
            comp,
            return_exceptions=True
        )

        assert len(result) == 1
        assert isinstance(result[0], ValueError)

    @pytest.mark.asyncio
    async def test_shutdown_returns_components(self, initialized_component):
        """Test that shutdown_components returns the components."""
        result = await shutdown_components(initialized_component)

        assert initialized_component in result
