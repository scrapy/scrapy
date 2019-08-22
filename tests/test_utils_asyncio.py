from unittest import TestCase

from pytest import mark

from scrapy.utils.asyncio import is_asyncio_supported, install_asyncio_reactor


@mark.usefixtures('reactor_pytest')
class AsyncioTest(TestCase):

    def test_is_asyncio_supported(self):
        # the result should depend only on the pytest --reactor argument
        self.assertEquals(is_asyncio_supported(), self.reactor_pytest == 'asyncio')

    def test_install_asyncio_reactor(self):
        # this should do nothing
        install_asyncio_reactor()
