from __future__ import annotations

from unittest.mock import Mock

import pytest

from scrapy.resolver import CachingHostnameResolver, CachingThreadedResolver, dnscache
from scrapy.utils.test import get_crawler


@pytest.fixture(autouse=True)
def reset_dnscache():
    original_limit = dnscache.limit
    dnscache.clear()
    yield
    dnscache.clear()
    dnscache.limit = original_limit


def test_caching_threaded_resolver_dnscache_disabled():
    crawler = get_crawler(settings_dict={"DNSCACHE_ENABLED": False})
    CachingThreadedResolver.from_crawler(crawler, Mock())
    assert dnscache.limit == 0


def test_caching_threaded_resolver_getHostByName_cache_hit():
    resolver = CachingThreadedResolver(Mock(), cache_size=10, timeout=5.0)
    dnscache["example.com"] = "1.2.3.4"

    result_deferred = resolver.getHostByName("example.com")
    results = []
    result_deferred.addCallback(results.append)
    assert results == ["1.2.3.4"]


def test_caching_hostname_resolver_dnscache_disabled():
    crawler = get_crawler(settings_dict={"DNSCACHE_ENABLED": False})
    CachingHostnameResolver.from_crawler(crawler, Mock())
    assert dnscache.limit == 0


def test_caching_hostname_resolver_no_addresses_not_cached():
    def fake_resolve(receiver, *_):
        receiver.resolutionBegan(Mock())
        receiver.resolutionComplete()
        return receiver

    reactor = Mock()
    reactor.nameResolver.resolveHostName.side_effect = fake_resolve

    resolver = CachingHostnameResolver(reactor, cache_size=10)
    resolver.resolveHostName(Mock(), "example.com")

    assert "example.com" not in dnscache
