# awioc

A modern, async-first Inversion of Control (IoC) and Dependency Injection (DI) framework for Python applications.

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
    - [Components](#components)
    - [Dependency Injection](#dependency-injection)
    - [Configuration](#configuration)
    - [Lifecycle Management](#lifecycle-management)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Configuration Files](#configuration-files)
- [CLI Usage](#cli-usage)
- [Testing](#testing)
- [Examples](#examples)

## Overview

**awioc** is a comprehensive IoC/DI framework designed for building modular, testable, and maintainable Python
applications. It provides a protocol-based component system with full async/await support, automatic dependency
resolution, and flexible configuration management.

The framework follows the Inversion of Control principle, allowing you to define components with their dependencies
declaratively and letting the framework handle instantiation, initialization, and lifecycle management.

## Features

- **Protocol-Based Components**: Define components using Python protocols without inheritance constraints
- **Async-First Lifecycle**: Full async/await support for component initialization, execution, and shutdown
- **Automatic Dependency Resolution**: Components declare dependencies; the framework handles initialization order
- **Flexible Configuration**: Support for YAML/JSON files, environment variables, and Pydantic models
- **Dynamic Module Loading**: Load components from arbitrary file paths at runtime
- **Plugin Architecture**: Runtime registration and unregistration of plugin components
- **Comprehensive DI Providers**: Easy-to-use injection functions for libraries, configuration, and logging
- **CLI Interface**: Run applications directly with the `awioc` command

## Installation

```bash
pip install awioc
```

Or install from source:

```bash
git clone https://github.com/pavalso/awioc.git
cd awioc
pip install -e .
```

### Dependencies

- Python 3.11+
- pydantic ~= 2.12.4
- PyYAML ~= 6.0.3
- pydantic-settings ~= 2.12.0
- dependency-injector
- cachetools ~= 6.2.3

## Quick Start

### 1. Define a Component

Create a file `my_app.py`:

```python
import asyncio
from ioc import get_config, get_logger, inject
import pydantic


# Define configuration model
class AppConfig(pydantic.BaseModel):
    __prefix__ = "my_app_config"
    name: str = "MyApp"
    debug: bool = False


# Module-level metadata (required for component registration)
__metadata__ = {
    "name": "my_app",
    "version": "1.0.0",
    "description": "My Application",
    "wire": True,
    "config": AppConfig
}


# Define the application component
class MyApp:

    @inject
    async def initialize(
            self,
            logger=get_logger(),
            config=get_config(AppConfig)
    ) -> None:
        self.logger = logger
        self.config = config
        self.logger.info(f"Starting {config.name}...")

    async def wait(self) -> None:
        """Keep the application running."""
        while True:
            await asyncio.sleep(1)

    async def shutdown(self) -> None:
        self.logger.info("Shutting down...")


# Create instance and export lifecycle methods
my_app = MyApp()
initialize = my_app.initialize
shutdown = my_app.shutdown
wait = my_app.wait
```

### 2. Create Configuration

Create `ioc.yaml`:

```yaml
app: my_app

my_app_config:
  name: "My Awesome App"
  debug: true
```

### 3. Run the Application

```bash
awioc
```

Or with verbose logging:

```bash
awioc -vv
```

## Core Concepts

### Components

Components are the building blocks of an awioc application. The framework defines three component types:

#### AppComponent

The main application entry point. Requires `initialize` and `shutdown` methods.

```python
# my_app.py

# Module-level metadata (required)
__metadata__ = {
    "name": "my_app",
    "version": "1.0.0",
    "description": "Main application"
}


class MyApp:

    async def initialize(self) -> None:
        """Called when application starts."""
        pass

    async def shutdown(self) -> None:
        """Called when application stops."""
        pass

    async def wait(self) -> None:
        """Optional: keeps the application running."""
        pass


# Export lifecycle methods at module level
my_app = MyApp()
initialize = my_app.initialize
shutdown = my_app.shutdown
wait = my_app.wait
```

#### PluginComponent

Optional extensions that can be registered/unregistered at runtime.

```python
# my_plugin.py

# Module-level metadata (required)
__metadata__ = {
    "name": "my_plugin",
    "version": "1.0.0",
    "description": "Optional plugin"
}


class MyPlugin:

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


# Export lifecycle methods at module level
my_plugin = MyPlugin()
initialize = my_plugin.initialize
shutdown = my_plugin.shutdown
```

#### LibraryComponent

Reusable libraries that provide shared functionality.

```python
# database_lib.py

# Module-level metadata (required)
__metadata__ = {
    "name": "database",
    "version": "1.0.0",
    "description": "Database connection library"
}


class DatabaseLibrary:

    async def initialize(self) -> None:
        self.connection = await create_connection()

    async def shutdown(self) -> None:
        await self.connection.close()

    async def query(self, sql: str):
        return await self.connection.execute(sql)


# Export lifecycle methods at module level
database = DatabaseLibrary()
initialize = database.initialize
shutdown = database.shutdown
```

#### Component Metadata

Every component module must have a `__metadata__` attribute defined at the **module level** (not inside a class). The
framework loads modules as components, so the metadata must be accessible directly on the module object.

| Field         | Type             | Required | Description                           |
|---------------|------------------|----------|---------------------------------------|
| `name`        | `str`            | Yes      | Unique component identifier           |
| `version`     | `str`            | Yes      | Semantic version string               |
| `description` | `str`            | Yes      | Human-readable description            |
| `wire`        | `bool`           | No       | Enable auto-wiring for this component |
| `wirings`     | `set[str]`       | No       | Additional modules to wire            |
| `requires`    | `set[Component]` | No       | Component dependencies                |
| `config`      | `BaseModel`      | No       | Configuration model class             |

### Dependency Injection

awioc provides several provider functions for dependency injection:

#### Injecting Libraries

```python
from ioc import get_library, inject


@inject
async def my_function(db=get_library("database")):
    result = await db.query("SELECT * FROM users")
```

#### Injecting Configuration

```python
from ioc import get_config, inject
import pydantic


class ServerConfig(pydantic.BaseModel):
    __prefix__ = "server"
    host: str = "localhost"
    port: int = 8080


@inject
async def start_server(config=get_config(ServerConfig)):
    print(f"Starting on {config.host}:{config.port}")
```

#### Injecting Logger

```python
from ioc import get_logger, inject


@inject
def process_data(logger=get_logger()):
    # Logger automatically uses caller's module name
    logger.info("Processing data...")
```

#### Available Providers

| Function              | Description                                          |
|-----------------------|------------------------------------------------------|
| `get_library(type_)`  | Get a registered library by type or name             |
| `get_config(model)`   | Get configuration for a Pydantic model               |
| `get_logger(*name)`   | Get a logger (auto-detects caller module if no name) |
| `get_app()`           | Get the main application component                   |
| `get_container_api()` | Get the container interface                          |
| `get_raw_container()` | Get the underlying DI container                      |

### Configuration

Configuration in awioc follows a layered approach:

#### 1. Pydantic Models

Define configuration schemas using Pydantic:

```python
import pydantic


class DatabaseConfig(pydantic.BaseModel):
    __prefix__ = "database"  # Environment variable prefix

    host: str = "localhost"
    port: int = 5432
    name: str = "mydb"
    user: str = "admin"
    password: str = ""
```

#### 2. Configuration Registration

Register configuration models via component metadata:

```python
from ioc import register_configuration


@register_configuration
class MyConfig(pydantic.BaseModel):
    __prefix__ = "myapp"
    setting: str = "default"


class MyComponent:
    __metadata__ = {
        "name": "my_component",
        "config": MyConfig  # Auto-registered
    }
```

#### 3. Configuration Sources

Configuration values are loaded from (in order of precedence):

1. **Environment Variables**: `DATABASE_HOST=localhost`
2. **Context-specific .env files**: `.production.env`, `.development.env`
3. **YAML/JSON configuration files**: `ioc.yaml` or `ioc.json`

#### 4. IOC Base Configuration

The framework itself is configured via `IOCBaseConfig`:

| Variable             | Description                       | Default    |
|----------------------|-----------------------------------|------------|
| `IOC_CONFIG_PATH`    | Path to component definition file | `ioc.yaml` |
| `IOC_CONTEXT`        | Environment context               | None       |
| `IOC_LOGGING_CONFIG` | Path to logging INI file          | None       |
| `IOC_VERBOSE`        | Verbosity level (0-3)             | 0          |

### Lifecycle Management

Components follow a three-phase lifecycle:

```
┌─────────────────────────────────────────────────────────────┐
│                     APPLICATION LIFECYCLE                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ INITIALIZE   │───▶│    WAIT      │───▶│  SHUTDOWN    │  │
│  │              │    │              │    │              │  │
│  │ • Libraries  │    │ • App runs   │    │ • Plugins    │  │
│  │ • Plugins    │    │ • Handle     │    │ • Libraries  │  │
│  │ • App        │    │   requests   │    │ • App        │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Initialization Order

1. Libraries (in dependency order)
2. Plugins (parallel)
3. Application

#### Shutdown Order

1. Application
2. Plugins (parallel)
3. Libraries (reverse dependency order)

#### Programmatic Lifecycle Control

```python
from ioc import (
    initialize_ioc_app,
    compile_ioc_app,
    initialize_components,
    wait_for_components,
    shutdown_components
)


async def main():
    # Initialize framework
    api = initialize_ioc_app()
    compile_ioc_app(api)

    app = api.provided_app()
    libs = api.provided_libs()
    plugins = api.provided_plugins()

    try:
        # Start components
        await initialize_components(app)
        await initialize_components(*libs)
        await initialize_components(*plugins)

        # Run
        await wait_for_components(app)
    finally:
        # Cleanup
        await shutdown_components(*plugins)
        await shutdown_components(*libs)
        await shutdown_components(app)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         awioc Framework                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                      Public API (api.py)                  │   │
│  │  • Bootstrap functions    • Lifecycle functions          │   │
│  │  • DI providers           • Configuration utilities      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │ Components  │     │  Container  │     │   Config    │       │
│  │             │     │             │     │             │       │
│  │ • Protocols │     │ • AppCont.  │     │ • Settings  │       │
│  │ • Metadata  │     │ • Interface │     │ • Loaders   │       │
│  │ • Registry  │     │ • Providers │     │ • Registry  │       │
│  │ • Lifecycle │     │             │     │ • Models    │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│         │                    │                    │             │
│         └────────────────────┼────────────────────┘             │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Bootstrap (bootstrap.py)               │   │
│  │  • Container creation     • IOC initialization           │   │
│  │  • Component compilation  • Configuration loading        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │     DI      │     │   Loader    │     │    Utils    │       │
│  │             │     │             │     │             │       │
│  │ • Providers │     │ • Dynamic   │     │ • Paths     │       │
│  │ • Wiring    │     │   loading   │     │ • Merging   │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Module Structure

```
src/ioc/
├── __init__.py          # Public exports
├── __main__.py          # CLI entry point
├── api.py               # Public API surface
├── bootstrap.py         # Application initialization
├── container.py         # DI container implementation
├── utils.py             # Utility functions
│
├── components/          # Component system
│   ├── protocols.py     # Component protocols (Component, App, Plugin, Library)
│   ├── metadata.py      # Metadata structures and types
│   ├── registry.py      # Component registration utilities
│   └── lifecycle.py     # Initialization/shutdown management
│
├── config/              # Configuration management
│   ├── base.py          # Settings base class
│   ├── models.py        # IOC configuration models
│   ├── loaders.py       # YAML/JSON file loaders
│   ├── registry.py      # Configuration registration
│   └── setup.py         # Logging setup
│
├── di/                  # Dependency Injection
│   ├── providers.py     # DI provider functions
│   └── wiring.py        # Module wiring utilities
│
└── loader/              # Dynamic loading
    └── module_loader.py # Component compilation
```

## API Reference

### Bootstrap Functions

```python
from ioc import (
    initialize_ioc_app,
    create_container,
    compile_ioc_app,
    reconfigure_ioc_app,
    reload_configuration
)

# Initialize full IOC application
api = initialize_ioc_app()

# Create empty container
container = create_container()

# Compile components into container
compile_ioc_app(api)

# Reconfigure with current components
reconfigure_ioc_app(api)

# Reload configuration at runtime
reload_configuration(api)
```

### Lifecycle Functions

```python
from ioc import (
    initialize_components,
    shutdown_components,
    wait_for_components,
    register_plugin,
    unregister_plugin
)

# Initialize one or more components
await initialize_components(component1, component2)

# Shutdown components
await shutdown_components(component1, component2)

# Wait for component completion
await wait_for_components(app)

# Runtime plugin management
register_plugin(api, plugin)
unregister_plugin(api, plugin)
```

### Container Interface

```python
from ioc import ContainerInterface

api: ContainerInterface

# Access components
app = api.provided_app()
libs = api.provided_libs()
plugins = api.provided_plugins()

# Access configuration
config = api.provided_config(MyConfigModel)

# Access logger
logger = api.provided_logger()
```

### Component Utilities

```python
from ioc import (
    as_component,
    component_requires,
    component_internals,
    component_str,
    compile_component
)

# Convert object to component
component = as_component(my_object)

# Get component dependencies
deps = component_requires(component, recursive=True)

# Access internal state
internals = component_internals(component)

# Load component from path
component = compile_component(Path("./my_component.py"))
```

## Configuration Files

### ioc.yaml

The main configuration file defines components and their settings:

```yaml
# Component definitions
app: path/to/app_module

libraries:
  database: path/to/database_lib
  cache: path/to/cache_lib

plugins:
  - path/to/plugin_a
  - path/to/plugin_b

# Component configuration (matches __prefix__ in config models)
database:
  host: localhost
  port: 5432
  name: production_db

cache:
  backend: redis
  ttl: 3600

app:
  debug: false
  workers: 4
```

### Environment Variables

Environment variables override file configuration:

```bash
# Set via environment
export DATABASE_HOST=production-db.example.com
export DATABASE_PORT=5432
export APP_DEBUG=false

# Or use context-specific .env files
# .production.env
DATABASE_HOST=production-db.example.com
APP_DEBUG=false
```

### Logging Configuration

Create a logging INI file for advanced logging:

```ini
[loggers]
keys = root,ioc,myapp

[handlers]
keys = console,file

[formatters]
keys = detailed

[logger_root]
level = INFO
handlers = console

[logger_ioc]
level = DEBUG
handlers = console,file
qualname = ioc

[logger_myapp]
level = DEBUG
handlers = console
qualname = myapp

[handler_console]
class = StreamHandler
level = DEBUG
formatter = detailed
args = (sys.stdout,)

[handler_file]
class = FileHandler
level = DEBUG
formatter = detailed
args = ('app.log', 'a')

[formatter_detailed]
format = %(asctime)s - %(name)s - %(levelname)s - %(message)s
```

## CLI Usage

The `awioc` command runs your application:

```bash
# Run with default settings
awioc

# Verbose output (INFO level)
awioc -v

# Debug output (DEBUG level)
awioc -vv

# Full debug including library logs
awioc -vvv

# Specify configuration file
IOC_CONFIG_PATH=./config/app.yaml

# Use environment context
IOC_CONTEXT=production

# Custom logging configuration
IOC_LOGGING_CONFIG=./logging.ini
```

## Testing

Run the test suite:

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=ioc --cov-report=html

# Run specific test module
pytest tests/ioc/test_container.py

# Run with verbose output
pytest -v
```

### Writing Tests

```python
import pytest
from ioc import create_container, as_component


@pytest.fixture
def container():
    return create_container()


@pytest.fixture
def sample_component():
    class TestComponent:
        __metadata__ = {
            "name": "test",
            "version": "1.0.0",
            "description": "Test component"
        }

        async def initialize(self):
            pass

        async def shutdown(self):
            pass

    return as_component(TestComponent())


async def test_component_initialization(container, sample_component):
    from ioc import initialize_components
    result = await initialize_components(sample_component)
    assert result is True
```

## Examples

### HTTP Server

See the complete example in `samples/http_server/`:

```python
# samples/http_server/__init__.py
import asyncio
from ioc import get_config, get_logger, inject
import pydantic


class ServerConfig(pydantic.BaseModel):
    __prefix__ = "server"
    host: str = "127.0.0.1"
    port: int = 8080


# Module-level metadata (required)
__metadata__ = {
    "name": "http_server_app",
    "version": "1.0.0",
    "description": "Simple HTTP Server",
    "wire": True,
    "config": ServerConfig
}


class HttpServerApp:

    @inject
    async def initialize(
            self,
            logger=get_logger(),
            config=get_config(ServerConfig)
    ) -> None:
        self.logger = logger
        self.config = config
        self.logger.info(f"Starting server on {config.host}:{config.port}")

    async def wait(self) -> None:
        while True:
            await asyncio.sleep(1)

    async def shutdown(self) -> None:
        self.logger.info("Server stopped")


# Export lifecycle methods at module level
http_server_app = HttpServerApp()
initialize = http_server_app.initialize
shutdown = http_server_app.shutdown
wait = http_server_app.wait
```

### Multi-Component Application

```python
# database_lib.py

# Module-level metadata (required)
__metadata__ = {
    "name": "database",
    "version": "1.0.0",
    "description": "Database connection library"
}

class DatabaseLibrary:

    async def initialize(self):
        self.pool = await create_pool()

    async def shutdown(self):
        await self.pool.close()

    async def query(self, sql):
        async with self.pool.acquire() as conn:
            return await conn.fetch(sql)

# Export lifecycle methods at module level
database = DatabaseLibrary()
initialize = database.initialize
shutdown = database.shutdown
```

```python
# app.py
from ioc import get_library, inject

# Module-level metadata (required)
__metadata__ = {
    "name": "my_app",
    "version": "1.0.0",
    "description": "Application with database",
    "requires": {database}
}

class MyApp:

    @inject
    async def initialize(self, db=get_library("database")):
        self.db = db
        users = await self.db.query("SELECT * FROM users")

# Export lifecycle methods at module level
my_app = MyApp()
initialize = my_app.initialize
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Links

- [GitHub Repository](https://github.com/pavalso/awioc)
- [Issue Tracker](https://github.com/pavalso/awioc/issues)
