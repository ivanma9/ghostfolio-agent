import json
import logging
import structlog
import pytest
from ghostfolio_agent.logging_config import configure_logging, get_request_id, set_request_id


class TestConfigureLogging:
    def test_configure_json_format(self):
        configure_logging(log_level="info", log_format="json")
        logger = structlog.get_logger("test_json")
        logger.info("test_event", key="value")

    def test_configure_console_format(self):
        configure_logging(log_level="debug", log_format="console")
        logger = structlog.get_logger("test_console")
        logger.info("test_event", key="value")

    def test_log_level_applied(self):
        configure_logging(log_level="warning", log_format="json")
        root = logging.getLogger()
        assert root.level == logging.WARNING


class TestRequestId:
    def test_set_and_get_request_id(self):
        set_request_id("test-123")
        assert get_request_id() == "test-123"

    def test_default_request_id_is_none(self):
        set_request_id("")
        assert get_request_id() == ""
