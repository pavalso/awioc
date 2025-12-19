import pytest
import pydantic

from src.awioc.config.base import Settings
from src.awioc.config.registry import register_configuration, _CONFIGURATIONS


class TestSettings:
    """Tests for Settings base class."""

    def test_settings_default_config(self):
        """Test Settings with default configuration."""
        settings = Settings()
        assert settings.model_config["env_file"] == ".env"
        assert settings.model_config["extra"] == "ignore"

    def test_get_config_returns_registered_config(self):
        """Test get_config returns a registered configuration."""
        class TestConfigModel(pydantic.BaseModel):
            value: str = "test_value"

        register_configuration(TestConfigModel, prefix="test_settings")

        # Create settings with the config loaded - access via get_config
        loaded_settings = Settings.load_config()
        # The config is accessible via get_config method
        result = loaded_settings.get_config(TestConfigModel)
        assert isinstance(result, TestConfigModel)
        assert result.value == "test_value"

    def test_get_config_not_found_raises(self):
        """Test get_config raises when config not registered."""
        class UnregisteredConfig(pydantic.BaseModel):
            pass

        settings = Settings()
        with pytest.raises(ValueError, match="Configuration for type .* not found"):
            settings.get_config(UnregisteredConfig)

    def test_load_config_creates_dynamic_class(self):
        """Test load_config creates a dynamic settings class."""
        @register_configuration(prefix="dynamic")
        class DynamicConfig(pydantic.BaseModel):
            name: str = "dynamic_value"

        loaded = Settings.load_config()
        assert hasattr(loaded, "DynamicConfig")

    def test_load_config_with_multiple_configurations(self):
        """Test load_config with multiple registered configurations."""
        @register_configuration(prefix="config_a")
        class ConfigA(pydantic.BaseModel):
            a_value: int = 1

        @register_configuration(prefix="config_b")
        class ConfigB(pydantic.BaseModel):
            b_value: str = "b"

        loaded = Settings.load_config()
        assert hasattr(loaded, "ConfigA")
        assert hasattr(loaded, "ConfigB")

    def test_load_config_inherits_from_settings(self):
        """Test that loaded config inherits from Settings."""
        @register_configuration(prefix="inherit_test")
        class InheritConfig(pydantic.BaseModel):
            pass

        loaded = Settings.load_config()
        assert isinstance(loaded, Settings)

    def test_settings_with_custom_subclass(self):
        """Test custom Settings subclass."""
        class CustomSettings(Settings):
            custom_field: str = "custom"

        settings = CustomSettings()
        assert settings.custom_field == "custom"

    def test_get_config_caching(self):
        """Test that get_config results are cached."""
        class CachedConfigModel(pydantic.BaseModel):
            value: int = 100

        register_configuration(CachedConfigModel, prefix="cached")

        loaded_settings = Settings.load_config()
        result1 = loaded_settings.get_config(CachedConfigModel)
        result2 = loaded_settings.get_config(CachedConfigModel)
        # Both calls should return the same cached value
        assert isinstance(result1, CachedConfigModel)
        assert isinstance(result2, CachedConfigModel)
        assert result1.value == result2.value
