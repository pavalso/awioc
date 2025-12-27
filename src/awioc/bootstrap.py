import logging
from pathlib import Path
from typing import Iterable

from dependency_injector import providers
from pydantic_settings import YamlConfigSettingsSource, DotEnvSettingsSource

logger = logging.getLogger(__name__)

from .components.registry import component_internals
from .components.protocols import Component
from .config.models import IOCBaseConfig
from .container import AppContainer, ContainerInterface
from .di.wiring import wire, inject_dependencies
from .loader.module_loader import compile_component, compile_components_from_manifest
from .loader.manifest import has_awioc_dir


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


def _is_manifest_directory(plugin_ref: str) -> bool:
    """Check if a plugin reference points to a directory with .awioc/manifest.yaml."""
    # Skip pot references
    if plugin_ref.startswith("@"):
        return False

    # Check if it's a directory with .awioc/manifest.yaml
    path = Path(plugin_ref)
    if path.is_dir():
        return has_awioc_dir(path)

    return False


def compile_ioc_app(  # TODO: add test coverage
        ioc_config: IOCBaseConfig
) -> ContainerInterface:
    """
    Compile the IOC application using the provided container interface.

    Supports both single-file plugins and directory-based plugins with .awioc/manifest.yaml.
    When a plugin reference is a directory containing .awioc/manifest.yaml, all components
    defined in that manifest will be loaded.

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
    for plugin_ref in ioc_components_definitions.plugins:
        try:
            # Check if this is a directory with manifest.yaml
            if _is_manifest_directory(plugin_ref):
                logger.debug("Loading plugins from manifest directory: %s", plugin_ref)
                directory_plugins = compile_components_from_manifest(Path(plugin_ref))
                plugins.update(directory_plugins)
                logger.info(
                    "Loaded %d plugin(s) from %s",
                    len(directory_plugins),
                    plugin_ref
                )
            else:
                # Single plugin file or pot reference
                plugin = compile_component(plugin_ref)
                plugins.add(plugin)
        except FileNotFoundError:
            logger.warning("Plugin not found, skipping: %s", plugin_ref)
        except Exception as e:
            logger.error("Failed to compile plugin '%s': %s", plugin_ref, e)

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
