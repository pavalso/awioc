import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_yaml_config(temp_dir):
    """Create a sample YAML config file."""
    config_path = temp_dir / "config.yaml"
    config_path.write_text("""
app: ./app
libraries:
  db: ./libs/db
  cache: ./libs/cache
plugins:
  - ./plugins/auth
  - ./plugins/logging
""")
    return config_path


@pytest.fixture
def sample_json_config(temp_dir):
    """Create a sample JSON config file."""
    config_path = temp_dir / "config.json"
    config_path.write_text("""{
    "app": "./app",
    "libraries": {
        "db": "./libs/db"
    },
    "plugins": ["./plugins/auth"]
}""")
    return config_path


@pytest.fixture
def empty_config_file(temp_dir):
    """Create an empty config file."""
    config_path = temp_dir / "empty.yaml"
    config_path.write_text("")
    return config_path


@pytest.fixture
def sample_component_module(temp_dir):
    """Create a sample component module file with .awioc/manifest.yaml."""
    import yaml

    module_path = temp_dir / "sample_component.py"
    module_path.write_text("""
async def initialize():
    return True

async def shutdown():
    pass

async def wait():
    pass
""")

    # Create .awioc/manifest.yaml
    awioc_dir = temp_dir / ".awioc"
    awioc_dir.mkdir()
    manifest = {
        "manifest_version": "1.0",
        "components": [
            {
                "name": "sample_component",
                "version": "1.0.0",
                "description": "A sample component for testing",
                "file": "sample_component.py",
                "wire": True,
            }
        ],
    }
    (awioc_dir / "manifest.yaml").write_text(yaml.dump(manifest))

    return module_path


@pytest.fixture
def sample_component_package(temp_dir):
    """Create a sample component package directory with .awioc/manifest.yaml."""
    import yaml

    pkg_dir = temp_dir / "sample_package"
    pkg_dir.mkdir()
    init_path = pkg_dir / "__init__.py"
    init_path.write_text("""
initialize = None
shutdown = None
wait = None
""")

    # Create .awioc/manifest.yaml inside the package
    awioc_dir = pkg_dir / ".awioc"
    awioc_dir.mkdir()
    manifest = {
        "manifest_version": "1.0",
        "components": [
            {
                "name": "sample_package",
                "version": "2.0.0",
                "description": "A sample package component",
                "file": "__init__.py",
                "wire": False,
            }
        ],
    }
    (awioc_dir / "manifest.yaml").write_text(yaml.dump(manifest))

    return pkg_dir


@pytest.fixture
def sample_app_module(temp_dir):
    """Create a sample app module for testing with .awioc/manifest.yaml."""
    import yaml

    module_path = temp_dir / "app.py"
    module_path.write_text("""
from src.awioc.config import Settings

class AppConfig(Settings):
    app_name: str = "test_app"

async def initialize():
    return True

async def shutdown():
    pass

async def wait():
    pass
""")

    # Create .awioc/manifest.yaml
    awioc_dir = temp_dir / ".awioc"
    awioc_dir.mkdir(exist_ok=True)
    manifest = {
        "manifest_version": "1.0",
        "components": [
            {
                "name": "test_app",
                "version": "1.0.0",
                "description": "Test application",
                "file": "app.py",
                "wire": True,
            }
        ],
    }
    (awioc_dir / "manifest.yaml").write_text(yaml.dump(manifest))

    return module_path


@pytest.fixture(autouse=True)
def clean_configurations():
    """Clean configurations before and after each test."""
    from src.awioc.config.registry import clear_configurations
    clear_configurations()
    yield
    clear_configurations()


@pytest.fixture
def reset_sys_modules():
    """Reset sys.modules for module loader tests."""
    original_modules = set(sys.modules.keys())
    yield
    # Remove any modules added during the test
    new_modules = set(sys.modules.keys()) - original_modules
    for mod in new_modules:
        if not mod.startswith(('pytest', '_pytest', 'pluggy')):
            sys.modules.pop(mod, None)
