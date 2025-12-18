"""Entry point for running the IOC framework as a module (python -m ioc)."""

import asyncio

from . import (
    compile_ioc_app,
    initialize_ioc_app,
    initialize_components,
    shutdown_components
)


async def run():
    api = initialize_ioc_app()
    app = api.provided_app()

    compile_ioc_app(api)

    try:
        await initialize_components(app)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await shutdown_components(app)


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
