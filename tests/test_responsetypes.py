from typing import Any

import pytest

from scrapy.http import (
    Headers,
    HtmlResponse,
    JsonResponse,
    Response,
    TextResponse,
    XmlResponse,
)
from scrapy.responsetypes import responsetypes


@pytest.mark.parametrize(
    ("source", "cls"),
    [
        ("data.bin", Response),
        ("file.txt", TextResponse),
        ("file.xml.gz", Response),
        ("file.xml", XmlResponse),
        ("file.html", HtmlResponse),
        ("file.unknownext", Response),
    ],
)
def test_from_filename(source: str, cls: type[Response]) -> None:
    assert responsetypes.from_filename(source) is cls


@pytest.mark.parametrize(
    ("source", "cls"),
    [
        pytest.param(b'attachment; filename="data.xml"', XmlResponse, id="quoted"),
        pytest.param(b"attachment; filename=data.xml", XmlResponse, id="unquoted"),
        pytest.param("attachment;filename=data£.tar.gz".encode(), Response, id="utf-8"),
        pytest.param(
            "attachment;filename=dataµ.tar.gz".encode("latin-1"),
            Response,
            id="latin-1",
        ),
        pytest.param(
            "attachment;filename=data高.doc".encode("gbk"), Response, id="gbk"
        ),
        pytest.param(
            "attachment;filename=دورهdata.html".encode("cp720"),
            HtmlResponse,
            id="cp720",
        ),
        pytest.param(
            "attachment;filename=日本語版Wikipedia.xml".encode("iso2022_jp"),
            XmlResponse,
            id="iso2022_jp",
        ),
    ],
)
def test_from_content_disposition(source: bytes, cls: type[Response]) -> None:
    assert responsetypes.from_content_disposition(source) is cls


def test_from_content_disposition_no_filename() -> None:
    assert responsetypes.from_content_disposition(b"attachment") is Response


@pytest.mark.parametrize(
    ("source", "cls"),
    [
        ("text/html; charset=UTF-8", HtmlResponse),
        ("text/xml; charset=UTF-8", XmlResponse),
        ("application/xhtml+xml; charset=UTF-8", HtmlResponse),
        ("application/vnd.wap.xhtml+xml; charset=utf-8", HtmlResponse),
        ("application/xml; charset=UTF-8", XmlResponse),
        ("application/octet-stream", Response),
        ("application/json; encoding=UTF8;charset=UTF-8", JsonResponse),
        ("application/x-json; encoding=UTF8;charset=UTF-8", JsonResponse),
        ("application/json-amazonui-streaming;charset=UTF-8", JsonResponse),
        (b"application/x-download; filename=\x80dummy.txt", Response),
    ],
)
def test_from_content_type(source: str | bytes, cls: type[Response]) -> None:
    assert responsetypes.from_content_type(source) is cls


@pytest.mark.parametrize(
    ("source", "cls"),
    [
        (b"\x03\x02\xdf\xdd\x23", Response),
        (b"Some plain text\ndata with tabs\t and null bytes\0", TextResponse),
        (b"<html><head><title>Hello</title></head>", HtmlResponse),
        # https://codersblock.com/blog/the-smallest-valid-html5-page/
        (b"<!DOCTYPE html>\n<title>.</title>", HtmlResponse),
        (b'<?xml version="1.0" encoding="utf-8"', XmlResponse),
    ],
)
def test_from_body(source: bytes, cls: type[Response]) -> None:
    assert responsetypes.from_body(source) is cls


@pytest.mark.parametrize(
    ("source", "cls"),
    [
        pytest.param(
            {"Content-Type": ["text/html; charset=utf-8"]},
            HtmlResponse,
            id="content-type",
        ),
        pytest.param(
            {
                "Content-Type": ["text/html; charset=utf-8"],
                "Content-Encoding": ["gzip"],
            },
            Response,
            id="content-encoding",
        ),
        pytest.param(
            {
                "Content-Type": ["application/octet-stream"],
                "Content-Disposition": ["attachment; filename=data.txt"],
            },
            TextResponse,
            id="content-disposition",
        ),
    ],
)
def test_from_headers(source: dict[str, list[str]], cls: type[Response]) -> None:
    assert responsetypes.from_headers(Headers(source)) is cls


# TODO: add more tests that check precedence between the different arguments
@pytest.mark.parametrize(
    ("source", "cls"),
    [
        pytest.param(
            {"url": "http://www.example.com/data.csv"}, TextResponse, id="url"
        ),
        # headers takes precedence over url
        pytest.param(
            {
                "headers": Headers({"Content-Type": ["text/html; charset=utf-8"]}),
                "url": "http://www.example.com/item/",
            },
            HtmlResponse,
            id="content-type-and-url",
        ),
        pytest.param(
            {
                "headers": Headers(
                    {"Content-Disposition": ['attachment; filename="data.xml.gz"']}
                ),
                "url": "http://www.example.com/page/",
            },
            Response,
            id="content-disposition-and-url",
        ),
    ],
)
def test_from_args(source: dict[str, Any], cls: type[Response]) -> None:
    assert responsetypes.from_args(**source) is cls


def test_custom_mime_types_loaded() -> None:
    # check that mime.types files shipped with scrapy are loaded
    assert responsetypes.mimetypes.guess_type("x.scrapytest")[0] == "x-scrapy/test"
