import warnings
from unittest import TestCase

from pytest import mark

from scrapy.utils.reactor import is_asyncio_reactor_installed, install_reactor


@mark.usefixtures('reactor_pytest')
class AsyncioTest(TestCase):

    def test_is_asyncio_reactor_installed(self):
        # the result should depend only on the pytest --reactor argument
        self.assertEqual(is_asyncio_reactor_installed(), self.reactor_pytest == 'asyncio')

    def test_install_asyncio_reactor(self):
        with warnings.catch_warnings(record=True) as w:
            install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
            self.assertEqual(len(w), 0)
