from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import pytest
from twisted.internet.error import CannotListenError
from twisted.internet.protocol import ServerFactory

from scrapy.utils.reactor import (
    _asyncio_reactor_path,
    install_reactor,
    is_asyncio_reactor_installed,
    listen_tcp,
    set_asyncio_event_loop,
    verify_installed_asyncio_event_loop,
    verify_installed_reactor,
)
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import Generator

    from twisted.internet.tcp import Port


class TestAsyncio:
    @pytest.mark.requires_reactor  # needs a reactor
    def test_is_asyncio_reactor_installed(self, reactor_pytest: str) -> None:
        # the result should depend only on the pytest --reactor argument
        assert is_asyncio_reactor_installed() == (reactor_pytest == "asyncio")

    @pytest.mark.requires_reactor  # installs a reactor
    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_set_asyncio_event_loop(self):
        install_reactor(_asyncio_reactor_path)
        assert set_asyncio_event_loop(None) is asyncio.get_running_loop()


class TestVerifyWithoutReactor:
    @pytest.fixture(autouse=True)
    def no_reactor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delitem(sys.modules, "twisted.internet.reactor", raising=False)

    def test_verify_installed_reactor(self) -> None:
        with pytest.raises(
            RuntimeError, match=r"verify_installed_reactor\(\) called without"
        ):
            verify_installed_reactor(_asyncio_reactor_path)

    def test_verify_installed_asyncio_event_loop(self) -> None:
        with pytest.raises(
            RuntimeError,
            match=r"verify_installed_asyncio_event_loop\(\) called without",
        ):
            verify_installed_asyncio_event_loop("asyncio.SelectorEventLoop")


@pytest.mark.requires_reactor  # needs a reactor
class TestListenTcp:
    @pytest.fixture
    def ports(self) -> Generator[list[Port]]:
        opened: list[Port] = []
        yield opened
        for port in opened:
            port.stopListening()

    @pytest.mark.parametrize("portrange", [[1, 2, 3], [8000, 7000]])
    def test_invalid_portrange(self, portrange: list[int]) -> None:
        with pytest.raises(ValueError, match="invalid portrange"):
            listen_tcp(portrange, "127.0.0.1", ServerFactory())

    def test_empty_portrange(self, ports: list[Port]) -> None:
        port = listen_tcp([], "127.0.0.1", ServerFactory())
        ports.append(port)
        assert port.getHost().port > 0

    def test_single_port(self, ports: list[Port]) -> None:
        port = listen_tcp([0], "127.0.0.1", ServerFactory())
        ports.append(port)
        assert port.getHost().port > 0

    def test_skips_used_ports(self, ports: list[Port]) -> None:
        used = listen_tcp([], "127.0.0.1", ServerFactory())
        ports.append(used)
        used_number = used.getHost().port

        port = listen_tcp([used_number, used_number + 50], "127.0.0.1", ServerFactory())
        ports.append(port)
        assert used_number < port.getHost().port <= used_number + 50

    def test_no_free_port(self, ports: list[Port]) -> None:
        used = listen_tcp([], "127.0.0.1", ServerFactory())
        ports.append(used)
        used_number = used.getHost().port

        with pytest.raises(CannotListenError):
            listen_tcp([used_number, used_number], "127.0.0.1", ServerFactory())
