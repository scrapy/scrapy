from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import PARSERS, MyItem, MyItem2, assert_exported

if TYPE_CHECKING:
    from pathlib import Path

    from tests.mockserver.http import MockServer


@pytest.mark.parametrize("fmt", ["csv", "jsonlines"])
@coroutine_test
async def test_export_items_empty_field_list(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    # FEED_EXPORT_FIELDS==[] means the same as default None
    items = [{"foo": "bar"}]
    header = ["foo"]
    rows = [{"foo": "bar"}]
    settings: dict[str, Any] = {"FEED_EXPORT_FIELDS": []}
    await assert_exported(mockserver, tmp_path, fmt, items, header, rows, settings)


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_items_field_list(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    items = [{"foo": "bar"}]
    header = ["foo", "baz"]
    rows = [{"foo": "bar"}]
    settings = {"FEED_EXPORT_FIELDS": header}
    await assert_exported(mockserver, tmp_path, fmt, items, header, rows, settings)


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_items_comma_separated_field_list(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    items = [{"foo": "bar"}]
    header = ["foo", "baz"]
    rows = [{"foo": "bar"}]
    settings = {"FEED_EXPORT_FIELDS": ",".join(header)}
    await assert_exported(mockserver, tmp_path, fmt, items, header, rows, settings)


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_items_json_field_list(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    items = [{"foo": "bar"}]
    header = ["foo", "baz"]
    rows = [{"foo": "bar"}]
    settings = {"FEED_EXPORT_FIELDS": json.dumps(header)}
    await assert_exported(mockserver, tmp_path, fmt, items, header, rows, settings)


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_items_field_names(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    items = [{"foo": "bar"}]
    header = {"foo": "Foo"}
    rows = [{"Foo": "bar"}]
    settings = {"FEED_EXPORT_FIELDS": header}
    await assert_exported(
        mockserver, tmp_path, fmt, items, header.values(), rows, settings
    )


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_items_dict_field_names(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    items = [{"foo": "bar"}]
    header = {
        "baz": "Baz",
        "foo": "Foo",
    }
    rows = [{"Foo": "bar"}]
    settings = {"FEED_EXPORT_FIELDS": header}
    await assert_exported(
        mockserver, tmp_path, fmt, items, ["Baz", "Foo"], rows, settings
    )


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_items_json_field_names(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    items = [{"foo": "bar"}]
    header = {"foo": "Foo"}
    rows = [{"Foo": "bar"}]
    settings = {"FEED_EXPORT_FIELDS": json.dumps(header)}
    await assert_exported(
        mockserver, tmp_path, fmt, items, header.values(), rows, settings
    )


# When dicts are used, only keys from the first row are used as
# a header for CSV, and all fields are used for JSON Lines.
@pytest.mark.parametrize(
    ("fmt", "rows"),
    [
        ("csv", [{"egg": "spam", "foo": "bar"}, {"egg": "spam", "foo": "bar"}]),
        (
            "jsonlines",
            [
                {"foo": "bar", "egg": "spam"},
                {"foo": "bar", "egg": "spam", "baz": "quux"},
            ],
        ),
    ],
)
@coroutine_test
async def test_export_dicts(
    fmt: str,
    rows: list[dict[str, Any]],
    mockserver: MockServer,
    tmp_path: Path,
) -> None:
    items = [
        {"foo": "bar", "egg": "spam"},
        {"foo": "bar", "egg": "spam", "baz": "quux"},
    ]
    header = ["foo", "egg"]
    await assert_exported(mockserver, tmp_path, fmt, items, header, rows)


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_tuple(fmt: str, mockserver: MockServer, tmp_path: Path) -> None:
    items = [
        {"foo": "bar1", "egg": "spam1"},
        {"foo": "bar2", "egg": "spam2", "baz": "quux"},
    ]

    settings = {"FEED_EXPORT_FIELDS": ("foo", "baz")}
    rows = [{"foo": "bar1"}, {"foo": "bar2", "baz": "quux"}]
    await assert_exported(
        mockserver, tmp_path, fmt, items, ["foo", "baz"], rows, settings
    )


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_feed_export_fields(
    fmt: str, mockserver: MockServer, tmp_path: Path
) -> None:
    # FEED_EXPORT_FIELDS option allows to order export fields
    # and to select a subset of fields to export, both for Items and dicts.

    for item_cls in [MyItem, dict]:
        items = [
            item_cls({"foo": "bar1", "egg": "spam1"}),
            item_cls({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
        ]

        # export all columns
        settings = {"FEED_EXPORT_FIELDS": "foo,baz,egg"}
        rows = [
            {"egg": "spam1", "foo": "bar1"},
            {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
        ]
        await assert_exported(
            mockserver, tmp_path, fmt, items, ["foo", "baz", "egg"], rows, settings
        )

        # export a subset of columns
        settings = {"FEED_EXPORT_FIELDS": "egg,baz"}
        rows = [{"egg": "spam1"}, {"egg": "spam2", "baz": "quux2"}]
        await assert_exported(
            mockserver, tmp_path, fmt, items, ["egg", "baz"], rows, settings
        )


# by default, Scrapy uses fields of the first Item for CSV and
# all fields for JSON Lines
@pytest.mark.parametrize(
    ("fmt", "rows"),
    [
        (
            "csv",
            [
                {"egg": "spam1", "foo": "bar1"},
                {"foo": "bar2"},
                {"egg": "spam3", "foo": "bar3", "baz": "quux3"},
                {"egg": "spam4"},
            ],
        ),
        (
            "jsonlines",
            [
                {"foo": "bar1", "egg": "spam1"},
                {"hello": "world2", "foo": "bar2"},
                {"foo": "bar3", "egg": "spam3", "baz": "quux3"},
                {"hello": "world4", "egg": "spam4"},
            ],
        ),
    ],
)
@coroutine_test
async def test_export_multiple_item_classes(
    fmt: str,
    rows: list[dict[str, Any]],
    mockserver: MockServer,
    tmp_path: Path,
) -> None:
    items = [
        MyItem({"foo": "bar1", "egg": "spam1"}),
        MyItem2({"hello": "world2", "foo": "bar2"}),
        MyItem({"foo": "bar3", "egg": "spam3", "baz": "quux3"}),
        {"hello": "world4", "egg": "spam4"},
    ]
    header = MyItem.fields.keys()
    await assert_exported(mockserver, tmp_path, fmt, items, header, rows)
