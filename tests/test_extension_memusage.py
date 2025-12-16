import pytest
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler
from scrapy.exceptions import NotConfigured

def test_memusage_disabled_when_limits_none():
    crawler = get_crawler(
        settings_dict={
            "MEMUSAGE_WARNING_MB": None,
            "MEMUSAGE_LIMIT_MB": None,
        }
    )
    with pytest.raises(NotConfigured):
        MemoryUsage.from_crawler(crawler)


def test_memusage_sends_mail_when_notify_enabled():
    pass

def test_memusage_engine_started_creates_looping_call():
    pass

def test_memusage_disabled_when_resource_unavailable(monkeypatch):
    pass
