import inspect
import logging
from typing import TypeVar, Optional

import pydantic

logger = logging.getLogger(__name__)

_M_type = TypeVar("_M_type", bound=type[pydantic.BaseModel])

_CONFIGURATIONS: dict[str, type[pydantic.BaseModel]] = {}


def register_configuration(
        _: Optional[_M_type] = None,
        prefix: str = None
) -> _M_type:
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
            logger.error("Configuration prefix collision: '%s' already registered for %s",
                         prefix, _CONFIGURATIONS[prefix])
            raise ValueError(
                f"Configuration prefix collision: '{prefix}' "
                f"already registered for {_CONFIGURATIONS[prefix]}"
            )

        _CONFIGURATIONS[prefix] = model
        logger.debug("Registered configuration '%s' with prefix '%s'", model.__name__, prefix)

        return model

    return __wrapper__ if _ is None else __wrapper__(_)


def clear_configurations():
    """Clear all registered configurations."""
    logger.debug("Clearing all registered configurations")
    _CONFIGURATIONS.clear()
