from __future__ import annotations

from unittest.mock import Mock

import pytest
from twisted.internet.address import IPv4Address, IPv6Address

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


def test_caching_hostname_resolver_cache_hit_uses_requested_port():
    dnscache["example.com"] = [
        IPv4Address("TCP", "1.2.3.4", 80),
        IPv6Address("TCP", "::1", 80),
    ]

    receiver = Mock()
    resolver = CachingHostnameResolver(Mock(), cache_size=10)
    resolver.resolveHostName(receiver, "example.com", portNumber=443)

    resolved_ports = [
        call.args[0].port for call in receiver.addressResolved.call_args_list
    ]
    assert resolved_ports == [443, 443]
    # The cached addresses must not be mutated in place.
    assert [addr.port for addr in dnscache["example.com"]] == [80, 80]


def test_caching_hostname_resolver_dnscache_disabled_rejects_storage():

    def fake_resolve(receiver, *_):
        receiver.resolutionBegan(Mock())
        receiver.addressResolved(Mock())
        receiver.resolutionComplete()
        return receiver

    reactor = Mock()
    reactor.nameResolver.resolveHostName.side_effect = fake_resolve

    resolver = CachingHostnameResolver(reactor, cache_size=0)
    resolver.resolveHostName(Mock(), "example.com")

    assert "example.com" not in dnscache
    assert len(dnscache) == 0
