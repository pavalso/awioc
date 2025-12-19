import logging
from typing import Iterable

from dependency_injector import providers

logger = logging.getLogger(__name__)

from .components.protocols import Component
from .config.base import Settings
from .config.loaders import load_file
from .config.models import IOCComponentsDefinition, IOCBaseConfig
from .config.setup import setup_logging
from .container import AppContainer, ContainerInterface
from .di.wiring import wire, inject_dependencies
from .loader.module_loader import compile_component
from .utils import deep_update


def create_container(
        container_cls=AppContainer
) -> ContainerInterface:
    """
    Create and return an instance of the application container.

    :param container_cls: The class of the container to instantiate.
    :return: An instance of the application container.
    """
    logger.debug("Creating container with class: %s", container_cls.__name__)
    container = container_cls()
    container.config.override(providers.Singleton(Settings))
    container.logger.override(providers.Singleton(logging.getLogger))
    logger.debug("Container created successfully")
    return ContainerInterface(container=container)


def initialize_ioc_app() -> ContainerInterface:  # pragma: no cover
    """
    Initialize the IOC application.

    Loads environment configuration, processes context-specific settings,
    loads components definitions, and creates the container with all components.

    :return: The initialized container interface.
    """
    logger.info("Initializing IOC application")
    ioc_config_env = IOCBaseConfig.load_config()
    logger.debug("Loaded IOC base configuration")

    if ioc_config_env.context:
        logger.debug("Loading context-specific configuration: %s", ioc_config_env.context)
        ioc_config_env.model_config["env_file"] = f".{ioc_config_env.context}.env"
        ioc_config_context = ioc_config_env.load_config()
    else:
        ioc_config_context = ioc_config_env

    logger.debug("Loading config file: %s", ioc_config_context.config_path)
    file_data = load_file(ioc_config_context.config_path)

    ioc_components_definition = IOCComponentsDefinition.model_validate(file_data)
    logger.debug("Validated components definition")

    logger.debug("Compiling app component: %s", ioc_components_definition.app)
    app = compile_component(ioc_components_definition.app)

    logger.debug("Compiling %d plugins", len(ioc_components_definition.plugins))
    plugins = {
        compile_component(plugin_name)
        for plugin_name in ioc_components_definition.plugins
    }
    logger.debug("Compiling %d libraries", len(ioc_components_definition.libraries))
    libraries = {
        id_: compile_component(library_name)
        for id_, library_name in ioc_components_definition.libraries.items()
    }

    container = AppContainer()
    container.logger.override(providers.Singleton(logging.getLogger))
    api_container = ContainerInterface(container)

    api_container.set_app(app)

    if libraries:
        api_container.register_libraries(*libraries.items())

    if plugins:
        api_container.register_plugins(*plugins)

    app_internals = app.__metadata__["_internals"]
    assert app_internals is not None

    app_internals.ioc_components_definition = ioc_components_definition
    app_internals.ioc_config = ioc_config_context

    logger.info("IOC application initialized successfully")
    return api_container


def compile_ioc_app(ioc_api: ContainerInterface):  # pragma: no cover
    """
    Compile the IOC application by reconfiguring all components.

    :param ioc_api: The container interface.
    """
    logger.info("Compiling IOC application")
    reconfigure_ioc_app(ioc_api, components=ioc_api.components)
    logger.info("IOC application compiled successfully")


def reconfigure_ioc_app(
        ioc_api: ContainerInterface,
        components: Iterable[Component]
):
    """
    Reconfigure the IOC application with the given components.

    :param ioc_api: The container interface.
    :param components: Components to reconfigure.
    """
    logger.debug("Reconfiguring IOC application")
    inject_dependencies(ioc_api, components=components)

    base_config = ioc_api.app_config_model
    ioc_config = ioc_api.ioc_config_model

    base_config.model_config = ioc_config.model_config
    env_config = base_config.load_config()
    logger.debug("Loaded environment configuration: %s", type(env_config).__name__)

    config_file_content = load_file(ioc_config.config_path)

    file_config = env_config.model_validate(config_file_content)
    logger.debug("Validated file configuration")

    validated_config = env_config.model_validate(
        deep_update(
            file_config.model_dump(exclude_unset=True, by_alias=True),
            env_config.model_dump(exclude_unset=True, by_alias=True)
        )
    )

    ioc_api.set_config(validated_config)
    logger.debug("Wiring components")
    wire(ioc_api, components=components)
    logger.debug("Reconfiguration complete")


def reload_configuration(api_container: ContainerInterface):  # pragma: no cover
    """
    Reload configuration for the container.

    :param api_container: The container interface.
    """
    logger.info("Reloading configuration")
    raw_container = api_container.raw_container()

    raw_container.config.reset_override()
    raw_container.logger.reset_override()
    logger.debug("Reset container overrides")

    inject_dependencies(api_container)

    # Setup configuration
    base_config = api_container.app_config_model
    ioc_config = api_container.ioc_config_model
    base_config.model_config = ioc_config.model_config
    config = base_config.load_config()
    logger.debug("Loaded configuration: %s", type(config).__name__)

    raw_container.config.override(config)
    raw_container.wire((__name__,))

    new_logger = setup_logging()
    raw_container.logger.override(new_logger)

    wire(api_container)
    logger.info("Configuration reloaded successfully")
