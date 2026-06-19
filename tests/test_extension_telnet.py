from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from twisted.conch.telnet import ITelnetProtocol
from twisted.cred import credentials

from scrapy.extensions.telnet import TelnetConsole
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.crawler import Crawler

pytestmark = pytest.mark.requires_reactor  # TelnetConsole requires a reactor


def _get_crawler(settings_dict: dict[str, Any] | None = None) -> Crawler:
    settings = {
        "TELNETCONSOLE_ENABLED": True,
        **(settings_dict or {}),
    }
    return get_crawler(settings_dict=settings)


def _get_console_and_portal(
    settings: dict[str, Any] | None = None,
) -> tuple[TelnetConsole, Any]:
    crawler = _get_crawler(settings_dict=settings)
    console = TelnetConsole(crawler)

    # This function has some side effects we don't need for this test
    console._get_telnet_vars = dict

    console.start_listening()
    protocol = console.protocol()
    portal = protocol.protocolArgs[0]

    return console, portal


@coroutine_test
async def test_bad_credentials() -> None:
    console, portal = _get_console_and_portal()
    creds = credentials.UsernamePassword(b"username", b"password")
    d = portal.login(creds, None, ITelnetProtocol)
    with pytest.raises(ValueError, match="Invalid credentials"):
        await maybe_deferred_to_future(d)
    console.stop_listening()


@coroutine_test
async def test_good_credentials() -> None:
    console, portal = _get_console_and_portal()
    creds = credentials.UsernamePassword(
        console.username.encode("utf8"), console.password.encode("utf8")
    )
    d = portal.login(creds, None, ITelnetProtocol)
    await maybe_deferred_to_future(d)
    console.stop_listening()


@coroutine_test
async def test_custom_credentials() -> None:
    settings = {
        "TELNETCONSOLE_USERNAME": "user",
        "TELNETCONSOLE_PASSWORD": "pass",
    }
    console, portal = _get_console_and_portal(settings=settings)
    creds = credentials.UsernamePassword(b"user", b"pass")
    d = portal.login(creds, None, ITelnetProtocol)
    await maybe_deferred_to_future(d)
    console.stop_listening()


def test_invalid_reversed_portrange() -> None:
    settings = {"TELNETCONSOLE_PORT": [2, 1]}
    console = TelnetConsole(_get_crawler(settings_dict=settings))
    with pytest.raises(ValueError, match=r"invalid portrange: \[2, 1\]"):
        console.start_listening()
