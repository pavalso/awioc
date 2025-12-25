import inspect
from logging import Logger
from types import ModuleType
from typing import TypeVar, Optional, Union, overload, Any

import pydantic
from dependency_injector.wiring import Provide, provided

from ..components.protocols import AppComponent, Component
from ..components.registry import clean_module_name
from ..container import AppContainer, ContainerInterface

_Component = Union[Component, ModuleType, Any]
_AppComponent = Union[AppComponent, ModuleType, Any]
_Component_type = Union[Component, Any]

_Lib_type = TypeVar("_Lib_type", bound=_Component)
_Plugin_type = TypeVar("_Plugin_type", bound=_Component)
_Model_type = TypeVar("_Model_type", bound=pydantic.BaseModel)

@overload
def get_library(type_: str) -> _Component_type:  # pragma: no cover
    ...


@overload
def get_library(type_: type[_Lib_type]) -> _Lib_type:  # pragma: no cover
    ...


def get_library(type_: Union[type[_Lib_type], str]) -> _Lib_type:
    return Provide["api", provided().provided_lib.call(type_)]


def get_plugin(type_: str) -> Optional[_Component_type]:
    return Provide["api", provided().provided_plugin.call(type_)]


@overload
def get_config(model: type[_Model_type]) -> _Model_type:  # pragma: no cover
    ...


@overload
def get_config(model: None = None) -> Optional[pydantic.BaseModel]:  # pragma: no cover
    ...


def get_config(model: Optional[type[_Model_type]] = None) -> Optional[_Model_type]:
    if model is None:
        return Provide["config", provided()]
    return Provide["config", getattr(provided(), model.__name__)]


def get_container_api() -> ContainerInterface:
    return Provide["api", provided()]


def get_raw_container() -> AppContainer:
    return Provide["__self__", provided()]


def get_app() -> _AppComponent:
    return Provide["app", provided()]


@overload
def get_logger() -> Logger:  # pragma: no cover
    ...


@overload
def get_logger(*name: str) -> Logger:  # pragma: no cover
    ...


def get_logger(*name: str) -> Logger:
    if not name:
        calling_frame = inspect.stack()[1]
        mod = inspect.getmodule(calling_frame[0])
        name = clean_module_name(mod.__name__) if mod else "logger"
    else:
        name = ".".join(name)

    return Provide["logger", provided().getChild.call(name)]
