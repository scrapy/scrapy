from __future__ import annotations

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning


def test_deprecated_concurrent_requests_per_ip_attribute() -> None:
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"scrapy\.settings\.default_settings\.CONCURRENT_REQUESTS_PER_IP attribute is deprecated",
    ):
        from scrapy.settings.default_settings import (  # noqa: PLC0415
            CONCURRENT_REQUESTS_PER_IP,
        )

    assert CONCURRENT_REQUESTS_PER_IP is not None
    assert isinstance(CONCURRENT_REQUESTS_PER_IP, int)
