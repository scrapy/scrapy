from __future__ import annotations

import socket
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from twisted.conch.telnet import ITelnetProtocol
from twisted.cred import credentials

from scrapy import Spider
from scrapy.extensions.telnet import TelnetConsole, update_telnet_vars
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.crawler import Crawler
    from scrapy.http import Response

pytestmark = pytest.mark.requires_reactor  # TelnetConsole requires a reactor


def _get_crawler(
    spidercls: type[Spider] | None = None,
    settings_dict: dict[str, Any] | None = None,
) -> Crawler:
    settings = {
        "TELNETCONSOLE_ENABLED": True,
        **(settings_dict or {}),
    }
    return get_crawler(spidercls, settings_dict=settings)


@contextmanager
def _get_console_and_portal(
    settings: dict[str, Any] | None = None,
) -> Generator[tuple[TelnetConsole, Any]]:
    crawler = _get_crawler(settings_dict=settings)
    console = TelnetConsole(crawler)

    # This function has some side effects we don't need for this test
    console._get_telnet_vars = dict  # type: ignore[method-assign]

    console.start_listening()
    protocol = console.protocol()
    portal = protocol.protocolArgs[0]

    try:
        yield console, portal
    finally:
        console.stop_listening()


@coroutine_test
async def test_bad_credentials() -> None:
    with _get_console_and_portal() as (_, portal):
        creds = credentials.UsernamePassword(b"username", b"password")
        d = portal.login(creds, None, ITelnetProtocol)
        with pytest.raises(ValueError, match="Invalid credentials"):
            await maybe_deferred_to_future(d)


@coroutine_test
async def test_good_credentials() -> None:
    with _get_console_and_portal() as (console, portal):
        creds = credentials.UsernamePassword(
            console.username.encode("utf8"), console.password.encode("utf8")
        )
        d = portal.login(creds, None, ITelnetProtocol)
        await maybe_deferred_to_future(d)


@coroutine_test
async def test_custom_credentials() -> None:
    settings = {
        "TELNETCONSOLE_USERNAME": "user",
        "TELNETCONSOLE_PASSWORD": "pass",
    }
    with _get_console_and_portal(settings=settings) as (_, portal):
        creds = credentials.UsernamePassword(b"user", b"pass")
        d = portal.login(creds, None, ITelnetProtocol)
        await maybe_deferred_to_future(d)


def test_invalid_reversed_portrange() -> None:
    settings = {"TELNETCONSOLE_PORT": [2, 1]}
    console = TelnetConsole(_get_crawler(settings_dict=settings))
    with pytest.raises(ValueError, match=r"invalid portrange: \[2, 1\]"):
        console.start_listening()


@coroutine_test
async def test_unavailable_port(caplog: pytest.LogCaptureFixture) -> None:
    """Run a crawl where the console cannot bind any port."""
    with socket.create_server(("127.0.0.1", 0)) as sock:
        port = sock.getsockname()[1]
        crawler = _get_crawler(settings_dict={"TELNETCONSOLE_PORT": [port]})
        await crawler.crawl_async()

    assert "CannotListenError" in caplog.text
    assert "AttributeError" not in caplog.text


@coroutine_test
async def test_telnet_vars() -> None:
    """Log into the console of a running crawl, which is when the telnet
    variables are built."""
    received: list[dict[str, Any]] = []

    def on_update_telnet_vars(telnet_vars: dict[str, Any]) -> None:
        received.append(telnet_vars)

    class TelnetSpider(Spider):
        name = "telnet"
        start_urls = ["data:,"]

        async def parse(self, response: Response) -> None:
            assert self.crawler.extensions
            console = next(
                ext
                for ext in self.crawler.extensions.middlewares
                if isinstance(ext, TelnetConsole)
            )
            creds = credentials.UsernamePassword(
                console.username.encode("utf8"), console.password.encode("utf8")
            )
            portal = console.protocol().protocolArgs[0]
            await maybe_deferred_to_future(portal.login(creds, None, ITelnetProtocol))

    crawler = _get_crawler(TelnetSpider)
    crawler.signals.connect(on_update_telnet_vars, signal=update_telnet_vars)
    await crawler.crawl_async()

    assert len(received) == 1
    telnet_vars = received[0]
    assert telnet_vars["crawler"] is crawler
    assert telnet_vars["engine"] is crawler.engine
    assert telnet_vars["spider"] is crawler.spider
    assert telnet_vars["extensions"] is crawler.extensions
    assert telnet_vars["stats"] is crawler.stats
    assert telnet_vars["settings"] is crawler.settings
    assert callable(telnet_vars["est"])
    assert callable(telnet_vars["p"])
    assert callable(telnet_vars["prefs"])
    assert "telnetconsole.html" in telnet_vars["help"]
