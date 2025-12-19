import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def load_file(path: Path) -> dict:
    """
    Load configuration from a YAML or JSON file.

    :param path: Path to the configuration file.
    :return: Dictionary with configuration data.
    :raises FileNotFoundError: If the file does not exist.
    :raises IsADirectoryError: If the path is a directory.
    :raises RuntimeError: If the file type is not supported.
    """
    logger.debug("Loading configuration file: %s", path)
    assert path is not None

    if not path.exists():
        logger.error("Config file not found: %s", path.absolute())
        raise FileNotFoundError(f"Config file not found: {path.absolute()}")

    if path.is_dir():
        logger.error("Path is a directory, not a file: %s", path.absolute())
        raise IsADirectoryError(path.absolute())

    with open(path, "r", encoding="utf-8") as fp:
        if fp.read(1) == "":
            logger.debug("Config file is empty: %s", path)
            return {}

        fp.seek(0)

        if path.name.endswith(".yaml"):
            logger.debug("Parsing YAML file: %s", path.name)
            return yaml.safe_load(fp)
        if path.name.endswith(".json"):
            logger.debug("Parsing JSON file: %s", path.name)
            return json.load(fp)

        logger.error("Invalid file type: %s", path.name)
        raise RuntimeError("Invalid file type give: %s" % path.name)
