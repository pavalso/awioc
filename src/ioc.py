import asyncio
import importlib
import importlib.util
import inspect
import json
import logging.config
import sys
from enum import Enum

import pydantic
import yaml

from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from types import ModuleType
from typing import (
    Protocol,
    Coroutine,
    runtime_checkable,
    TypeVar,
    TypedDict,
    overload,
    Any,
    Union,
    Iterable,
    Optional
)

import pydantic_settings as settings
from cachetools import cached
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, provided, inject

from src.utils import expanded_path, deep_update


_Lib_type = TypeVar("_Lib_type")
_Model_type = TypeVar("_Model_type", bound=pydantic.BaseModel)
_S_type = TypeVar("_S_type", bound=type["Settings"])
_M_type = TypeVar("_M_type", bound=type[pydantic.BaseModel])
_P_type = TypeVar("_P_type", bound=pydantic.BaseModel)

_CONFIGURATIONS = {}

class Settings(settings.BaseSettings):
    model_config = settings.SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            env_nested_delimiter="_",
            env_nested_max_split=1,
            env_prefix="",
            cli_ignore_unknown_args=True,
            cli_avoid_json=True,
            cli_parse_args=True,
            validate_default=True
        )

    @cached(cache={}, key=lambda _, type_: type_)
    def get_config(self, config_type: type[_P_type]) -> _P_type:
        for name, model in _CONFIGURATIONS.items():
            if model == config_type:
                return getattr(self, name)
        raise ValueError(f"Configuration for type {config_type} not found")

    @classmethod
    def load_config(cls: type[_S_type]) -> _S_type:
        mapped_fields = {
            value.__name__: pydantic.Field(default_factory=value, alias=key) for key, value in _CONFIGURATIONS.items()
        }

        annotations = {
            value.__name__: value for value in _CONFIGURATIONS.values()
        }

        return type(
            "BaseSettings",
            (cls,),
            {
                "__annotations__": annotations,
                **mapped_fields
            })()

def clear_configurations():
    """Clear all registered configurations."""
    _CONFIGURATIONS.clear()

def register_configuration(
        _: Optional[_M_type] = None,
        prefix: str = None) -> _M_type:
    def __wrapper__(model: _M_type):
        nonlocal prefix

        assert issubclass(model, pydantic.BaseModel)

        if prefix is None:
            frm = inspect.stack()[2]
            mod = inspect.getmodule(frm[0])
            prefix = mod.__name__

        prefix = prefix.strip("_")
        prefix = prefix.lower()
        prefix = " ".join(prefix.split())
        prefix = prefix.replace(" ", "_")

        if prefix in _CONFIGURATIONS:
            raise ValueError(
                f"Configuration prefix collision: '{prefix}' "
                f"already registered for {_CONFIGURATIONS[prefix]}"
            )

        _CONFIGURATIONS[prefix] = model

        return model
    return __wrapper__ if _ is None else __wrapper__(_)


class ComponentMetadata(TypedDict):
    """
    Metadata for a component.
    Used for identification and configuration.

    Attributes:
        name (str): The name of the component.
        version (str): The version of the component.
        description (str): A brief description of the component.
        wire (Optional[bool]): Whether the component should be auto-wired.
        wirings (Optional[set[str]]): A set of module names to wire.
        requires (Optional[set[Component]]): A set of other components this component depends on.
            Those components MUST be registered in the container for this component to work.
        config (Optional[type[BaseModel]]): An optional Pydantic model for configuration.
    """
    name: str
    version: str
    description: str
    wire: Optional[bool]
    wirings: Optional[set[str]]
    requires: Optional[set["Component"]]
    config: Optional[set[type[pydantic.BaseModel]]]

    _internals: Optional["_Internals"]

class AppMetadata(ComponentMetadata):
    base_config: Optional[type[Settings]]

class ComponentTypes(Enum):
    APP = "app"
    PLUGIN = "plugin"
    LIBRARY = "library"
    COMPONENT = "component"

@dataclass
class _Internals:
    required_by: set["Component"] = field(default_factory=set)
    initialized_by: set["Component"] = field(default_factory=set)
    is_initialized: bool = False
    is_initializing: bool = False
    type: ComponentTypes = ComponentTypes.COMPONENT

ComponentMetadata = Union[ComponentMetadata, dict]

@runtime_checkable
class Component(Protocol):
    __metadata__: ComponentMetadata

    initialize: Optional[Coroutine[..., Any, Any]]
    shutdown: Optional[Coroutine[..., Any, Any]]

@runtime_checkable
class AppComponent(Component, Protocol):
    __metadata__: Union[ComponentMetadata, AppMetadata]

    initialize: Coroutine[..., Any, Any]
    shutdown: Coroutine[..., Any, Any]

@runtime_checkable
class PluginComponent(Component, Protocol): ...
@runtime_checkable
class LibraryComponent(Component, Protocol): ...

class AppContainer(containers.DeclarativeContainer):
    __self__ = providers.Self()
    api = providers.Object(None)

    config = providers.Object(None)
    logger = providers.Object(None)

    components = providers.Singleton(dict)

class ContainerInterface:
    """Interface for interacting with the AppContainer."""

    def __init__(self, container: AppContainer) -> None:
        self._container = container

        self._app_component: Optional[Component] = None
        self._libs_map: dict[str, providers.Provider[LibraryComponent]] = {}
        self._plugins_map: dict[str, providers.Provider[PluginComponent]] = {}

        self._monotonic_id = 0

        container.api.override(
            providers.Object(self)
        )

    @property
    def app_config_model(self):
        app = self.provided_app()
        meta = app.__metadata__
        if "base_config" in meta and meta["base_config"] is not None:
            cfg_cls = meta["base_config"]
            assert issubclass(cfg_cls, Settings)
            return cfg_cls
        raise ValueError("App base configuration model is not defined in the app metadata.")

    @property
    def ioc_config_model(self):
        app = self.provided_app()
        meta = app.__metadata__
        if "ioc_config" in meta and meta["ioc_config"] is not None:
            ioc_config = meta["ioc_config"]
            assert isinstance(ioc_config, Settings)
            return ioc_config
        raise ValueError("IOC configuration model is not defined in the app metadata.")

    @property
    def components(self) -> list[Component]:
        return list(
            component()
            for component in self._container.components().values())

    def raw_container(self) -> AppContainer:
        return self._container

    def provided_libs(self) -> set[LibraryComponent]:
        return set(lib() for lib in self._libs_map.values())

    def provided_lib(self, type_: type[_Lib_type]) -> _Lib_type:
        return self._libs_map[type_.__qualname__]()

    @overload
    def provided_config(self, model: type[_Model_type]) -> _Model_type: ...
    @overload
    def provided_config(self, model: None = None) -> Settings: ...
    def provided_config(self, model: Optional[type[_Model_type]] = None):
        cfg = self._container.config()
        if model is None:
            return cfg
        return getattr(cfg, model.__name__)

    def provided_app(self) -> AppComponent:
        if self._app_component is None:
            raise RuntimeError("App component not set")
        return self._app_component

    def provided_plugins(self) -> set[PluginComponent]:
        # TODO: Implement this
        return set(plugin() for plugin in self._plugins_map.values())

    def provided_logger(self) -> Logger:
        return self._container.logger()

    @staticmethod
    def __init_component(
            component: Component
    ) -> _Internals:
        assert hasattr(component, "__metadata__")
        assert "_internals" not in component.__metadata__

        _internals = _Internals()
        component.__metadata__["_internals"] = _internals

        for req in component_requires(component):
            ContainerInterface.__init_component(req)
            req.__metadata__["_internals"].required_by.add(component)

        return _internals

    @staticmethod
    def __deinit_component(
            component: Component
    ):
        assert hasattr(component, "__metadata__")
        assert "_internals" in component.__metadata__

        del component.__metadata__["_internals"]

        for req in component_requires(component):
            req.__metadata__["_internals"].required_by.discard(component)

    def register_libraries(
            self,
            *libs: tuple[str | type, LibraryComponent]
    ) -> None:
        for key, lib in libs:
            lib_id = key if isinstance(key, str) else key.__qualname__

            self.__init_component(lib)
            component_internals(lib).type = ComponentTypes.LIBRARY

            provider = providers.Object(lib)
            self._libs_map[lib_id] = provider
            self._container.components()[lib_id] = provider

    def unregister_libraries(
            self,
            *types: type[_Lib_type]
    ) -> None:
        assert self._container.libs().keys() >= {type_.__qualname__ for type_ in types}
        for type_ in types:
            self.__deinit_component(self._container.libs()[type_.__qualname__]())
            del self._container.libs()[type_.__qualname__]

    def register_plugins(
            self,
            *plugins: PluginComponent
    ) -> None:
        assert self._container.plugins().isdisjoint(plugins)
        for plugin in plugins:
            self.__init_component(plugin)
            self._container.plugins().add(plugin)

    def unregister_plugins(
            self,
            *plugins: PluginComponent
    ) -> None:
        assert self._container.plugins().issuperset(plugins)
        for plugin in plugins:
            self.__deinit_component(plugin)
            self._container.plugins().discard(plugin)

    def set_app(self, app: AppComponent) -> None:
        self.__init_component(app)
        self._app_component = app
        self._container.components()[app.__metadata__["name"]] = providers.Object(app)

    def set_logger(
            self,
            logger: Logger
    ) -> None:
        self._container.logger.override(
            providers.Object(logger)
        )

    def set_config(
            self,
            config: Settings
    ) -> None:
        self._container.config.override(
            providers.Object(config)
        )

@overload
def get_library(type_: type[_Lib_type]) -> _Lib_type: ...
@overload
def get_library(type_: str) -> _Lib_type: ...
def get_library(type_: Union[type[_Lib_type], str]) -> _Lib_type:
    if isinstance(type_, str):
        return Provide["libs", provided().get.call(type_).call()]
    return Provide["libs", provided().get.call(type_.__qualname__).call()]

@overload
def get_config(model: type[_Model_type]) -> _Model_type: ...
@overload
def get_config(model: None = None) -> Optional[pydantic.BaseModel]: ...
def get_config(model: Optional[type[_Model_type]] = None) -> Optional[_Model_type]:
    if model is None:
        return Provide["config", provided()]
    return Provide["config", getattr(provided(), model.__name__)]

def get_container_api() -> ContainerInterface:
    return Provide["api", provided()]

def get_raw_container() -> AppContainer:
    return Provide["__self__", provided()]

def get_app() -> AppComponent:
    return Provide["app", provided()]

@overload
def get_logger() -> Logger: ...
@overload
def get_logger(*name: str) -> Logger: ...
def get_logger(*name: str) -> Logger:
    if not name:
        calling_frame = inspect.stack()[1]
        mod = inspect.getmodule(calling_frame[0])
        name = mod.__name__ if mod else "logger"
    else:
        name = ".".join(name)

    return Provide["logger", provided().getChild.call(name)]

def component_requires(*components: Component, recursive: bool = False) -> set[Component]:
    """
    Get the full set of components required by the given components.

    :param components: The initial components to analyze.
    :param recursive: Whether to include dependencies of dependencies.
    :return: A set of all required components.
    """
    required = set()

    for component in components:
        for req in component.__metadata__.get("requires", set()):
            if req in required:
                continue
            required.add(req)
            if recursive:
                required.update(component_requires(req, recursive=True))

    return required

def component_internals(component: Component) -> _Internals:
    """
    Get the internal metadata of a component.

    :param component: The component to analyze.
    :return: The internal metadata of the component.
    """
    assert "_internals" in component.__metadata__
    return component.__metadata__["_internals"]

def as_component(obj: Any) -> Component:
    if not hasattr(obj, "__metadata__"):
        obj.__metadata__ = {
            "name": getattr(obj, "__qualname__", obj.__class__.__qualname__),
            "version": "0.0.0",
            "wire": False,
            "description": getattr(obj, "__doc__", "") or ""
        }

    if not hasattr(obj, "initialize"):
        obj.initialize = None

    if not hasattr(obj, "shutdown"):
        obj.shutdown = None

    return obj

def component_str(comp: Component) -> str:
    meta = comp.__metadata__
    return f"{meta['name']} v{meta['version']}"


# CONFIG.PY

class IOCComponentsDefinition(pydantic.BaseModel):
    app: Path

    libraries: dict[str, Path] = pydantic.Field(default_factory=dict)
    plugins: list[Path] = pydantic.Field(default_factory=list)


class IOCBaseConfig(Settings):
    config_path: Optional[Path] = None

    context: Optional[str] = None

    @pydantic.field_validator("config_path", mode="before")
    @classmethod
    def validate_paths(cls, v):
        if v is None:
            return v
        return expanded_path(v)


def create_container(
        container_cls=AppContainer
) -> ContainerInterface:
    """
    Create and return an instance of the application container.

    :param container_cls: The class of the container to instantiate.
    :return: An instance of the application container.
    """
    return ContainerInterface(
        container=container_cls(
            app=providers.Object(None),
            config=providers.Singleton(Settings),
            logger=providers.Singleton(logging.getLogger),
            libs=dict(),
            plugins=set()
        )
    )

def initialize_ioc_app():
    """
    TODO
    """
    ioc_config_env = IOCBaseConfig.load_config()

    if ioc_config_env.context:
        ioc_config_env.model_config["env_file"] = f".{ioc_config_env.context}.env"
        ioc_config_context = ioc_config_env.load_config()
    else:
        ioc_config_context = ioc_config_env

    if ioc_config_context.config_path is not None:
        file_data = load_file(ioc_config_context.config_path)
    else:
        file_data = {}

    ioc_components_definition = IOCComponentsDefinition.model_validate(file_data)

    app = compile_component(ioc_components_definition.app)

    plugins = {
        compile_component(plugin_name)
        for plugin_name in ioc_components_definition.plugins
    }
    libraries = {
        id_: compile_component(library_name)
        for id_, library_name in ioc_components_definition.libraries.items()
    }

    api_container = ContainerInterface(
        AppContainer(
            logger=providers.Singleton(logging.getLogger),
            libs=providers.Singleton(dict),
            plugins=providers.Singleton(set)
        )
    )

    api_container.set_app(app)

    if libraries:
        api_container.register_libraries(*libraries.items())

    if plugins:
        api_container.register_plugins(*plugins)

    app.__metadata__["ioc_components_definition"] = ioc_components_definition
    app.__metadata__["ioc_config"] = ioc_config_context

    return api_container

def compile_ioc_app(
        ioc_api: ContainerInterface
):
    """
    TODO
    """
    reconfigure_ioc_app(ioc_api, components=ioc_api.components.values())

def reconfigure_ioc_app(
        ioc_api: ContainerInterface,
        components: Iterable[Component]
):
    """
    TODO
    """
    _inject_dependencies(ioc_api, components=components)

    base_config = ioc_api.app_config_model
    ioc_config = ioc_api.ioc_config_model

    base_config.model_config = ioc_config.model_config
    env_config = base_config.load_config()

    config_file_content = load_file(ioc_config.config_path) if ioc_config.config_path else {}

    file_config = env_config.model_validate(config_file_content)

    validated_config = env_config.model_validate(
        deep_update(
            file_config.model_dump(exclude_unset=True, by_alias=True),
            env_config.model_dump(exclude_unset=True, by_alias=True)
        )
    )

    ioc_api.set_config(validated_config)

    wire(ioc_api, components=components)

def compile_component(name: Path):
    # Determine module path and desired module name
    if name.is_file():
        module_path = name
        module_name = name.stem

    elif name.with_suffix(".py").is_file():
        module_path = name.with_suffix(".py")
        module_name = name.stem

    elif name.is_dir():
        module_path = name / "__init__.py"
        module_name = name.name

    else:
        raise FileNotFoundError(f"Component not found: {name}")

    if module_name in sys.modules:
        return as_component(sys.modules[module_name])

    # Create spec
    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path.as_posix(),
        submodule_search_locations=[module_path.parent.as_posix()]
        if module_path.name == "__init__.py"
        else None
    )

    assert spec is not None
    loader = spec.loader
    assert loader is not None

    # Create module with the desired name
    module = importlib.util.module_from_spec(spec)

    # Guarantee module.__name__ == module_name
    sys.modules[module_name] = module

    # Execute module code
    loader.exec_module(module)

    return as_component(module)

def load_file(
        path: Path
) -> dict:
    """
    TODO
    """
    assert path is not None

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.absolute()}")

    if path.is_dir():
        raise IsADirectoryError(path.absolute())

    with open(path, "r", encoding="utf-8") as fp:
        if fp.read(1) == "":
            return {}

        fp.seek(0)

        if path.name.endswith(".yaml"):
            return yaml.safe_load(fp)
        if path.name.endswith(".json"):
            return json.load(fp)

        raise RuntimeError("Invalid file type give: %s" % path.name)

def reload_configuration(
        api_container: ContainerInterface
):
    raw_container = api_container.raw_container()

    raw_container.config.reset_override()
    raw_container.logger.reset_override()

    _inject_dependencies(api_container)
    config = _setup_configuration(api_container)

    raw_container.config.override(config)
    raw_container.wire((__name__,))

    logger = _setup_logging()
    raw_container.logger.override(logger)

    _setup_locale()

    wire(api_container)


def _inject_dependencies(
        container: ContainerInterface,
        components: Optional[Iterable[Component]] = None
):
    """
    TODO
    """
    if components is None:
        components = container.components.values()

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


@inject
async def register_plugin(
        plugin: PluginComponent,
        api_container=get_container_api(),
        logger=get_logger()
) -> PluginComponent:
    """
    Register a new plugin into the application container and wire it.

    :param plugin: The plugin component to register.
    :param api_container: The application container.
    :param logger: The logger instance.
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

    api_container.set_config(
        _setup_configuration(api_container)
    )

    wire(api_container, components=(plugin,))

    return plugin


@inject
async def unregister_plugin(
        plugin: PluginComponent,
        api_container=get_container_api(),
        logger=get_logger()
) -> None:
    """
    Unregister a plugin from the application container.

    :param plugin: The plugin component to unregister.
    :param api_container: The application container.
    :param logger: The logger instance.
    """
    caller_frame = inspect.stack()[2]  # Get the frame of the caller of unregister_plugin. Avoid Inject frame.

    if plugin not in api_container.provided_plugins():
        logger.warning("Plugin not registered: %s v%s [From: %s.%s]",
                       plugin.__metadata__['name'],
                       plugin.__metadata__['version'],
                       caller_frame.filename,
                       caller_frame.lineno)
        return

    if component_internals(plugin).required_by:
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


@inject
async def initialize_components(
        *components: Component,
        return_exceptions: bool = False,
        logger=get_logger()
):
    """
    Initialize the specified components.

    :param components: Components to initialize.
    :param return_exceptions: Whether to return exceptions instead of raising them.
    :param logger: The logger instance.
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
        _internal.is_initializing = True
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
            if await comp.initialize() is False:
                logger.debug("Component initialization aborted: %s v%s",
                             comp.__metadata__['name'],
                             comp.__metadata__['version'])
                return
        else:
            logger.debug("Component has no initialize method: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
        _internal.is_initializing = False
        _internal.is_initialized = True

    _ret = await asyncio.gather(
        *map(__initialize, components),
        return_exceptions=return_exceptions
    )

    _exceptions = [_exc for _exc in _ret if isinstance(_exc, Exception)]

    if return_exceptions:
        return _exceptions

    elif _exceptions:
        raise ExceptionGroup(
            "One or more errors occurred during component initialization.",
            _exceptions
        )

    return components


@inject
async def shutdown_components(
        *components: Component,
        return_exceptions: bool = False,
        logger=get_logger()
):
    """
    Shutdown the specified components.

    :param components: Components to shut down.
    :param return_exceptions: Whether to return exceptions instead of raising them.
    :param logger: The logger instance.
    """

    async def __shutdown(comp: Component):
        _internal = component_internals(comp)
        if not _internal.is_initialized:
            logger.debug("Component not initialized: %s v%s",
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
            await comp.shutdown()
        else:
            logger.debug("Component has no shutdown method: %s v%s",
                         comp.__metadata__['name'],
                         comp.__metadata__['version'])
        _internal.is_initialized = False

    _ret = await asyncio.gather(
        *map(__shutdown, components),
        return_exceptions=return_exceptions
    )

    _exceptions = [_exc for _exc in _ret if isinstance(_exc, Exception)]

    if _exceptions:
        if not return_exceptions:
            raise ExceptionGroup(
                "One or more errors occurred during component shutdown.",
                _exceptions
            )
        return _exceptions

    return components
