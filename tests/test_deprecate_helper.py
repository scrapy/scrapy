import warnings

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import get_spider_attr


def test_get_spider_attr_deprecated_uppercase_used():
    class S:
        DOWNLOAD_TIMEOUT = 5

    s = S()
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        val = get_spider_attr(s, "download_timeout", 10, "DOWNLOAD_TIMEOUT")
        assert val == 5
        assert any(isinstance(w.category, type) and issubclass(w.category, ScrapyDeprecationWarning.__class__) for w in rec) or any(
            "DOWNLOAD_TIMEOUT" in str(w.message) for w in rec
        )


def test_get_spider_attr_prefers_lowercase_no_warning():
    class S:
        download_timeout = 7
        DOWNLOAD_TIMEOUT = 5

    s = S()
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        val = get_spider_attr(s, "download_timeout", 10, "DOWNLOAD_TIMEOUT")
        assert val == 7
        # No ScrapyDeprecationWarning should be raised because lowercase is preferred
        assert not any("DOWNLOAD_TIMEOUT" in str(w.message) for w in rec)


def test_get_spider_attr_default_used():
    class S:
        pass

    s = S()
    val = get_spider_attr(s, "download_timeout", 10, "DOWNLOAD_TIMEOUT")
    assert val == 10
