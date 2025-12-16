from typing import TypeVar

import pydantic
import pydantic_settings as settings
from cachetools import cached

from src.ioc.config.registry import _CONFIGURATIONS

_P_type = TypeVar("_P_type", bound=pydantic.BaseModel)
_S_type = TypeVar("_S_type", bound=type["Settings"])


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
                # Attribute name is the class name, not the prefix
                return getattr(self, model.__name__)
        raise ValueError(f"Configuration for type {config_type} not found")

    @classmethod
    def load_config(cls: type[_S_type]) -> _S_type:
        mapped_fields = {
            value.__name__: pydantic.Field(default_factory=value, alias=key)
            for key, value in _CONFIGURATIONS.items()
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
            }
        )()
