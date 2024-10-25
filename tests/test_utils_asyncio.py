import asyncio
import warnings

from pytest import mark
from twisted.trial.unittest import TestCase

from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.reactor import (
    install_reactor,
    is_asyncio_reactor_installed,
    set_asyncio_event_loop,
)


@mark.usefixtures("reactor_pytest")
class AsyncioTest(TestCase):
    def test_is_asyncio_reactor_installed(self):
        # the result should depend only on the pytest --reactor argument
        self.assertEqual(
            is_asyncio_reactor_installed(), self.reactor_pytest == "asyncio"
        )

    def test_install_asyncio_reactor(self):
        from twisted.internet import reactor as original_reactor

        with warnings.catch_warnings(record=True) as w:
            install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
            self.assertEqual(len(w), 0)
        from twisted.internet import reactor

        assert original_reactor == reactor

    @mark.only_asyncio()
    @deferred_f_from_coro_f
    async def test_set_asyncio_event_loop(self):
        install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
        assert set_asyncio_event_loop(None) is asyncio.get_running_loop()
