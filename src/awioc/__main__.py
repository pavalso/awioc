"""Entry point for running the AWIOC framework as a module (python -m awioc)."""

import argparse
import asyncio
import logging
import logging.config
import sys
from pathlib import Path
from typing import Optional

from .commands import CommandContext, get_registered_commands
from .utils import expanded_path

logger = logging.getLogger(__name__)

# Available commands for help text
AVAILABLE_COMMANDS = {
    "run": "Start the AWIOC application (default)",
    "init": "Initialize a new AWIOC project",
    "add": "Add plugins or libraries to the project",
    "remove": "Remove plugins or libraries from the project",
    "info": "Show project information",
    "config": "Manage project configuration",
    "pot": "Manage shared component directories",
    "generate": "Generate manifest.yaml from components",
}


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with subcommands."""
    # Build epilog with available commands
    epilog_lines = ["\nAvailable commands:"]
    for cmd, desc in AVAILABLE_COMMANDS.items():
        epilog_lines.append(f"  {cmd:12} {desc}")
    epilog_lines.append("\nUse 'awioc <command> --help' for more information about a command.")

    parser = argparse.ArgumentParser(
        prog="awioc",
        description="AWIOC - Async Wired IOC Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(epilog_lines),
        add_help=False,  # We handle --help manually to support command-specific help
    )

    parser.add_argument(
        "-h", "--help",
        action="store_true",
        help="Show this help message and exit"
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        metavar="COMMAND",
        help="Command to execute (default: run)"
    )

    parser.add_argument(
        "args",
        nargs="*",
        metavar="ARGS",
        help="Command arguments"
    )

    parser.add_argument(
        "-c", "--config-path",
        type=Path,
        default=None,
        help="Path to the IOC components configuration file (YAML/JSON)"
    )

    parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Environment context (loads .{context}.env file)"
    )

    parser.add_argument(
        "--logging-config",
        type=Path,
        default=None,
        help="Path to logging configuration file (.ini)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Verbosity level: -v (INFO), -vv (DEBUG), -vvv (DEBUG + libs)"
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information"
    )

    return parser


def configure_logging(
        verbose: int = 0,
        logging_config: Optional[Path] = None
) -> None:
    """Configure logging based on CLI arguments.

    Priority:
    1. logging_config (.ini file) if provided
    2. verbose level (-v, -vv, -vvv)
    3. Default (WARNING level for minimal output)
    """
    if logging_config and logging_config.exists():
        logging.config.fileConfig(logging_config)
        return

    # For commands other than 'run', default to WARNING for cleaner output
    level_map = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG
    }
    level = level_map.get(min(verbose, 2), logging.DEBUG)

    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    if verbose >= 2:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if verbose < 3:
        for lib in ("asyncio", "urllib3", "httpcore", "httpx"):
            logging.getLogger(lib).setLevel(logging.WARNING)


def show_help(parser: argparse.ArgumentParser) -> int:
    """Show help message."""
    parser.print_help()
    return 0


def show_version() -> int:
    """Show version information."""
    try:
        from importlib.metadata import version
        ver = version("awioc")
    except Exception:
        ver = "unknown"
    print(f"awioc version {ver}")
    return 0


async def dispatch_command(
        command_name: str,
        ctx: CommandContext
) -> int:
    """Dispatch to the appropriate command handler.

    Args:
        command_name: Name of the command to execute.
        ctx: Command context with arguments and options.

    Returns:
        Exit code from the command.
    """
    registered_commands = get_registered_commands()

    if command_name not in registered_commands:
        logger.error(f"Unknown command: {command_name}")
        print(f"\nUnknown command: {command_name}")
        print(f"Available commands: {', '.join(AVAILABLE_COMMANDS.keys())}")
        print("Use 'awioc --help' for more information.")
        return 1

    # Instantiate and execute the command
    command_class = registered_commands[command_name]
    command = command_class()

    return await command.execute(ctx)


def show_command_help(command_name: str) -> int:
    """Show help for a specific command."""
    registered_commands = get_registered_commands()

    if command_name not in registered_commands:
        print(f"Unknown command: {command_name}")
        print(f"Available commands: {', '.join(AVAILABLE_COMMANDS.keys())}")
        return 1

    command_class = registered_commands[command_name]
    command = command_class()
    print(command.help_text)
    return 0


def main() -> int:
    """Main entry point for the CLI."""
    parser = create_parser()

    # Use parse_known_args to allow commands to have their own arguments
    args, remaining = parser.parse_known_args()

    # Handle --version flag
    if args.version:
        return show_version()

    command_name = args.command

    # Combine args.args and remaining arguments
    command_args = (args.args or []) + remaining

    # Check if --help or -h is requested for a specific command
    help_requested = args.help or "-h" in command_args or "--help" in command_args

    if help_requested:
        # If no command specified or command is 'run' and help was explicit on main parser
        if args.help and command_name == "run" and not args.args and not remaining:
            # Show main help
            return show_help(parser)
        else:
            # Show command-specific help
            return show_command_help(command_name)

    # Configure logging
    logging_config = None
    if args.logging_config:
        logging_config = expanded_path(args.logging_config)

    # For 'run' command, default to INFO level for better visibility
    verbose = args.verbose
    if command_name == "run" and verbose == 0:
        verbose = 1

    configure_logging(verbose=verbose, logging_config=logging_config)

    # Build command context
    config_path = None
    if args.config_path:
        config_path = str(expanded_path(args.config_path))

    # Combine args.args and remaining arguments
    command_args = (args.args or []) + remaining

    ctx = CommandContext(
        command=command_name,
        args=command_args,
        verbose=args.verbose,
        config_path=config_path,
        context=args.context,
    )

    # Execute the command
    try:
        exit_code = asyncio.run(dispatch_command(command_name, ctx))
        return exit_code
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130
    except Exception:
        logger.exception("Error executing command")
        return 1


if __name__ == "__main__":
    sys.exit(main())
