"""
Component event system for lifecycle hooks.

This module provides an event-oriented approach to component lifecycle management,
allowing registration of callbacks that fire before/after initialization and shutdown.
"""
import inspect
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Awaitable, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols import Component

logger = logging.getLogger(__name__)

# Type aliases
EventHandler = Callable[["Component"], Union[None, Awaitable[None]]]
CheckFn = Callable[["Component"], bool]


class ComponentEvent(Enum):
    """Events emitted during component lifecycle."""
    BEFORE_INITIALIZE = "before_initialize"
    AFTER_INITIALIZE = "after_initialize"
    BEFORE_SHUTDOWN = "before_shutdown"
    AFTER_SHUTDOWN = "after_shutdown"


@dataclass
class _RegisteredHandler:
    """Internal representation of a registered handler."""
    handler: EventHandler
    check: Optional[CheckFn] = None


# Registry: event -> list of registered handlers
_handlers: dict[ComponentEvent, list[_RegisteredHandler]] = {}


def on_event(
        event: ComponentEvent,
        check: Optional[CheckFn] = None,
        handler: Optional[EventHandler] = None
) -> Union[EventHandler, Callable[[EventHandler], EventHandler]]:
    """
    Register an event handler for component lifecycle events.

    Can be used as a direct call or as a decorator:

        # Decorator - all components
        @on_event(ComponentEvent.AFTER_INITIALIZE)
        async def handle_init(component):
            print(f"Initialized: {component.__metadata__['name']}")

        # Decorator - with check function
        @on_event(ComponentEvent.AFTER_INITIALIZE, check=lambda c: c.__metadata__["name"] == "my_plugin")
        async def handle_plugin_init(component):
            print("My plugin initialized!")

        # Direct call
        on_event(ComponentEvent.BEFORE_SHUTDOWN, check=is_critical, handler=cleanup)

    :param event: The event type to listen for.
    :param check: Optional function that receives the component and returns True if
                  the handler should be called. If None, handler is called for all components.
    :param handler: The callback function (sync or async). If None, returns a decorator.
    :return: The handler, or a decorator if handler is None.
    """

    def _register(h: EventHandler) -> EventHandler:
        if event not in _handlers:
            _handlers[event] = []
        _handlers[event].append(_RegisteredHandler(handler=h, check=check))
        logger.debug("Registered handler for %s (with check: %s)", event.value, check is not None)
        return h

    if handler is None:
        return _register
    return _register(handler)


# Alias for convenience
on = on_event


async def emit(component: "Component", event: ComponentEvent) -> None:
    """
    Emit an event for a component, calling all registered handlers whose check passes.

    :param component: The component emitting the event.
    :param event: The event being emitted.
    """
    if event not in _handlers:
        return

    handlers_to_call = []
    for registered in _handlers[event]:
        # If no check function, always call; otherwise check must return True
        if registered.check is None or registered.check(component):
            handlers_to_call.append(registered.handler)

    if not handlers_to_call:
        return

    logger.debug("Emitting %s for component %s (%d handlers)",
                 event.value, component.__metadata__["name"], len(handlers_to_call))

    for handler in handlers_to_call:
        try:
            result = handler(component)
            if inspect.iscoroutine(result):
                await result
        except Exception as e:
            logger.exception("Error in event handler for %s on %s: %s",
                             event.value, component.__metadata__["name"], e)
            raise


def clear_handlers(event: Optional[ComponentEvent] = None) -> None:
    """
    Clear event handlers.

    :param event: If provided, only clear handlers for this event.
                  If None, clear all handlers.
    """
    if event is None:
        _handlers.clear()
        logger.debug("Cleared all event handlers")
    elif event in _handlers:
        del _handlers[event]
        logger.debug("Cleared handlers for %s", event.value)
