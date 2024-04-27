import logging
from typing import Dict, Optional

import pytest

from scrapy.utils.spider_logger_adapter import SpiderLoggerAdapter


@pytest.mark.parametrize(
    ("base_extra", "log_extra", "expected_extra"),
    (
        (
            {"spider": "test"},
            {"extra": {"log_extra": "info"}},
            {"extra": {"log_extra": "info", "spider": "test"}},
        ),
        ({"spider": "test"}, {"extra": None}, {"extra": {"spider": "test"}}),
        (None, {"extra": {"log_extra": "info"}}, {"extra": {"log_extra": "info"}}),
        (None, {"extra": None}, {"extra": None}),
        (
            {"spider": "test"},
            {"extra": {"spider": "test2"}},
            {"extra": {"spider": "test"}},
        ),
    ),
)
def test_spider_logger_adapter_process(
    base_extra: Optional[Dict], log_extra: Dict, expected_extra: Dict
):
    logger = logging.getLogger("test")
    spider_logger_adapter = SpiderLoggerAdapter(logger, base_extra)

    log_message = "test_log_message"
    result_message, result_kwargs = spider_logger_adapter.process(
        log_message, log_extra
    )

    assert result_message == log_message
    assert result_kwargs == expected_extra
