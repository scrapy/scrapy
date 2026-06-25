from __future__ import annotations

from unittest.mock import Mock

import pytest

from scrapy.resolver import CachingHostnameResolver, CachingThreadedResolver, dnscache
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test


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


@coroutine_test
async def test_caching_threaded_resolver_getHostByName_cache_hit():
    resolver = CachingThreadedResolver(Mock(), cache_size=10, timeout=5.0)
    dnscache["example.com"] = "1.2.3.4"

    result = await maybe_deferred_to_future(resolver.getHostByName("example.com"))
    assert result == "1.2.3.4"


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


def test_caching_hostname_resolver_dnscache_disabled_rejects_storage():
    # Regression test for LocalCache(limit=0) rejecting storage
    # when DNSCACHE_ENABLED=False. _CachingResolutionReceiver writes
    # directly to dnscache, so we verify nothing is stored.
    def fake_resolve(receiver, *_):
        receiver.resolutionBegan(Mock())
        receiver.addressResolved(Mock())
        receiver.resolutionComplete()
        return receiver

    reactor = Mock()
    reactor.nameResolver.resolveHostName.side_effect = fake_resolve

    # cache_size=0 simulates DNSCACHE_ENABLED=False
    resolver = CachingHostnameResolver(reactor, cache_size=0)
    resolver.resolveHostName(Mock(), "example.com")

    # dnscache should remain empty despite address being resolved
    assert "example.com" not in dnscache
    assert len(dnscache) == 0


def test_caching_threaded_resolver_dnscache_disabled_rejects_storage():
    # Regression test: when DNSCACHE_ENABLED=False, resolved DNS results
    # should not be stored in dnscache even after successful resolution.
    dnscache.limit = 0
    dnscache["example.com"] = "1.2.3.4"
    assert "example.com" not in dnscache
    assert len(dnscache) == 0
