from types import ModuleType
from typing import Optional, Iterable

from ..components.protocols import Component
from ..config.registry import register_configuration
from ..container import ContainerInterface


def inject_dependencies(
        container: ContainerInterface,
        components: Optional[Iterable[Component]] = None
):
    """
    Register component configurations.

    :param container: The container interface.
    :param components: Components to process. If None, uses all container components.
    """
    if components is None:
        components = container.components

    def __register_components(iterable: Iterable[Component]) -> None:
        for item in iterable:
            configs = item.__metadata__.get("config", set())

            if not isinstance(configs, Iterable):
                configs = (configs,)

            for config in configs:
                if hasattr(config, "__prefix__"):
                    prefix = config.__prefix__
                else:
                    prefix = item.__metadata__['name']
                register_configuration(config, prefix=prefix)

    __register_components(components)


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

                if component.__package__:
                    relative_wirings = set(
                        f"{component.__package__}.{wiring}"
                        for wiring in wirings_
                    )
                else:
                    relative_wirings = wirings_

                wirings.update((module_name, *relative_wirings))

    __register_components(components)

    api_container.raw_container().wire(modules=wirings)
