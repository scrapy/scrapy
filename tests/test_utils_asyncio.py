import pytest

from scrapy.utils.asyncio import is_asyncio_available


@pytest.mark.usefixtures("reactor_pytest")
class TestAsyncio:
    def test_is_asyncio_available(self):
        # the result should depend only on the pytest --reactor argument
        assert is_asyncio_available() == (self.reactor_pytest != "default")
