"""Base command protocol and utilities for AWIOC CLI commands."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Protocol, runtime_checkable


@dataclass
class CommandContext:
    """Context passed to command execution.

    Contains parsed arguments and any additional context needed by commands.
    """
    command: str
    args: list[str] = field(default_factory=list)
    verbose: int = 0
    config_path: Optional[str] = None
    context: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Command(Protocol):
    """Protocol for CLI commands.

    Commands must implement the execute method which receives a CommandContext
    and returns an exit code (0 for success, non-zero for failure).
    """

    @property
    def name(self) -> str:
        """The command name (e.g., 'run', 'init', 'add')."""
        ...

    @property
    def description(self) -> str:
        """Short description of what the command does."""
        ...

    @property
    def help_text(self) -> str:
        """Detailed help text for the command."""
        ...

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the command.

        Args:
            ctx: The command context with parsed arguments.

        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        ...


class BaseCommand(ABC):
    """Abstract base class for CLI commands.

    Provides a common structure for implementing CLI commands as AWIOC components.
    Each command should be decorated with @as_component to register it.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The command name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of the command."""
        pass

    @property
    def help_text(self) -> str:
        """Detailed help text. Override for custom help."""
        return self.description

    @abstractmethod
    async def execute(self, ctx: CommandContext) -> int:
        """Execute the command. Must be implemented by subclasses."""
        pass


# Command registry to track available commands
_command_registry: dict[str, type] = {}


def register_command(name: str):
    """Decorator to register a command class in the registry.

    Usage:
        @register_command("init")
        @as_component(name="Init Command", ...)
        class InitCommand(BaseCommand):
            ...
    """

    def decorator(cls):
        _command_registry[name] = cls
        return cls

    return decorator


def get_registered_commands() -> dict[str, type]:
    """Get all registered command classes."""
    return _command_registry.copy()
