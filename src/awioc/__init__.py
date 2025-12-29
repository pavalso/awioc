"""
IOC Framework - Inversion of Control Framework for Python applications.

This module provides a clean public surface for the IOC framework.
Consumers should import from here for stable API access.
"""

from .api import (
    # Bootstrap
    initialize_ioc_app,
    compile_ioc_app,
    reconfigure_ioc_app,
    # Lifecycle
    initialize_components,
    shutdown_components,
    wait_for_components,
    register_plugin,
    unregister_plugin,
    # Events
    ComponentEvent,
    on_event,
    clear_event_handlers,
    # DI Providers
    get_library,
    get_config,
    get_container_api,
    get_raw_container,
    get_app,
    get_logger,
    get_plugin,
    get_component,
    wire,
    inject,
    # Config
    Settings,
    register_configuration,
    clear_configurations,
    load_file,
    IOCComponentsDefinition,
    IOCBaseConfig,
    # Container
    ContainerInterface,
    AppContainer,
    # Components
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
    ComponentMetadata,
    AppMetadata,
    ComponentTypes,
    RegistrationInfo,
    metadata,
    as_component,
    component_requires,
    component_required_by,
    component_internals,
    component_str,
    component_registration,
    # Loader
    compile_component,
    # Logging
    setup_logging,
)

from .project import (
    # Project API
    AWIOCProject,
    is_awioc_project,
    open_project,
    create_project,
)

__all__ = [
    # Bootstrap
    "initialize_ioc_app",
    "compile_ioc_app",
    "reconfigure_ioc_app",
    # Lifecycle
    "initialize_components",
    "shutdown_components",
    "wait_for_components",
    "register_plugin",
    "unregister_plugin",
    # Events
    "ComponentEvent",
    "on_event",
    "clear_event_handlers",
    # DI Providers
    "get_library",
    "get_config",
    "get_container_api",
    "get_raw_container",
    "get_app",
    "get_logger",
    "get_plugin",
    "get_component",
    "wire",
    "inject",
    # Config
    "Settings",
    "register_configuration",
    "clear_configurations",
    "load_file",
    "IOCComponentsDefinition",
    "IOCBaseConfig",
    # Container
    "ContainerInterface",
    "AppContainer",
    # Components
    "Component",
    "AppComponent",
    "PluginComponent",
    "LibraryComponent",
    "ComponentMetadata",
    "AppMetadata",
    "ComponentTypes",
    "RegistrationInfo",
    "metadata",
    "as_component",
    "component_required_by",
    "component_requires",
    "component_internals",
    "component_str",
    "component_registration",
    # Loader
    "compile_component",
    # Logging
    "setup_logging",
    # Project API
    "AWIOCProject",
    "is_awioc_project",
    "open_project",
    "create_project",
]
