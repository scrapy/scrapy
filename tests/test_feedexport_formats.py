from __future__ import annotations

from typing import TYPE_CHECKING

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


@pytest.mark.parametrize(
    ("fmt", "encoding", "expected"),
    [
        pytest.param("json", None, b'[{"foo": "Test\\u00d6"}]', id="json-default"),
        pytest.param(
            "jsonlines", None, b'{"foo": "Test\\u00d6"}\n', id="jsonlines-default"
        ),
        pytest.param(
            "xml",
            None,
            (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                "<items><item><foo>Test\xd6</foo></item></items>"
            ).encode(),
            id="xml-default",
        ),
        pytest.param("csv", None, "foo\r\nTest\xd6\r\n".encode(), id="csv-default"),
        pytest.param("json", "latin-1", b'[{"foo": "Test\xd6"}]', id="json-latin-1"),
        pytest.param(
            "jsonlines", "latin-1", b'{"foo": "Test\xd6"}\n', id="jsonlines-latin-1"
        ),
        pytest.param(
            "xml",
            "latin-1",
            (
                b'<?xml version="1.0" encoding="latin-1"?>\n'
                b"<items><item><foo>Test\xd6</foo></item></items>"
            ),
            id="xml-latin-1",
        ),
        pytest.param("csv", "latin-1", b"foo\r\nTest\xd6\r\n", id="csv-latin-1"),
    ],
)
@coroutine_test
async def test_export_encoding(
    fmt: str,
    encoding: str | None,
    expected: bytes,
    mockserver: MockServer,
    tmp_path: Path,
) -> None:
    items = [{"foo": "Test\xd6"}]
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": fmt},
        },
        "FEED_EXPORT_INDENT": None,
        "FEED_EXPORT_ENCODING": encoding,
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


@pytest.mark.parametrize(
    ("fmt", "indent", "expected"),
    [
        pytest.param(
            "json", None, b'[{"foo": ["bar"]},{"key": "value"}]', id="json-None"
        ),
        pytest.param(
            "json",
            -1,
            b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            id="json--1",
        ),
        pytest.param(
            "json",
            0,
            b"""[
{"foo": ["bar"]},
{"key": "value"}
]""",
            id="json-0",
        ),
        pytest.param(
            "json",
            2,
            b"""[
{
  "foo": [
    "bar"
  ]
},
{
  "key": "value"
}
]""",
            id="json-2",
        ),
        pytest.param(
            "json",
            4,
            b"""[
{
    "foo": [
        "bar"
    ]
},
{
    "key": "value"
}
]""",
            id="json-4",
        ),
        pytest.param(
            "json",
            5,
            b"""[
{
     "foo": [
          "bar"
     ]
},
{
     "key": "value"
}
]""",
            id="json-5",
        ),
        pytest.param(
            "xml",
            None,
            b"""<?xml version="1.0" encoding="utf-8"?>
<items><item><foo><value>bar</value></foo></item><item><key>value</key></item></items>""",
            id="xml-None",
        ),
        pytest.param(
            "xml",
            -1,
            b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            id="xml--1",
        ),
        pytest.param(
            "xml",
            0,
            b"""<?xml version="1.0" encoding="utf-8"?>
<items>
<item><foo><value>bar</value></foo></item>
<item><key>value</key></item>
</items>""",
            id="xml-0",
        ),
        pytest.param(
            "xml",
            2,
            b"""<?xml version="1.0" encoding="utf-8"?>
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
            id="xml-2",
        ),
        pytest.param(
            "xml",
            4,
            b"""<?xml version="1.0" encoding="utf-8"?>
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
            id="xml-4",
        ),
        pytest.param(
            "xml",
            5,
            b"""<?xml version="1.0" encoding="utf-8"?>
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
            id="xml-5",
        ),
    ],
)
@coroutine_test
async def test_export_indentation(
    fmt: str,
    indent: int | None,
    expected: bytes,
    mockserver: MockServer,
    tmp_path: Path,
) -> None:
    items = [
        {"foo": ["bar"]},
        {"key": "value"},
    ]
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {
                "format": fmt,
                "indent": indent,
            },
        },
    }
    data = await export_by_format(mockserver, items, settings)
    assert data[fmt] == expected


@pytest.mark.parametrize(
    ("include_headers_line", "expected"),
    [
        pytest.param(True, b"foo,bar\r\nFOO,BAR\r\n", id="with-headers"),
        pytest.param(False, b"FOO,BAR\r\n", id="without-headers"),
    ],
)
@coroutine_test
async def test_extend_kwargs(
    include_headers_line: bool,
    expected: bytes,
    mockserver: MockServer,
    tmp_path: Path,
) -> None:
    items = [{"foo": "FOO", "bar": "BAR"}]
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {
                "format": "csv",
                "item_export_kwargs": {"include_headers_line": include_headers_line},
            },
        },
        "FEED_EXPORT_INDENT": None,
    }
    data = await export_by_format(mockserver, items, settings)
    assert data["csv"] == expected
