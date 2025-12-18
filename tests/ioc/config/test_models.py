from pathlib import Path

import pytest
from src.ioc.config.models import IOCComponentsDefinition, IOCBaseConfig


class TestIOCComponentsDefinition:
    """Tests for IOCComponentsDefinition model."""

    def test_minimal_definition(self):
        """Test minimal valid definition."""
        definition = IOCComponentsDefinition(app=Path("./app"))
        assert definition.app == Path("./app")
        assert definition.libraries == {}
        assert definition.plugins == []

    def test_full_definition(self):
        """Test definition with all fields."""
        definition = IOCComponentsDefinition(
            app=Path("./app"),
            libraries={"db": Path("./libs/db"), "cache": Path("./libs/cache")},
            plugins=[Path("./plugins/auth"), Path("./plugins/logging")]
        )
        assert definition.app == Path("./app")
        assert len(definition.libraries) == 2
        assert len(definition.plugins) == 2

    def test_definition_from_dict(self):
        """Test creating definition from dictionary."""
        data = {
            "app": "./app",
            "libraries": {"db": "./db"},
            "plugins": ["./plugin1"]
        }
        definition = IOCComponentsDefinition.model_validate(data)
        assert definition.app == Path("./app")

    def test_definition_requires_app(self):
        """Test that app is required."""
        with pytest.raises(Exception):  # ValidationError
            IOCComponentsDefinition()


class TestIOCBaseConfig:
    """Tests for IOCBaseConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = IOCBaseConfig()
        assert config.config_path == Path("ioc.yaml")
        assert config.context is None

    def test_with_config_path(self, temp_dir):
        """Test setting config_path."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("")

        config = IOCBaseConfig(config_path=str(config_file))
        assert config.config_path == config_file

    def test_with_context(self):
        """Test setting context."""
        config = IOCBaseConfig(context="development")
        assert config.context == "development"

    def test_config_path_expansion(self, temp_dir, monkeypatch):
        """Test that config_path expands environment variables."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("")
        monkeypatch.setenv("TEST_CONFIG_DIR", str(temp_dir))

        # Test with environment variable in path
        config = IOCBaseConfig(config_path=f"{temp_dir}/config.yaml")
        assert config.config_path is not None

    def test_inherits_from_settings(self):
        """Test that IOCBaseConfig inherits from Settings."""
        from src.ioc.config.base import Settings
        config = IOCBaseConfig()
        assert isinstance(config, Settings)
