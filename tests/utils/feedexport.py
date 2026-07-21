from __future__ import annotations

import random
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from string import ascii_letters, digits
from typing import IO, TYPE_CHECKING, Any
from urllib.parse import urljoin
from urllib.request import pathname2url

import scrapy
from scrapy import Field, Item, Spider
from tests.mockserver.http import MockServer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


def path_to_url(path: str | Path) -> str:
    return urljoin("file:", pathname2url(str(path)))


def printf_escape(s: str) -> str:
    return s.replace("%", "%%")


class MyItem(Item):
    foo = Field()
    egg = Field()
    baz = Field()


class MyItem2(Item):
    foo = Field()
    hello = Field()


class TestFeedExportBase(ABC):
    mockserver: MockServer

    def _random_temp_filename(self, inter_dir="") -> Path:
        chars = [random.choice(ascii_letters + digits) for _ in range(15)]
        filename = "".join(chars)
        return Path(self.temp_dir, inter_dir, filename)

    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def exported_data(
        self, items: Iterable[Any], settings: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Return exported data which a spider yielding ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                yield from items

        return await self.run_and_export(TestSpider, settings)

    async def exported_no_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        """
        Return exported data which a spider yielding no ``items`` would return.
        """

        class TestSpider(scrapy.Spider):
            name = "testspider"

            def parse(self, response):
                pass

        return await self.run_and_export(TestSpider, settings)

    async def assertExported(
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        await self.assertExportedCsv(items, header, rows, settings)
        await self.assertExportedJsonLines(items, rows, settings)
        await self.assertExportedXml(items, rows, settings)
        await self.assertExportedPickle(items, rows, settings)
        await self.assertExportedMarshal(items, rows, settings)
        await self.assertExportedMultiple(items, rows, settings)

    async def assertExportedCsv(  # noqa: B027
        self,
        items: Iterable[Any],
        header: Iterable[str],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedJsonLines(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedXml(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedMultiple(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedPickle(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    async def assertExportedMarshal(  # noqa: B027
        self,
        items: Iterable[Any],
        rows: Iterable[dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def run_and_export(
        self, spider_cls: type[Spider], settings: dict[str, Any]
    ) -> dict[str, Any]:
        pass

    def _load_until_eof(
        self, data: bytes, load_func: Callable[[IO[bytes]], Any]
    ) -> list[Any]:
        result: list[Any] = []
        with tempfile.TemporaryFile() as temp:
            temp.write(data)
            temp.seek(0)
            while True:
                try:
                    result.append(load_func(temp))
                except EOFError:
                    break
        return result
