"""AWIOC CLI Commands package.

This package contains all CLI commands implemented as AWIOC components.
"""

# Import command modules (registers them via @register_command decorator)
from . import run, init, add, remove, info, config, pot
from .base import (
    CommandContext,
    Command,
    BaseCommand,
    register_command,
    get_registered_commands,
)

__all__ = [
    "CommandContext",
    "Command",
    "BaseCommand",
    "register_command",
    "get_registered_commands",
    # Command modules
    "run",
    "init",
    "add",
    "remove",
    "info",
    "config",
    "pot",
]
