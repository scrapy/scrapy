import warnings


def test_deprecated_twisted_version():
    with warnings.catch_warnings(record=True) as warns:
        from scrapy import (  # noqa: PLC0415  # pylint: disable=no-name-in-module
            twisted_version,
        )

        assert twisted_version is not None
        assert isinstance(twisted_version, tuple)
        assert (
            "The scrapy.twisted_version attribute is deprecated, use twisted.version instead"
            in warns[0].message.args
        )


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
