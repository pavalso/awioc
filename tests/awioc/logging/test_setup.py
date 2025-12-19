import logging

from src.awioc.config.setup import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default(self):
        """Test setup_logging with default parameters."""
        logger = setup_logging()

        assert isinstance(logger, logging.Logger)
        assert logger.level == logging.INFO

    def test_setup_logging_with_name(self):
        """Test setup_logging with specific name."""
        logger = setup_logging(name="test_logger")

        assert logger.name == "test_logger"

    def test_setup_logging_with_level(self):
        """Test setup_logging with specific level."""
        logger = setup_logging(name="level_test", level=logging.DEBUG)

        assert logger.level == logging.DEBUG

    def test_setup_logging_creates_handler(self):
        """Test setup_logging creates a handler."""
        # Use unique name to avoid handler accumulation
        logger = setup_logging(name="handler_test_unique")

        assert len(logger.handlers) >= 1

    def test_setup_logging_handler_is_stream(self):
        """Test setup_logging creates StreamHandler."""
        logger = setup_logging(name="stream_test_unique")

        # Find the StreamHandler
        stream_handlers = [
            h for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) >= 1

    def test_setup_logging_handler_has_formatter(self):
        """Test setup_logging handler has formatter."""
        logger = setup_logging(name="formatter_test_unique")

        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                assert handler.formatter is not None

    def test_setup_logging_does_not_duplicate_handlers(self):
        """Test setup_logging doesn't add duplicate handlers."""
        logger_name = "no_dup_test_unique"

        # First call
        logger1 = setup_logging(name=logger_name)
        handler_count1 = len(logger1.handlers)

        # Second call should not add more handlers
        logger2 = setup_logging(name=logger_name)
        handler_count2 = len(logger2.handlers)

        assert handler_count1 == handler_count2

    def test_setup_logging_returns_root_when_no_name(self):
        """Test setup_logging returns root logger when name is None."""
        logger = setup_logging(name=None)

        # Root logger has empty name
        assert logger.name == "root" or logger.name == ""

    def test_setup_logging_different_levels(self):
        """Test setup_logging with various log levels."""
        levels = [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL
        ]

        for level in levels:
            logger = setup_logging(name=f"level_{level}", level=level)
            assert logger.level == level

    def test_setup_logging_formatter_format(self):
        """Test the formatter contains expected fields."""
        logger = setup_logging(name="format_test_unique")

        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.formatter:
                fmt = handler.formatter._fmt
                assert "asctime" in fmt
                assert "name" in fmt
                assert "levelname" in fmt
                assert "message" in fmt
