import asyncio
import warnings

import pytest
from twisted.trial.unittest import TestCase

from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.reactor import (
    install_reactor,
    is_asyncio_reactor_installed,
    set_asyncio_event_loop,
)


@pytest.mark.usefixtures("reactor_pytest")
class TestAsyncio(TestCase):
    def test_is_asyncio_reactor_installed(self):
        # the result should depend only on the pytest --reactor argument
        assert is_asyncio_reactor_installed() == (self.reactor_pytest != "default")

    def test_install_asyncio_reactor(self):
        from twisted.internet import reactor as original_reactor

        with warnings.catch_warnings(record=True) as w:
            install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
            assert len(w) == 0
        from twisted.internet import reactor  # pylint: disable=reimported

        assert original_reactor == reactor

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_set_asyncio_event_loop(self):
        install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
        assert set_asyncio_event_loop(None) is asyncio.get_running_loop()
