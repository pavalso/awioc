from typing import Protocol, runtime_checkable, Coroutine, Any, Optional, Union, Callable

from .metadata import ComponentMetadata, AppMetadata


@runtime_checkable
class Component(Protocol):
    """
    Protocol defining the interface for components.

    Required:
        __metadata__: ComponentMetadata dictionary

    Optional lifecycle methods:
        initialize: Async method called during component initialization
        shutdown: Async method called during component shutdown
        wait: Async method for blocking until shutdown

    Optional event handlers (auto-called during lifecycle):
        on_before_initialize: Called before initialize()
        on_after_initialize: Called after initialize()
        on_before_shutdown: Called before shutdown()
        on_after_shutdown: Called after shutdown()
    """
    __metadata__: ComponentMetadata

    initialize: Optional[Callable[..., Coroutine[Any, Any, None]]]
    shutdown: Optional[Callable[..., Coroutine[Any, Any, None]]]
    wait: Optional[Callable[..., Coroutine[Any, Any, None]]]


@runtime_checkable
class AppComponent(Component, Protocol):
    __metadata__: Union[ComponentMetadata, AppMetadata]

    initialize: Callable[..., Coroutine[Any, Any, None]]
    shutdown: Callable[..., Coroutine[Any, Any, None]]


@runtime_checkable
class PluginComponent(Component, Protocol):
    ...


@runtime_checkable
class LibraryComponent(Component, Protocol):
    ...
