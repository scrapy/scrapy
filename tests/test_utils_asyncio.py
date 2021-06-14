import platform
import sys
from unittest import skipIf, TestCase

from pytest import mark

from scrapy.utils.reactor import is_asyncio_reactor_installed, install_reactor


@mark.usefixtures('reactor_pytest')
class AsyncioTest(TestCase):

    def test_is_asyncio_reactor_installed(self):
        # the result should depend only on the pytest --reactor argument
        self.assertEqual(is_asyncio_reactor_installed(), self.reactor_pytest == 'asyncio')

    # https://twistedmatrix.com/trac/ticket/9766
    @skipIf(platform.system() == 'Windows' and sys.version_info >= (3, 8),
            "the asyncio reactor is broken on Windows when running Python ≥ 3.8")
    def test_install_asyncio_reactor(self):
        # this should do nothing
        install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
