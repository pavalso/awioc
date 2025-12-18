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
    config_path: Path = pydantic.Field(
        default=Path("ioc.yaml"),
        description="Path to the IOC components configuration file (YAML/JSON)"
    )

    context: Optional[str] = pydantic.Field(
        default=None,
        description="Environment context (loads .{context}.env file)"
    )

    logging_config: Optional[Path] = pydantic.Field(
        default=None,
        description="Path to logging configuration file (.ini)"
    )

    verbose: int = pydantic.Field(
        default=0,
        description="Verbosity level: -v (INFO), -vv (DEBUG), -vvv (DEBUG + libs)"
    )

    @pydantic.field_validator("config_path", mode="before")
    @classmethod
    def validate_config_path(cls, v):
        return expanded_path(v)

    @pydantic.field_validator("logging_config", mode="before")
    @classmethod
    def validate_logging_config(cls, v):
        if v is None:
            return v
        return expanded_path(v)
