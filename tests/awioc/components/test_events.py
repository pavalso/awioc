import asyncio

import pytest

from src.awioc.components.events import (
    ComponentEvent,
    on_event,
    emit,
    clear_handlers,
    _handlers,
)
from src.awioc.components.lifecycle import (
    initialize_components,
    shutdown_components,
)
from src.awioc.components.metadata import Internals


class TestComponentEvent:
    """Tests for ComponentEvent enum."""

    def test_all_events_defined(self):
        """Test all expected events are defined."""
        assert ComponentEvent.BEFORE_INITIALIZE.value == "before_initialize"
        assert ComponentEvent.AFTER_INITIALIZE.value == "after_initialize"
        assert ComponentEvent.BEFORE_SHUTDOWN.value == "before_shutdown"
        assert ComponentEvent.AFTER_SHUTDOWN.value == "after_shutdown"

    def test_event_count(self):
        """Test correct number of events."""
        assert len(ComponentEvent) == 4


class TestOnEvent:
    """Tests for on_event function."""

    @pytest.fixture(autouse=True)
    def clear_all_handlers(self):
        """Clear handlers before and after each test."""
        clear_handlers()
        yield
        clear_handlers()

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

    def test_decorator_registers_handler(self):
        """Test that decorator registers handler."""

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def my_handler(component):
            pass

        assert ComponentEvent.AFTER_INITIALIZE in _handlers
        assert len(_handlers[ComponentEvent.AFTER_INITIALIZE]) == 1

    def test_decorator_returns_original_function(self):
        """Test that decorator returns the original function."""

        def my_handler(component):
            pass

        result = on_event(ComponentEvent.AFTER_INITIALIZE)(my_handler)
        assert result is my_handler

    def test_direct_call_registers_handler(self):
        """Test direct call with handler argument."""

        def my_handler(component):
            pass

        on_event(ComponentEvent.BEFORE_SHUTDOWN, handler=my_handler)

        assert ComponentEvent.BEFORE_SHUTDOWN in _handlers
        assert len(_handlers[ComponentEvent.BEFORE_SHUTDOWN]) == 1

    def test_multiple_handlers_same_event(self):
        """Test registering multiple handlers for same event."""

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def handler1(component):
            pass

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def handler2(component):
            pass

        assert len(_handlers[ComponentEvent.AFTER_INITIALIZE]) == 2

    def test_handlers_different_events(self):
        """Test registering handlers for different events."""

        @on_event(ComponentEvent.BEFORE_INITIALIZE)
        def handler1(component):
            pass

        @on_event(ComponentEvent.AFTER_SHUTDOWN)
        def handler2(component):
            pass

        assert len(_handlers[ComponentEvent.BEFORE_INITIALIZE]) == 1
        assert len(_handlers[ComponentEvent.AFTER_SHUTDOWN]) == 1

    def test_check_function_stored(self):
        """Test that check function is stored with handler."""

        def my_check(c):
            return True

        @on_event(ComponentEvent.AFTER_INITIALIZE, check=my_check)
        def my_handler(component):
            pass

        registered = _handlers[ComponentEvent.AFTER_INITIALIZE][0]
        assert registered.check is my_check


class TestEmit:
    """Tests for emit function."""

    @pytest.fixture(autouse=True)
    def clear_all_handlers(self):
        """Clear handlers before and after each test."""
        clear_handlers()
        yield
        clear_handlers()

    @pytest.fixture
    def simple_component(self):
        """Create a simple component for testing."""

        class SimpleComponent:
            __metadata__ = {
                "name": "test_component",
                "version": "1.0.0",
                "description": "Test component",
                "requires": set(),
                "_internals": Internals()
            }

        return SimpleComponent()

    @pytest.mark.asyncio
    async def test_emit_calls_sync_handler(self, simple_component):
        """Test emit calls synchronous handler."""
        called = []

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def my_handler(component):
            called.append(component)

        await emit(simple_component, ComponentEvent.AFTER_INITIALIZE)

        assert len(called) == 1
        assert called[0] is simple_component

    @pytest.mark.asyncio
    async def test_emit_calls_async_handler(self, simple_component):
        """Test emit calls asynchronous handler."""
        called = []

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        async def my_handler(component):
            await asyncio.sleep(0)
            called.append(component)

        await emit(simple_component, ComponentEvent.AFTER_INITIALIZE)

        assert len(called) == 1
        assert called[0] is simple_component

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self, simple_component):
        """Test emit with no registered handlers."""
        # Should not raise
        await emit(simple_component, ComponentEvent.AFTER_INITIALIZE)

    @pytest.mark.asyncio
    async def test_emit_multiple_handlers_order(self, simple_component):
        """Test handlers are called in registration order."""
        order = []

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def handler1(component):
            order.append(1)

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def handler2(component):
            order.append(2)

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def handler3(component):
            order.append(3)

        await emit(simple_component, ComponentEvent.AFTER_INITIALIZE)

        assert order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_emit_handler_exception_propagates(self, simple_component):
        """Test that handler exceptions propagate."""

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def failing_handler(component):
            raise ValueError("Handler failed")

        with pytest.raises(ValueError, match="Handler failed"):
            await emit(simple_component, ComponentEvent.AFTER_INITIALIZE)

    @pytest.mark.asyncio
    async def test_emit_async_handler_exception_propagates(self, simple_component):
        """Test that async handler exceptions propagate."""

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        async def failing_handler(component):
            raise ValueError("Async handler failed")

        with pytest.raises(ValueError, match="Async handler failed"):
            await emit(simple_component, ComponentEvent.AFTER_INITIALIZE)


class TestCheckFunction:
    """Tests for check function filtering."""

    @pytest.fixture(autouse=True)
    def clear_all_handlers(self):
        """Clear handlers before and after each test."""
        clear_handlers()
        yield
        clear_handlers()

    @pytest.fixture
    def component_a(self):
        """Create component A."""

        class ComponentA:
            __metadata__ = {
                "name": "component_a",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

        return ComponentA()

    @pytest.fixture
    def component_b(self):
        """Create component B."""

        class ComponentB:
            __metadata__ = {
                "name": "component_b",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

        return ComponentB()

    @pytest.mark.asyncio
    async def test_check_true_calls_handler(self, component_a):
        """Test handler is called when check returns True."""
        called = []

        @on_event(ComponentEvent.AFTER_INITIALIZE, check=lambda c: True)
        def my_handler(component):
            called.append(component)

        await emit(component_a, ComponentEvent.AFTER_INITIALIZE)

        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_check_false_skips_handler(self, component_a):
        """Test handler is skipped when check returns False."""
        called = []

        @on_event(ComponentEvent.AFTER_INITIALIZE, check=lambda c: False)
        def my_handler(component):
            called.append(component)

        await emit(component_a, ComponentEvent.AFTER_INITIALIZE)

        assert len(called) == 0

    @pytest.mark.asyncio
    async def test_check_filters_by_name(self, component_a, component_b):
        """Test check function can filter by component name."""
        called = []

        @on_event(
            ComponentEvent.AFTER_INITIALIZE,
            check=lambda c: c.__metadata__["name"] == "component_a"
        )
        def my_handler(component):
            called.append(component.__metadata__["name"])

        await emit(component_a, ComponentEvent.AFTER_INITIALIZE)
        await emit(component_b, ComponentEvent.AFTER_INITIALIZE)

        assert called == ["component_a"]

    @pytest.mark.asyncio
    async def test_no_check_calls_for_all(self, component_a, component_b):
        """Test handler without check is called for all components."""
        called = []

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def my_handler(component):
            called.append(component.__metadata__["name"])

        await emit(component_a, ComponentEvent.AFTER_INITIALIZE)
        await emit(component_b, ComponentEvent.AFTER_INITIALIZE)

        assert "component_a" in called
        assert "component_b" in called

    @pytest.mark.asyncio
    async def test_mixed_handlers_with_and_without_check(self, component_a, component_b):
        """Test mixing handlers with and without check functions."""
        all_calls = []
        filtered_calls = []

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def all_handler(component):
            all_calls.append(component.__metadata__["name"])

        @on_event(
            ComponentEvent.AFTER_INITIALIZE,
            check=lambda c: c.__metadata__["name"] == "component_b"
        )
        def filtered_handler(component):
            filtered_calls.append(component.__metadata__["name"])

        await emit(component_a, ComponentEvent.AFTER_INITIALIZE)
        await emit(component_b, ComponentEvent.AFTER_INITIALIZE)

        assert all_calls == ["component_a", "component_b"]
        assert filtered_calls == ["component_b"]


class TestClearHandlers:
    """Tests for clear_handlers function."""

    @pytest.fixture(autouse=True)
    def clear_all_handlers(self):
        """Clear handlers before and after each test."""
        clear_handlers()
        yield
        clear_handlers()

    def test_clear_all_handlers(self):
        """Test clearing all handlers."""

        @on_event(ComponentEvent.BEFORE_INITIALIZE)
        def handler1(c):
            pass

        @on_event(ComponentEvent.AFTER_SHUTDOWN)
        def handler2(c):
            pass

        clear_handlers()

        assert len(_handlers) == 0

    def test_clear_specific_event(self):
        """Test clearing handlers for specific event."""

        @on_event(ComponentEvent.BEFORE_INITIALIZE)
        def handler1(c):
            pass

        @on_event(ComponentEvent.AFTER_SHUTDOWN)
        def handler2(c):
            pass

        clear_handlers(ComponentEvent.BEFORE_INITIALIZE)

        assert ComponentEvent.BEFORE_INITIALIZE not in _handlers
        assert ComponentEvent.AFTER_SHUTDOWN in _handlers

    def test_clear_nonexistent_event(self):
        """Test clearing event with no handlers doesn't raise."""
        clear_handlers(ComponentEvent.BEFORE_SHUTDOWN)
        # Should not raise


class TestLifecycleIntegration:
    """Tests for event integration with component lifecycle."""

    @pytest.fixture(autouse=True)
    def clear_all_handlers(self):
        """Clear handlers before and after each test."""
        clear_handlers()
        yield
        clear_handlers()

    @pytest.fixture
    def simple_component(self):
        """Create a simple component for testing."""

        class SimpleComponent:
            __metadata__ = {
                "name": "lifecycle_test",
                "version": "1.0.0",
                "description": "Lifecycle test component",
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

    @pytest.mark.asyncio
    async def test_before_initialize_event(self, simple_component):
        """Test BEFORE_INITIALIZE event fires before component initializes."""
        events = []

        @on_event(ComponentEvent.BEFORE_INITIALIZE)
        def handler(component):
            events.append(("before", component.__metadata__["_internals"].is_initialized))

        await initialize_components(simple_component)

        assert events == [("before", False)]

    @pytest.mark.asyncio
    async def test_after_initialize_event(self, simple_component):
        """Test AFTER_INITIALIZE event fires after component initializes."""
        events = []

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def handler(component):
            events.append(("after", component.__metadata__["_internals"].is_initialized))

        await initialize_components(simple_component)

        assert events == [("after", True)]

    @pytest.mark.asyncio
    async def test_before_shutdown_event(self, simple_component):
        """Test BEFORE_SHUTDOWN event fires before component shuts down."""
        await initialize_components(simple_component)

        events = []

        @on_event(ComponentEvent.BEFORE_SHUTDOWN)
        def handler(component):
            events.append(("before", component.__metadata__["_internals"].is_initialized))

        await shutdown_components(simple_component)

        assert events == [("before", True)]

    @pytest.mark.asyncio
    async def test_after_shutdown_event(self, simple_component):
        """Test AFTER_SHUTDOWN event fires after component shuts down."""
        await initialize_components(simple_component)

        events = []

        @on_event(ComponentEvent.AFTER_SHUTDOWN)
        def handler(component):
            events.append(("after", component.__metadata__["_internals"].is_initialized))

        await shutdown_components(simple_component)

        assert events == [("after", False)]

    @pytest.mark.asyncio
    async def test_full_lifecycle_events_order(self, simple_component):
        """Test full lifecycle events fire in correct order."""
        events = []

        @on_event(ComponentEvent.BEFORE_INITIALIZE)
        def before_init(c):
            events.append("before_init")

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def after_init(c):
            events.append("after_init")

        @on_event(ComponentEvent.BEFORE_SHUTDOWN)
        def before_shutdown(c):
            events.append("before_shutdown")

        @on_event(ComponentEvent.AFTER_SHUTDOWN)
        def after_shutdown(c):
            events.append("after_shutdown")

        await initialize_components(simple_component)
        await shutdown_components(simple_component)

        assert events == [
            "before_init",
            "after_init",
            "before_shutdown",
            "after_shutdown"
        ]

    @pytest.mark.asyncio
    async def test_event_with_check_in_lifecycle(self):
        """Test check function works during lifecycle."""

        class ComponentA:
            __metadata__ = {
                "name": "comp_a",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }
            initialize = None
            shutdown = None

        class ComponentB:
            __metadata__ = {
                "name": "comp_b",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }
            initialize = None
            shutdown = None

        comp_a = ComponentA()
        comp_b = ComponentB()

        called_for = []

        @on_event(
            ComponentEvent.AFTER_INITIALIZE,
            check=lambda c: c.__metadata__["name"] == "comp_a"
        )
        def only_a_handler(component):
            called_for.append(component.__metadata__["name"])

        await initialize_components(comp_a)
        await initialize_components(comp_b)

        assert called_for == ["comp_a"]

    @pytest.mark.asyncio
    async def test_async_handler_in_lifecycle(self, simple_component):
        """Test async handlers work in lifecycle."""
        results = []

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        async def async_handler(component):
            await asyncio.sleep(0.01)
            results.append("async_done")

        await initialize_components(simple_component)

        assert results == ["async_done"]


class TestComponentSpecificEventHandlers:
    """Tests for component-specific event handlers (on_before_initialize, etc.)."""

    @pytest.fixture(autouse=True)
    def clear_all_handlers(self):
        """Clear handlers before and after each test."""
        clear_handlers()
        yield
        clear_handlers()

    @pytest.mark.asyncio
    async def test_on_before_initialize_called(self):
        """Test on_before_initialize attribute is called before initialize."""
        events = []

        class ComponentWithHandler:
            __metadata__ = {
                "name": "handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            def on_before_initialize(self):
                events.append("on_before_initialize")

            async def initialize(self):
                events.append("initialize")

            shutdown = None

        comp = ComponentWithHandler()
        await initialize_components(comp)

        assert events == ["on_before_initialize", "initialize"]

    @pytest.mark.asyncio
    async def test_on_after_initialize_called(self):
        """Test on_after_initialize attribute is called after initialize."""
        events = []

        class ComponentWithHandler:
            __metadata__ = {
                "name": "handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def initialize(self):
                events.append("initialize")

            def on_after_initialize(self):
                events.append("on_after_initialize")

            shutdown = None

        comp = ComponentWithHandler()
        await initialize_components(comp)

        assert events == ["initialize", "on_after_initialize"]

    @pytest.mark.asyncio
    async def test_on_before_shutdown_called(self):
        """Test on_before_shutdown attribute is called before shutdown."""
        events = []

        class ComponentWithHandler:
            __metadata__ = {
                "name": "handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def initialize(self):
                pass

            def on_before_shutdown(self):
                events.append("on_before_shutdown")

            async def shutdown(self):
                events.append("shutdown")

        comp = ComponentWithHandler()
        await initialize_components(comp)
        await shutdown_components(comp)

        assert events == ["on_before_shutdown", "shutdown"]

    @pytest.mark.asyncio
    async def test_on_after_shutdown_called(self):
        """Test on_after_shutdown attribute is called after shutdown."""
        events = []

        class ComponentWithHandler:
            __metadata__ = {
                "name": "handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                events.append("shutdown")

            def on_after_shutdown(self):
                events.append("on_after_shutdown")

        comp = ComponentWithHandler()
        await initialize_components(comp)
        await shutdown_components(comp)

        assert events == ["shutdown", "on_after_shutdown"]

    @pytest.mark.asyncio
    async def test_async_component_handlers(self):
        """Test async component-specific handlers work."""
        events = []

        class ComponentWithAsyncHandlers:
            __metadata__ = {
                "name": "async_handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def on_before_initialize(self):
                await asyncio.sleep(0.01)
                events.append("async_on_before_initialize")

            async def initialize(self):
                events.append("initialize")

            shutdown = None

        comp = ComponentWithAsyncHandlers()
        await initialize_components(comp)

        assert events == ["async_on_before_initialize", "initialize"]

    @pytest.mark.asyncio
    async def test_all_component_handlers_full_lifecycle(self):
        """Test all component-specific handlers in a full lifecycle."""
        events = []

        class ComponentWithAllHandlers:
            __metadata__ = {
                "name": "full_handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            def on_before_initialize(self):
                events.append("on_before_initialize")

            async def initialize(self):
                events.append("initialize")

            def on_after_initialize(self):
                events.append("on_after_initialize")

            def on_before_shutdown(self):
                events.append("on_before_shutdown")

            async def shutdown(self):
                events.append("shutdown")

            def on_after_shutdown(self):
                events.append("on_after_shutdown")

        comp = ComponentWithAllHandlers()
        await initialize_components(comp)
        await shutdown_components(comp)

        assert events == [
            "on_before_initialize",
            "initialize",
            "on_after_initialize",
            "on_before_shutdown",
            "shutdown",
            "on_after_shutdown"
        ]

    @pytest.mark.asyncio
    async def test_component_handler_called_before_global_handlers(self):
        """Test component-specific handlers are called before global handlers."""
        events = []

        class ComponentWithHandler:
            __metadata__ = {
                "name": "handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            def on_after_initialize(self):
                events.append("component_handler")

            initialize = None
            shutdown = None

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def global_handler(component):
            events.append("global_handler")

        comp = ComponentWithHandler()
        await initialize_components(comp)

        assert events == ["component_handler", "global_handler"]

    @pytest.mark.asyncio
    async def test_component_handler_exception_propagates(self):
        """Test component handler exceptions propagate."""

        class ComponentWithFailingHandler:
            __metadata__ = {
                "name": "failing_handler_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            def on_before_initialize(self):
                raise ValueError("Component handler failed")

            initialize = None
            shutdown = None

        comp = ComponentWithFailingHandler()

        with pytest.raises(ValueError, match="Component handler failed"):
            await initialize_components(comp)

    @pytest.mark.asyncio
    async def test_non_callable_attribute_ignored(self):
        """Test non-callable attributes named like handlers are ignored."""
        events = []

        class ComponentWithNonCallable:
            __metadata__ = {
                "name": "non_callable_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            on_before_initialize = "not a function"

            async def initialize(self):
                events.append("initialize")

            shutdown = None

        comp = ComponentWithNonCallable()
        await initialize_components(comp)

        # Should only have initialize, not crash on non-callable
        assert events == ["initialize"]

    @pytest.mark.asyncio
    async def test_component_without_handlers_still_works(self):
        """Test components without handler attributes still work normally."""
        events = []

        class NormalComponent:
            __metadata__ = {
                "name": "normal_component",
                "version": "1.0.0",
                "requires": set(),
                "_internals": Internals()
            }

            async def initialize(self):
                events.append("initialize")

            async def shutdown(self):
                events.append("shutdown")

        @on_event(ComponentEvent.AFTER_INITIALIZE)
        def global_handler(component):
            events.append("global_handler")

        comp = NormalComponent()
        await initialize_components(comp)

        assert events == ["initialize", "global_handler"]
