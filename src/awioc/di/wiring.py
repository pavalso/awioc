import importlib
import logging
import sys
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
                # For class-based components, check __package__ first, then derive from __module__
                if isinstance(component, ModuleType):
                    package = component.__package__
                else:
                    # For class-based components, check __package__ attribute first
                    package = getattr(component, "__package__", None)
                    # Fall back to deriving package from __module__
                    if not package:
                        # Check if the module itself is a package (directory with __init__.py)
                        # If so, use it as the package; otherwise use its parent
                        module_obj = sys.modules.get(module_name)
                        if module_obj and hasattr(module_obj, '__path__'):
                            # Module is a package, use it directly
                            package = module_name
                        elif "." in module_name:
                            # Module is a regular file, use parent as package
                            package = module_name.rsplit(".", 1)[0]

                if package:
                    relative_wirings = set(
                        f"{package}.{wiring}"
                        for wiring in wirings_
                    )
                else:
                    relative_wirings = set(wirings_)

                wirings.update((module_name, *relative_wirings))
                logger.debug("Added wiring for component: %s", module_name)

    __register_components(components)

    # Convert module names to actual module objects for dependency_injector
    module_objects = set()
    for module_name in wirings:
        # Try to get from sys.modules first (already imported)
        module_obj = sys.modules.get(module_name)
        if module_obj is None:
            # Try to import the module
            try:
                module_obj = importlib.import_module(module_name)
            except ImportError as e:
                logger.warning("Could not import module '%s' for wiring: %s", module_name, e)
                continue
        module_objects.add(module_obj)

    logger.debug("Wiring %d modules: %s", len(module_objects), [m.__name__ for m in module_objects])
    api_container.raw_container().wire(modules=module_objects)
    logger.debug("Container wiring complete")
