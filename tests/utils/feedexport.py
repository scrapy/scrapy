from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin
from urllib.request import pathname2url

from scrapy import Field, Item

if TYPE_CHECKING:
    from pathlib import Path


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
