from typing import Protocol, runtime_checkable, Coroutine, Any, Optional, Union, Callable

from .metadata import ComponentMetadata, AppMetadata


@runtime_checkable
class Component(Protocol):
    __metadata__: ComponentMetadata

    initialize: Optional[Callable[..., Coroutine[Any, Any, None]]]
    shutdown: Optional[Callable[..., Coroutine[Any, Any, None]]]


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
