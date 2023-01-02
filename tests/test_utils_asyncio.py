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
        from twisted.internet import reactor
        original_class = type(reactor)
        original_import_path = f"{original_class.__module__}.{original_class.__qualname__}"
        asyncio_import_path = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        try:
            with warnings.catch_warnings(record=True) as w:
                install_reactor(asyncio_import_path)
                self.assertEqual(len(w), 0)
        finally:
            if original_import_path != asyncio_import_path:
                install_reactor(original_import_path)
