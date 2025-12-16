import json
from pathlib import Path

import yaml


def load_file(path: Path) -> dict:
    """
    Load configuration from a YAML or JSON file.

    :param path: Path to the configuration file.
    :return: Dictionary with configuration data.
    :raises FileNotFoundError: If the file does not exist.
    :raises IsADirectoryError: If the path is a directory.
    :raises RuntimeError: If the file type is not supported.
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
