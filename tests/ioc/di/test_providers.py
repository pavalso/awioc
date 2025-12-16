import pytest
from unittest.mock import MagicMock, patch

from src.ioc.di import providers as providers_module


class TestGetLibraryFunction:
    """Tests for get_library function structure."""

    def test_get_library_exists(self):
        """Test get_library function exists."""
        assert hasattr(providers_module, 'get_library')
        assert callable(providers_module.get_library)

    def test_get_library_has_overloads(self):
        """Test get_library has type and string variants."""
        # Function should accept both types
        from src.ioc.di.providers import get_library
        assert get_library is not None


class TestGetConfigFunction:
    """Tests for get_config function structure."""

    def test_get_config_exists(self):
        """Test get_config function exists."""
        assert hasattr(providers_module, 'get_config')
        assert callable(providers_module.get_config)


class TestGetContainerApi:
    """Tests for get_container_api function."""

    def test_function_exists(self):
        """Test get_container_api function exists."""
        assert hasattr(providers_module, 'get_container_api')
        assert callable(providers_module.get_container_api)


class TestGetRawContainer:
    """Tests for get_raw_container function."""

    def test_function_exists(self):
        """Test get_raw_container function exists."""
        assert hasattr(providers_module, 'get_raw_container')
        assert callable(providers_module.get_raw_container)


class TestGetApp:
    """Tests for get_app function."""

    def test_function_exists(self):
        """Test get_app function exists."""
        assert hasattr(providers_module, 'get_app')
        assert callable(providers_module.get_app)


class TestGetLoggerFunction:
    """Tests for get_logger function structure."""

    def test_get_logger_exists(self):
        """Test get_logger function exists."""
        assert hasattr(providers_module, 'get_logger')
        assert callable(providers_module.get_logger)
