from pathlib import Path
from typing import Optional, Callable

import pydantic
from pydantic_settings import PydanticBaseSettingsSource, BaseSettings

from .base import Settings
from ..utils import expanded_path

_sources: list[
    Callable[
        [type[BaseSettings]],
        PydanticBaseSettingsSource]
] = []

class IOCComponentsDefinition(pydantic.BaseModel):
    app: Path

    libraries: dict[str, Path] = pydantic.Field(default_factory=dict)
    plugins: list[Path] = pydantic.Field(default_factory=list)

    @pydantic.model_validator(mode="after")
    def validate_paths(self) -> "IOCComponentsDefinition":
        self.app = expanded_path(self.app)
        self.libraries = {
            name: expanded_path(path)
            for name, path in self.libraries.items()
        }
        self.plugins = [
            expanded_path(path)
            for path in self.plugins
        ]
        return self


class IOCBaseConfig(Settings):
    config_path: Path = pydantic.Field(
        default=Path("ioc.yaml"),
        description="Path to the IOC components configuration file (YAML/JSON)",
        exclude=True
    )

    context: Optional[str] = pydantic.Field(
        default=None,
        description="Environment context (loads .{context}.env file)",
        exclude=True
    )

    ioc_components_definitions: Optional[IOCComponentsDefinition] = pydantic.Field(
        default=None,
        description="Loaded IOC components definition",
        alias="components"
    )

    @classmethod
    def add_sources(
            cls,
            *sources: Callable[[pydantic.ConfigDict], PydanticBaseSettingsSource],
            index: int = -1,
    ) -> None:
        _sources.insert(index, *sources)

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings
        ) + tuple(map(lambda s: s(settings_cls), _sources))

    @pydantic.field_validator("config_path", mode="before")
    @classmethod
    def validate_config_path(cls, v):
        return expanded_path(v)
