from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import (
    PARSERS,
    MyItem,
    assert_exported,
    export_by_format,
    unique_path,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.mockserver.http import MockServer


@pytest.mark.parametrize("fmt", list(PARSERS))
@coroutine_test
async def test_export_items(fmt: str, mockserver: MockServer, tmp_path: Path) -> None:
    # feed exporters use field names from Item
    items = [
        MyItem({"foo": "bar1", "egg": "spam1"}),
        MyItem({"foo": "bar2", "egg": "spam2", "baz": "quux2"}),
    ]
    rows = [
        {"egg": "spam1", "foo": "bar1"},
        {"egg": "spam2", "foo": "bar2", "baz": "quux2"},
    ]
    header = MyItem.fields.keys()
    await assert_exported(mockserver, tmp_path, fmt, items, header, rows)


@coroutine_test
async def test_export_encoding(mockserver: MockServer, tmp_path: Path) -> None:
    items = [{"foo": "Test\xd6"}]

    formats = {
        "json": b'[{"foo": "Test\\u00d6"}]',
        "jsonlines": b'{"foo": "Test\\u00d6"}\n',
        "xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<items><item><foo>Test\xd6</foo></item></items>"
        ).encode(),
        "csv": "foo\r\nTest\xd6\r\n".encode(),
    }

    for fmt, expected in formats.items():
        settings: dict[str, Any] = {
            "FEEDS": {
                unique_path(tmp_path): {"format": fmt},
            },
            "FEED_EXPORT_INDENT": None,
        }
        data = await export_by_format(mockserver, items, settings)
        assert data[fmt] == expected

    formats = {
        "json": b'[{"foo": "Test\xd6"}]',
        "jsonlines": b'{"foo": "Test\xd6"}\n',
        "xml": (
            b'<?xml version="1.0" encoding="latin-1"?>\n'
            b"<items><item><foo>Test\xd6</foo></item></items>"
        ),
        "csv": b"foo\r\nTest\xd6\r\n",
    }

    for fmt, expected in formats.items():
        settings = {
            "FEEDS": {
                unique_path(tmp_path): {"format": fmt},
            },
            "FEED_EXPORT_INDENT": None,
            "FEED_EXPORT_ENCODING": "latin-1",
        }
        data = await export_by_format(mockserver, items, settings)
        assert data[fmt] == expected


@coroutine_test
async def test_export_multiple_configs(mockserver: MockServer, tmp_path: Path) -> None:
    items = [{"foo": "FOO", "bar": "BAR"}]

    formats = {
        "json": b'[\n{"bar": "BAR"}\n]',
        "xml": (
            b'<?xml version="1.0" encoding="latin-1"?>\n'
            b"<items>\n  <item>\n    <foo>FOO</foo>\n  </item>\n</items>"
        ),
        "csv": b"bar,foo\r\nBAR,FOO\r\n",
    }

    settings = {
        "FEEDS": {
            unique_path(tmp_path): {
                "format": "json",
                "indent": 0,
                "fields": ["bar"],
                "encoding": "utf-8",
            },
            unique_path(tmp_path): {
                "format": "xml",
                "indent": 2,
                "fields": ["foo"],
                "encoding": "latin-1",
            },
            unique_path(tmp_path): {
                "format": "csv",
                "indent": None,
                "fields": ["bar", "foo"],
                "encoding": "utf-8",
            },
        },
    }

    data = await export_by_format(mockserver, items, settings)
    for fmt, expected in formats.items():
        assert data[fmt] == expected


@coroutine_test
async def test_export_indentation(mockserver: MockServer, tmp_path: Path) -> None:
    items = [
        {"foo": ["bar"]},
        {"key": "value"},
    ]

    test_cases: list[dict[str, Any]] = [
        # JSON
        {
            "format": "json",
            "indent": None,
            "expected": b'[{"foo": ["bar"]},{"key": "value"}]',
        },
        {
            "format": "json",
            "indent": -1,
            "expected": b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
        },
        {
            "format": "json",
            "indent": 0,
            "expected": b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
        },
        {
            "format": "json",
            "indent": 2,
            "expected": b"""[
{
  "foo": [
    "bar"
  ]
},
{
  "key": "value"
}
]""",
        },
        {
            "format": "json",
            "indent": 4,
            "expected": b"""[
{
    "foo": [
        "bar"
    ]
},
{
    "key": "value"
}
]""",
        },
        {
            "format": "json",
            "indent": 5,
            "expected": b"""[
{
     "foo": [
          "bar"
     ]
},
{
     "key": "value"
}
]""",
        },
        # XML
        {
            "format": "xml",
            "indent": None,
            "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items><item><foo><value>bar</value></foo></item><item><key>value</key></item></items>""",
        },
        {
            "format": "xml",
            "indent": -1,
            "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
        },
        {
            "format": "xml",
            "indent": 0,
            "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
        },
        {
            "format": "xml",
            "indent": 2,
            "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
  <item>
    <foo>
      <value>bar</value>
    </foo>
  </item>
  <item>
    <key>value</key>
  </item>
</items>""",
        },
        {
            "format": "xml",
            "indent": 4,
            "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
    <item>
        <foo>
            <value>bar</value>
        </foo>
    </item>
    <item>
        <key>value</key>
    </item>
</items>""",
        },
        {
            "format": "xml",
            "indent": 5,
            "expected": b"""<?xml version="1.0" encoding="utf-8"?>
<items>
     <item>
          <foo>
               <value>bar</value>
          </foo>
     </item>
     <item>
          <key>value</key>
     </item>
</items>""",
        },
    ]

    for row in test_cases:
        settings = {
            "FEEDS": {
                unique_path(tmp_path): {
                    "format": row["format"],
                    "indent": row["indent"],
                },
            },
        }
        data = await export_by_format(mockserver, items, settings)
        assert data[row["format"]] == row["expected"]


@coroutine_test
async def test_extend_kwargs(mockserver: MockServer, tmp_path: Path) -> None:
    items = [{"foo": "FOO", "bar": "BAR"}]

    expected_with_title_csv = b"foo,bar\r\nFOO,BAR\r\n"
    expected_without_title_csv = b"FOO,BAR\r\n"
    test_cases: list[dict[str, Any]] = [
        # with title
        {
            "options": {
                "format": "csv",
                "item_export_kwargs": {"include_headers_line": True},
            },
            "expected": expected_with_title_csv,
        },
        # without title
        {
            "options": {
                "format": "csv",
                "item_export_kwargs": {"include_headers_line": False},
            },
            "expected": expected_without_title_csv,
        },
    ]

    for row in test_cases:
        feed_options = row["options"]
        settings = {
            "FEEDS": {
                unique_path(tmp_path): feed_options,
            },
            "FEED_EXPORT_INDENT": None,
        }

        data = await export_by_format(mockserver, items, settings)
        assert data[feed_options["format"]] == row["expected"]
