from pathlib import Path
from typing import Optional

import pydantic

from .base import Settings
from ..utils import expanded_path


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
