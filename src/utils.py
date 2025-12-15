import os

from pathlib import Path
from typing import Union


def expanded_path(path: Union[str, Path]) -> Path:
    """
    Expands environment variables, user tilde, and normalizes path separators
    in a given path.

    :param path: The path to expand.
    :return: The expanded and normalized path as a Path object.
    """
    if isinstance(path, Path):
        path = str(path)

    # Expand environment variables and user (~)
    return Path(os.path.expandvars(os.path.expanduser(path)))

def deep_update(d: dict, u: dict) -> dict:
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d
