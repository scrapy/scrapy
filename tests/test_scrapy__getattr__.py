import warnings


def test_deprecated_twisted_version():
    with warnings.catch_warnings(record=True) as warns:
        from scrapy import twisted_version  # pylint: disable=no-name-in-module

        assert twisted_version is not None
        assert isinstance(twisted_version, tuple)
        assert (
            "The scrapy.twisted_version attribute is deprecated, use twisted.version instead"
            in warns[0].message.args
        )
