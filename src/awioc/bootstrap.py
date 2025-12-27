import logging
from typing import Iterable

from dependency_injector import providers
from pydantic_settings import YamlConfigSettingsSource, DotEnvSettingsSource

logger = logging.getLogger(__name__)

from .components.registry import component_internals
from .components.protocols import Component
from .config.models import IOCBaseConfig
from .container import AppContainer, ContainerInterface
from .di.wiring import wire, inject_dependencies
from .loader.module_loader import compile_component


def initialize_ioc_app() -> ContainerInterface:  # TODO: add test coverage
    """
    Initialize the IOC application.

    Loads environment configuration, processes context-specific settings,
    loads components definitions, and creates the container with all components.

    :return: The initialized container interface.
    """
    logger.info("Initializing IOC application")
    ioc_config = IOCBaseConfig()  # Initial load to get context and config path from .env and CLI

    if ioc_config.context:
        logger.debug("Loading context-specific configuration for context: %s", ioc_config.context)

        IOCBaseConfig.add_sources(lambda x: DotEnvSettingsSource(
            x,
            env_file=f".{ioc_config.context}.env"
        ))

        ioc_config = IOCBaseConfig(
            context=ioc_config.context
        )  # Reload to apply context-specific settings
    else:
        logger.debug("No context provided; using default environment configuration")

    if ioc_config.config_path:
        logger.debug("Loading configuration from: %s", ioc_config.config_path)

        IOCBaseConfig.add_sources(lambda x: YamlConfigSettingsSource(
            x,
            yaml_file=ioc_config.config_path
        ))

        ioc_config = IOCBaseConfig(
            context=ioc_config.context,
            config_path=ioc_config.config_path
        )  # Final load to apply YAML configuration
    else:
        logger.debug("No config path provided; skipping YAML configuration loading")

    return compile_ioc_app(ioc_config)


def compile_ioc_app(  # TODO: add test coverage
        ioc_config: IOCBaseConfig
) -> ContainerInterface:
    """
    Compile the IOC application using the provided container interface.

    :param ioc_config: The IOC configuration.
    """
    assert ioc_config is not None
    assert ioc_config.ioc_components_definitions is not None

    logger.info("Compiling IOC application")

    ioc_components_definitions = ioc_config.ioc_components_definitions

    logger.debug("Got components definition: %s", ioc_config.ioc_components_definitions)

    app = compile_component(ioc_components_definitions.app)

    # Compile plugins with error handling - missing plugins are skipped with a warning
    plugins = set()
    for plugin_name in ioc_components_definitions.plugins:
        try:
            plugin = compile_component(plugin_name)
            plugins.add(plugin)
        except FileNotFoundError:
            logger.warning("Plugin not found, skipping: %s", plugin_name)
        except Exception as e:
            logger.error("Failed to compile plugin '%s': %s", plugin_name, e)

    libraries = {
        id_: compile_component(library_name)
        for id_, library_name in ioc_components_definitions.libraries.items()
    }

    container = AppContainer()
    container.logger.override(providers.Singleton(logging.getLogger))
    api_container = ContainerInterface(container)

    api_container.set_app(app)

    if libraries:
        api_container.register_libraries(*libraries.items())

    if plugins:
        api_container.register_plugins(*plugins)

    app_internals = component_internals(app)
    assert app_internals is not None

    app_internals.ioc_config = ioc_config

    return reconfigure_ioc_app(api_container, components=api_container.components)


def reconfigure_ioc_app(
        api_container: ContainerInterface,
        components: Iterable[Component]
) -> ContainerInterface:
    """
    Reconfigure given components in the IOC application.

    :param api_container: The container interface.
    :param components: Components to reconfigure.
    """
    logger.info("Configuring IOC application")

    inject_dependencies(api_container, components=components)

    base_config = api_container.app_config_model
    base_config.model_config = api_container.ioc_config_model.model_config

    config = base_config.load_config()
    logger.debug("Loaded application configuration: %s", config)

    api_container.set_config(config)

    wire(api_container, components=components)

    return api_container
