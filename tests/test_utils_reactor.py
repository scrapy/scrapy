import asyncio

import pytest

from scrapy.utils.reactor import (
    _asyncio_reactor_path,
    install_reactor,
    is_asyncio_reactor_installed,
    set_asyncio_event_loop,
)
from tests.utils.decorators import coroutine_test


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
