import logging
from types import ModuleType
from typing import Optional, Iterable

from ..components.protocols import Component
from ..config.registry import register_configuration, clear_configurations
from ..container import ContainerInterface

logger = logging.getLogger(__name__)


def inject_dependencies(
        container: ContainerInterface,
        components: Optional[Iterable[Component]] = None
):
    """
    Register component configurations.

    :param container: The container interface.
    :param components: Components to process. If None, uses all container components.
    """
    logger.debug("Injecting dependencies")
    if components is None:
        components = container.components

    def __register_components(iterable: Iterable[Component]) -> None:
        new_configs = {}

        for item in iterable:
            configs = item.__metadata__.get("config", set())

            if not isinstance(configs, Iterable):
                configs = (configs,)

            for config in configs:
                if hasattr(config, "__prefix__"):
                    prefix = config.__prefix__
                else:
                    prefix = item.__metadata__['name']
                logger.debug("Registering configuration for component '%s' with prefix '%s'",
                             item.__metadata__.get('name', 'unknown'), prefix)
                new_configs[prefix] = config

        clear_configurations(prefixes=new_configs.keys())

        for prefix, config in new_configs.items():
            register_configuration(config, prefix=prefix)

    __register_components(components)
    logger.debug("Dependency injection complete")


def wire(
        api_container: ContainerInterface,
        components: Optional[Iterable[Component]] = None
) -> object:
    """
    Wires the application container, registering configurations and initializing components.

    :param api_container: The application container to wire.
    :param components: Specific components to wire. If None, all components are wired.
    :return: The main application instance.
    """
    logger.debug("Wiring container")
    if components is None:
        components = api_container.components

    wirings = {__name__}

    def __register_components(iterable: Iterable[Component]) -> None:
        for component in iterable:
            if isinstance(component, ModuleType):
                module_name = component.__name__
            else:
                module_name = component.__module__

            if component.__metadata__.get("wire", True):
                wirings_ = component.__metadata__.get("wirings", set())

                if not isinstance(wirings_, Iterable) or isinstance(wirings_, str):
                    wirings_ = (wirings_,)

                # If the component is a module, we can retrieve its package via __package__
                # But if it's an instance, we need to get the package from its class
                if getattr(component, "__package__", None):
                    relative_wirings = set(
                        f"{component.__package__}.{wiring}"
                        for wiring in wirings_
                    )
                else:
                    relative_wirings = wirings_

                wirings.update((module_name, *relative_wirings))
                logger.debug("Added wiring for component: %s", module_name)

    __register_components(components)

    logger.debug("Wiring %d modules", len(wirings))
    api_container.raw_container().wire(modules=wirings)
    logger.debug("Container wiring complete")
