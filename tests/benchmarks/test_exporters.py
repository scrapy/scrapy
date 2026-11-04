from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Field, Item
from scrapy.exporters import CsvItemExporter, JsonLinesItemExporter, XmlItemExporter

if TYPE_CHECKING:
    from pytest_codspeed import BenchmarkFixture  # type: ignore[import-not-found]

pytest.importorskip("pytest_codspeed", reason="Benchmarks require pytest-codspeed")

ITEMS = 1000


class _Offer(Item):
    seller = Field()
    price = Field()
    currency = Field()


class _Product(Item):
    url = Field()
    name = Field()
    sku = Field()
    brand = Field()
    price = Field()
    currency = Field()
    availability = Field()
    rating = Field()
    review_count = Field()
    description = Field()
    tags = Field()
    offers = Field()


def _values(index: int) -> dict[str, Any]:
    return {
        "url": f"https://www.example.com/catalogue/product-{index}.html",
        "name": f"Product {index}",
        "sku": f"SKU-{index:06d}",
        "brand": "Example Brand",
        "price": 19.99 + index,
        "currency": "EUR",
        "availability": "InStock",
        "rating": 4.5,
        "review_count": index % 500,
        "description": f"A description of product {index}, a few words long.",
        "tags": ["books", "fiction", "paperback"],
    }


def _offers(index: int) -> list[_Offer]:
    return [
        _Offer(seller=f"Seller {seller}", price=17.99 + index, currency="EUR")
        for seller in range(2)
    ]


ITEM_SETS: dict[str, list[Any]] = {
    "dict": [_values(index) for index in range(ITEMS)],
    "item": [_Product(**_values(index)) for index in range(ITEMS)],
    "nested": [
        _Product(**_values(index), offers=_offers(index)) for index in range(ITEMS)
    ],
}


@pytest.mark.parametrize(
    ("exporter_cls", "separator", "separators"),
    [
        pytest.param(JsonLinesItemExporter, b"\n", ITEMS, id="jsonlines"),
        # The header row adds a line.
        pytest.param(CsvItemExporter, b"\r\n", ITEMS + 1, id="csv"),
        pytest.param(XmlItemExporter, b"<item>", ITEMS, id="xml"),
    ],
)
@pytest.mark.parametrize("values", list(ITEM_SETS))
def test_export(
    benchmark: BenchmarkFixture,
    exporter_cls: type[CsvItemExporter | JsonLinesItemExporter | XmlItemExporter],
    separator: bytes,
    separators: int,
    values: str,
) -> None:
    """Exporting items to each of the most common feed formats.

    The dict and item scenarios export the same flat values. Items also have
    field metadata, where exporters look up a serializer for every field. The
    nested scenario adds a list of nested items to every item, which exporters
    serialize recursively.
    """
    items = ITEM_SETS[values]

    def run() -> None:
        file = BytesIO()
        exporter = exporter_cls(file)
        exporter.start_exporting()
        for item in items:
            exporter.export_item(item)
        exporter.finish_exporting()
        assert file.getvalue().count(separator) == separators

    benchmark(run)
