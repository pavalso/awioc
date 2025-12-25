import pydantic
import pytest

from src.awioc.config.registry import (
    _CONFIGURATIONS,
    register_configuration,
    clear_configurations,
)


class TestConfigurationRegistry:
    """Tests for configuration registry functions."""

    def test_register_configuration_with_decorator(self):
        """Test registering a configuration using decorator syntax."""
        @register_configuration(prefix="test")
        class TestConfig(pydantic.BaseModel):
            value: str = "default"

        assert "test" in _CONFIGURATIONS
        assert _CONFIGURATIONS["test"] == TestConfig

    def test_register_configuration_with_explicit_prefix(self):
        """Test registering with an explicit prefix."""
        @register_configuration(prefix="custom_prefix")
        class CustomConfig(pydantic.BaseModel):
            name: str = "custom"

        assert "custom_prefix" in _CONFIGURATIONS

    def test_register_configuration_normalizes_prefix(self):
        """Test that prefix is normalized (lowercase, underscores)."""
        @register_configuration(prefix="  TEST_PREFIX  ")
        class NormalizedConfig(pydantic.BaseModel):
            pass

        assert "test_prefix" in _CONFIGURATIONS

    def test_register_configuration_collision_raises(self):
        """Test that duplicate prefix raises ValueError."""
        @register_configuration(prefix="duplicate")
        class FirstConfig(pydantic.BaseModel):
            pass

        with pytest.raises(ValueError, match="Configuration prefix collision"):
            @register_configuration(prefix="duplicate")
            class SecondConfig(pydantic.BaseModel):
                pass

    def test_register_configuration_direct_call(self):
        """Test registering configuration with direct call."""
        class DirectConfig(pydantic.BaseModel):
            setting: int = 42

        registered = register_configuration(DirectConfig, prefix="direct")
        assert registered == DirectConfig
        assert "direct" in _CONFIGURATIONS

    def test_clear_configurations(self):
        """Test clearing all configurations."""
        @register_configuration(prefix="to_clear")
        class ToClearConfig(pydantic.BaseModel):
            pass

        assert len(_CONFIGURATIONS) > 0
        clear_configurations()
        assert len(_CONFIGURATIONS) == 0

    def test_register_non_basemodel_raises(self):
        """Test that non-BaseModel classes raise assertion error."""
        with pytest.raises(AssertionError):
            @register_configuration(prefix="invalid")
            class NotAModel:
                pass

    def test_register_configuration_auto_prefix_from_module(self):
        """Test auto-generated prefix from module name."""
        @register_configuration
        class AutoPrefixConfig(pydantic.BaseModel):
            value: str = "auto"

        # Should use the test module name as prefix
        assert any("test" in key for key in _CONFIGURATIONS.keys())


class TestClearConfigurationsSpecific:
    """Tests for clear_configurations with specific prefixes."""

    def test_clear_specific_prefix(self):
        """Test clearing a specific configuration prefix."""

        @register_configuration(prefix="specific_a")
        class SpecificA(pydantic.BaseModel):
            pass

        @register_configuration(prefix="specific_b")
        class SpecificB(pydantic.BaseModel):
            pass

        assert "specific_a" in _CONFIGURATIONS
        assert "specific_b" in _CONFIGURATIONS

        # Clear only specific_a
        clear_configurations(prefixes=["specific_a"])

        assert "specific_a" not in _CONFIGURATIONS
        assert "specific_b" in _CONFIGURATIONS

        # Cleanup
        clear_configurations()

    def test_clear_multiple_specific_prefixes(self):
        """Test clearing multiple specific prefixes."""

        @register_configuration(prefix="multi_a")
        class MultiA(pydantic.BaseModel):
            pass

        @register_configuration(prefix="multi_b")
        class MultiB(pydantic.BaseModel):
            pass

        @register_configuration(prefix="multi_c")
        class MultiC(pydantic.BaseModel):
            pass

        # Clear a and b but not c
        clear_configurations(prefixes=["multi_a", "multi_b"])

        assert "multi_a" not in _CONFIGURATIONS
        assert "multi_b" not in _CONFIGURATIONS
        assert "multi_c" in _CONFIGURATIONS

        # Cleanup
        clear_configurations()

    def test_clear_nonexistent_prefix(self):
        """Test clearing a prefix that doesn't exist doesn't raise."""
        # Should not raise
        clear_configurations(prefixes=["nonexistent_prefix"])
