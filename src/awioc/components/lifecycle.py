import asyncio
import inspect
import logging
from typing import TYPE_CHECKING

from .protocols import Component, PluginComponent
from .registry import component_requires, component_internals, component_str, component_initialized

if TYPE_CHECKING:
    from ..container import ContainerInterface

logger = logging.getLogger(__name__) # TODO: remove global logger usage

async def initialize_components(
        *components: Component,
        return_exceptions: bool = False
):
    """
    Initialize the specified components.

    :param components: Components to initialize.
    :param return_exceptions: Whether to return exceptions instead of raising them.
    """
    async def __initialize(comp: Component):
        _internal = component_internals(comp)
        if _internal.is_initialized:
            logger.debug("Component already initialized: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            return
        if _internal.is_initializing:
            logger.debug("Component is already initializing: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            return
        if any(not component_internals(required).is_initialized
               for required in component_requires(comp)
               if required not in components
               ):
            logger.debug("Component dependencies not initialized: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            return
        if hasattr(comp, "initialize") and comp.initialize is not None:
            logger.debug("Initializing component: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            _internal.is_initializing = True
            try:
                if await comp.initialize() is False:
                    logger.debug("Component initialization aborted: %s v%s",
                                 comp.__metadata__['name'],
                                 comp.__metadata__['version'])
                    return
            finally:
                _internal.is_initializing = False
        else:
            logger.debug("Component has no initialize method: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
        _internal.is_initialized = True
        logger.debug("Component initialized: %s v%s",
                     comp.__metadata__['name'],
                     comp.__metadata__['version'])

    _ret = await asyncio.gather(
        *map(__initialize, components),
        return_exceptions=return_exceptions
    )

    _exceptions = [_exc for _exc in _ret if isinstance(_exc, Exception)]

    if return_exceptions:
        return _exceptions

    elif _exceptions:  # pragma: no cover
        raise ExceptionGroup(
            "One or more errors occurred during component initialization.",
            _exceptions
        )

    return components


async def shutdown_components(
        *components: Component,
        return_exceptions: bool = False
):
    """
    Shutdown the specified components.

    :param components: Components to shut down.
    :param return_exceptions: Whether to return exceptions instead of raising them.
    """
    async def __shutdown(comp: Component):
        _internal = component_internals(comp)
        if not _internal.is_initialized:
            logger.debug("Component not initialized: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            return
        if _internal.is_shutting_down:
            logger.debug("Component is already shutting down: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            return
        if any(component_internals(required).is_initialized
               for required in _internal.required_by
               if required not in components
               ):
            logger.debug("Component still required: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            return
        if hasattr(comp, "shutdown") and comp.shutdown is not None:
            logger.debug("Shutting down component: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            _internal.is_shutting_down = True
            try:
                await comp.shutdown()
            finally:
                _internal.is_shutting_down = False
        else:
            logger.debug("Component has no shutdown method: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
        _internal.is_initialized = False
        logger.debug("Component shut down: %s v%s",
                     comp.__metadata__['name'],
                     comp.__metadata__['version'])

    _ret = await asyncio.gather(
        *map(__shutdown, components),
        return_exceptions=return_exceptions
    )

    _exceptions = [_exc for _exc in _ret if isinstance(_exc, Exception)]

    if return_exceptions:
        return _exceptions

    if _exceptions:
        raise ExceptionGroup(
            "One or more errors occurred during component shutdown.",
            _exceptions
        )

    return components


async def register_plugin(
        api_container: "ContainerInterface",
        plugin: PluginComponent
) -> PluginComponent:
    """
    Register a new plugin into the application container and wire it.

    :param api_container: The application container.
    :param plugin: The plugin component to register.
    """
    caller_frame = inspect.stack()[2]  # Get the frame of the caller of register_plugin. Avoid Inject frame.

    if plugin in api_container.provided_plugins():
        logger.warning("Plugin already registered: %s v%s [From: %s.%s]",
                       plugin.__metadata__['name'],
                       plugin.__metadata__['version'],
                       caller_frame.filename,
                       caller_frame.lineno)
        return plugin

    api_container.register_plugins(plugin)

    logger.debug("Registering plugin: %s v%s [From: %s.%s]",
                 plugin.__metadata__['name'],
                 plugin.__metadata__['version'],
                 caller_frame.filename,
                 caller_frame.lineno)

    return plugin


async def wait_for_components(*components: Component):
    """
    Wait for the specified components to signal they are done.

    If a component has a `wait` method, it will be awaited. If a component
    does not have a `wait` method, a default infinite sleep is used.

    This function is typically cancelled via CancelledError when shutdown
    is requested.

    :param components: Components to wait for.
    """
    async def __wait(comp: Component):
        if hasattr(comp, "wait") and comp.wait is not None:
            logger.debug("Waiting for component: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            try:
                await comp.wait()
            except asyncio.CancelledError:
                logger.debug("Wait cancelled for component: %s v%s",
                             comp.__metadata__['name'],
                             comp.__metadata__['version'])
                raise
        else:
            logger.debug("Component has no wait method, using default: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass

    try:
        await asyncio.gather(*map(__wait, components))
    except asyncio.CancelledError:
        logger.debug("Wait for components cancelled")
        raise


async def unregister_plugin(
        api_container: "ContainerInterface",
        plugin: PluginComponent
) -> None:
    """
    Unregister a plugin from the application container.

    :param api_container: The application container.
    :param plugin: The plugin component to unregister.
    """
    caller_frame = inspect.stack()[2]  # Get the frame of the caller of unregister_plugin. Avoid Inject frame.

    if plugin not in api_container.provided_plugins():
        logger.warning("Plugin not registered: %s v%s [From: %s.%s]",
                       plugin.__metadata__['name'],
                       plugin.__metadata__['version'],
                       caller_frame.filename,
                       caller_frame.lineno)
        return

    if any(component_initialized(requirer)
           for requirer
           in component_internals(plugin).required_by):
        raise RuntimeError(
            f"Cannot unregister plugin {component_str(plugin)}; "
            "it is still required by other components"
        )

    if component_internals(plugin).is_initialized:
        await shutdown_components(plugin)

    api_container.unregister_plugins(plugin)

    logger.debug("Unregistering plugin: %s v%s [From: %s.%s]",
                 plugin.__metadata__['name'],
                 plugin.__metadata__['version'],
                 caller_frame.filename,
                 caller_frame.lineno)
