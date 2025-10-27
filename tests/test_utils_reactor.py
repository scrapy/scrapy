import asyncio
import warnings

import pytest

from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.reactor import (
    _asyncio_reactor_path,
    install_reactor,
    is_asyncio_reactor_installed,
    set_asyncio_event_loop,
)


class TestAsyncio:
    def test_is_asyncio_reactor_installed(self, reactor_pytest: str) -> None:
        # the result should depend only on the pytest --reactor argument
        assert is_asyncio_reactor_installed() == (reactor_pytest == "asyncio")

    def test_install_asyncio_reactor(self):
        from twisted.internet import reactor as original_reactor

        with warnings.catch_warnings(record=True) as w:
            install_reactor(_asyncio_reactor_path)
            assert len(w) == 0, [str(warning) for warning in w]
        from twisted.internet import reactor  # pylint: disable=reimported

        assert original_reactor == reactor

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_set_asyncio_event_loop(self):
        install_reactor(_asyncio_reactor_path)
        assert set_asyncio_event_loop(None) is asyncio.get_running_loop()
