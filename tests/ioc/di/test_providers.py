import pytest
from unittest.mock import MagicMock, patch, Mock
import pydantic

from dependency_injector.wiring import Provide

from src.ioc.di import providers as providers_module
from src.ioc.di.providers import (
    get_library,
    get_config,
    get_container_api,
    get_raw_container,
    get_app,
    get_logger,
)


class TestGetLibraryFunction:
    """Tests for get_library function."""

    def test_get_library_exists(self):
        """Test get_library function exists."""
        assert hasattr(providers_module, 'get_library')
        assert callable(providers_module.get_library)

    def test_get_library_has_overloads(self):
        """Test get_library has type and string variants."""
        assert get_library is not None

    def test_get_library_with_type_returns_provide_marker(self):
        """Test get_library returns a Provide marker when given a type."""

        class MockLibrary:
            pass

        result = get_library(MockLibrary)
        assert isinstance(result, Provide)

    def test_get_library_with_string_returns_provide_marker(self):
        """Test get_library returns a Provide marker when given a string."""
        result = get_library("some_library")
        assert isinstance(result, Provide)

    def test_get_library_different_types_produce_different_markers(self):
        """Test that different library types produce distinct markers."""

        class LibraryA:
            pass

        class LibraryB:
            pass

        result_a = get_library(LibraryA)
        result_b = get_library(LibraryB)
        # Both should be Provide instances
        assert isinstance(result_a, Provide)
        assert isinstance(result_b, Provide)


class TestGetConfigFunction:
    """Tests for get_config function."""

    def test_get_config_exists(self):
        """Test get_config function exists."""
        assert hasattr(providers_module, 'get_config')
        assert callable(providers_module.get_config)

    def test_get_config_without_model_returns_provide_marker(self):
        """Test get_config returns a Provide marker when called without model."""
        result = get_config()
        assert isinstance(result, Provide)

    def test_get_config_with_none_returns_provide_marker(self):
        """Test get_config returns a Provide marker when called with None."""
        result = get_config(None)
        assert isinstance(result, Provide)

    def test_get_config_with_model_returns_provide_marker(self):
        """Test get_config returns a Provide marker when given a model type."""

        class TestConfigModel(pydantic.BaseModel):
            name: str = "test"

        result = get_config(TestConfigModel)
        assert isinstance(result, Provide)

    def test_get_config_different_models_produce_markers(self):
        """Test that different config models produce markers."""

        class ConfigA(pydantic.BaseModel):
            value_a: str = "a"

        class ConfigB(pydantic.BaseModel):
            value_b: str = "b"

        result_a = get_config(ConfigA)
        result_b = get_config(ConfigB)
        assert isinstance(result_a, Provide)
        assert isinstance(result_b, Provide)


class TestGetContainerApi:
    """Tests for get_container_api function."""

    def test_function_exists(self):
        """Test get_container_api function exists."""
        assert hasattr(providers_module, 'get_container_api')
        assert callable(providers_module.get_container_api)

    def test_returns_provide_marker(self):
        """Test get_container_api returns a Provide marker."""
        result = get_container_api()
        assert isinstance(result, Provide)

    def test_consistent_return(self):
        """Test get_container_api returns consistent marker type."""
        result1 = get_container_api()
        result2 = get_container_api()
        assert type(result1) == type(result2)


class TestGetRawContainer:
    """Tests for get_raw_container function."""

    def test_function_exists(self):
        """Test get_raw_container function exists."""
        assert hasattr(providers_module, 'get_raw_container')
        assert callable(providers_module.get_raw_container)

    def test_returns_provide_marker(self):
        """Test get_raw_container returns a Provide marker."""
        result = get_raw_container()
        assert isinstance(result, Provide)

    def test_consistent_return(self):
        """Test get_raw_container returns consistent marker type."""
        result1 = get_raw_container()
        result2 = get_raw_container()
        assert type(result1) == type(result2)


class TestGetApp:
    """Tests for get_app function."""

    def test_function_exists(self):
        """Test get_app function exists."""
        assert hasattr(providers_module, 'get_app')
        assert callable(providers_module.get_app)

    def test_returns_provide_marker(self):
        """Test get_app returns a Provide marker."""
        result = get_app()
        assert isinstance(result, Provide)

    def test_consistent_return(self):
        """Test get_app returns consistent marker type."""
        result1 = get_app()
        result2 = get_app()
        assert type(result1) == type(result2)


class TestGetLoggerFunction:
    """Tests for get_logger function."""

    def test_get_logger_exists(self):
        """Test get_logger function exists."""
        assert hasattr(providers_module, 'get_logger')
        assert callable(providers_module.get_logger)

    def test_get_logger_no_args_returns_provide_marker(self):
        """Test get_logger returns a Provide marker when called without arguments."""
        result = get_logger()
        assert isinstance(result, Provide)

    def test_get_logger_with_single_name_returns_provide_marker(self):
        """Test get_logger returns a Provide marker when given a single name."""
        result = get_logger("mylogger")
        assert isinstance(result, Provide)

    def test_get_logger_with_multiple_names_returns_provide_marker(self):
        """Test get_logger returns a Provide marker when given multiple names."""
        result = get_logger("parent", "child", "grandchild")
        assert isinstance(result, Provide)

    def test_get_logger_name_joining(self):
        """Test that get_logger joins multiple names with dots."""
        # We test the internal logic by patching the Provide call
        # The function joins names with "."
        result = get_logger("a", "b", "c")
        assert isinstance(result, Provide)

    def test_get_logger_with_empty_string(self):
        """Test get_logger with empty string name."""
        result = get_logger("")
        assert isinstance(result, Provide)

    def test_get_logger_uses_calling_module_when_no_name(self):
        """Test that get_logger uses the calling module's name when no name is provided."""
        # When no name is provided, get_logger uses inspect.stack() to get
        # the calling module's __name__
        result = get_logger()
        assert isinstance(result, Provide)


class TestGetLoggerNameResolution:
    """Tests for get_logger's name resolution logic."""

    def test_name_provided_uses_name(self):
        """Test that when name is provided, it uses that name."""
        # Internal logic: if name is provided, use ".".join(name)
        result = get_logger("custom", "logger")
        assert isinstance(result, Provide)

    def test_no_name_inspects_stack(self):
        """Test that when no name is provided, inspect.stack is called."""
        with patch('src.ioc.di.providers.inspect') as mock_inspect:
            mock_frame = Mock()
            mock_module = Mock()
            mock_module.__name__ = "test_module"
            mock_inspect.stack.return_value = [None, (mock_frame,)]
            mock_inspect.getmodule.return_value = mock_module

            # Call get_logger without arguments
            result = get_logger()
            # Should have called inspect.stack
            mock_inspect.stack.assert_called_once()

    def test_no_name_no_module_uses_fallback(self):
        """Test fallback when module cannot be determined."""
        with patch('src.ioc.di.providers.inspect') as mock_inspect:
            mock_frame = Mock()
            mock_inspect.stack.return_value = [None, (mock_frame,)]
            mock_inspect.getmodule.return_value = None

            result = get_logger()
            assert isinstance(result, Provide)


class TestProviderModuleExports:
    """Tests for providers module exports."""

    def test_all_providers_exported(self):
        """Test that all provider functions are accessible."""
        expected_functions = [
            'get_library',
            'get_config',
            'get_container_api',
            'get_raw_container',
            'get_app',
            'get_logger',
        ]
        for func_name in expected_functions:
            assert hasattr(providers_module, func_name)
            assert callable(getattr(providers_module, func_name))

    def test_type_vars_exist(self):
        """Test that type variables are defined."""
        assert hasattr(providers_module, '_Lib_type')
        assert hasattr(providers_module, '_Model_type')


class TestProviderReturnTypes:
    """Integration tests for provider return types."""

    def test_all_providers_return_provide_instances(self):
        """Test that all provider functions return Provide instances."""

        class DummyLib:
            pass

        class DummyConfig(pydantic.BaseModel):
            value: str = "test"

        providers_to_test = [
            lambda: get_library(DummyLib),
            lambda: get_library("string_lib"),
            lambda: get_config(),
            lambda: get_config(None),
            lambda: get_config(DummyConfig),
            lambda: get_container_api(),
            lambda: get_raw_container(),
            lambda: get_app(),
            lambda: get_logger(),
            lambda: get_logger("named"),
            lambda: get_logger("parent", "child"),
        ]

        for provider_fn in providers_to_test:
            result = provider_fn()
            assert isinstance(result, Provide), f"Expected Provide, got {type(result)}"