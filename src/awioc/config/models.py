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


def _expand_component_path(component_ref: str) -> str:
    """
    Expand the path portion of a component reference.

    Component references can be in the format:
    - "path/to/module" - just a path
    - "path/to/module:attribute" - path with attribute reference

    :param component_ref: The component reference string.
    :return: The reference with expanded path.
    """
    if ":" in component_ref:
        path_part, ref_part = component_ref.rsplit(":", 1)
        return f"{expanded_path(path_part)}:{ref_part}"
    return str(expanded_path(component_ref))


class IOCComponentsDefinition(pydantic.BaseModel):
    app: str

    libraries: dict[str, str] = pydantic.Field(default_factory=dict)
    plugins: list[str] = pydantic.Field(default_factory=list)

    @pydantic.model_validator(mode="after")
    def validate_paths(self) -> "IOCComponentsDefinition":
        self.app = _expand_component_path(self.app)
        self.libraries = {
            name: _expand_component_path(path)
            for name, path in self.libraries.items()
        }
        self.plugins = [
            _expand_component_path(path)
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
        # if index is -1, append to the end
        if index == -1:
            _sources.extend(sources)
        else:
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
