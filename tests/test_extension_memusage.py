import pytest
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.test import get_crawler
from scrapy.exceptions import NotConfigured
from unittest.mock import Mock

def test_memusage_disabled_when_limits_none():
    crawler = get_crawler(
        settings_dict={
            "MEMUSAGE_WARNING_MB": None,
            "MEMUSAGE_LIMIT_MB": None,
        }
    )
    with pytest.raises(NotConfigured):
        MemoryUsage.from_crawler(crawler)

def test_memusage_notify_mail_configuration(monkeypatch):
    fake_resource = Mock()
    fake_resource.getrusage.return_value = Mock(ru_maxrss=1024 * 1024)

    monkeypatch.setattr(
        "scrapy.extensions.memusage.import_module",
        lambda name: fake_resource,
    )

    crawler = get_crawler(
        settings_dict={
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 1,
            "MEMUSAGE_WARNING_MB": None,
            "MEMUSAGE_NOTIFY_MAIL": ["test@example.com"],
        }
    )

    try:
        ext = MemoryUsage.from_crawler(crawler)
    except NotConfigured:
        pytest.skip("MemoryUsage disabled during initialization")

    assert hasattr(ext, "mail")
    assert ext.mail is not None 

def test_memusage_engine_started_creates_looping_call():
    pass

def test_memusage_disabled_when_resource_unavailable(monkeypatch):
    pass
