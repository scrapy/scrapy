import warnings


def test_deprecated_concurrent_requests_per_ip_attribute():
    with warnings.catch_warnings(record=True) as warns:
        from scrapy.settings.default_settings import (  # noqa: PLC0415
            CONCURRENT_REQUESTS_PER_IP,
        )

        assert CONCURRENT_REQUESTS_PER_IP is not None
        assert isinstance(CONCURRENT_REQUESTS_PER_IP, int)
        assert (
            "The scrapy.settings.default_settings.CONCURRENT_REQUESTS_PER_IP attribute is deprecated, use scrapy.settings.default_settings.CONCURRENT_REQUESTS_PER_DOMAIN instead."
            in warns[0].message.args
        )
