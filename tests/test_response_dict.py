from __future__ import annotations

from ipaddress import ip_address

from scrapy import Request
from scrapy.http import HtmlResponse, Response, TextResponse
from scrapy.utils.response import response_from_dict


class CustomResponse(TextResponse):
    attributes: tuple[str, ...] = (*TextResponse.attributes, "custom")

    def __init__(self, *args, custom: str | None = None, **kwargs):
        self.custom = custom
        super().__init__(*args, **kwargs)


class DynamicResponse(Response):
    """Response subclass that extends
    :attr:`~scrapy.http.Response.attributes` on instances, as plugins that
    support several Scrapy versions do."""

    def __init__(self, *args, custom: str | None = None, **kwargs):
        self.custom = custom
        super().__init__(*args, **kwargs)
        self.attributes = (*self.attributes, "custom")


def test_basic() -> None:
    """The class of plain responses is not stored, it is guessed back from the
    response data."""
    response = Response("https://example.com", body=b"\x00\x01")
    assert "_class" not in response.to_dict()
    response2 = response_from_dict(response.to_dict())
    assert response2.__class__ is Response
    assert response2.url == response.url


def test_all_attributes() -> None:
    response = HtmlResponse(
        url="https://example.com",
        status=201,
        headers={"Content-Type": "text/html; charset=latin-1"},
        body=b"\xa3",
        flags=["testFlag"],
        encoding="latin-1",
        ip_address=ip_address("127.0.0.1"),
        protocol="h2",
    )
    response2 = response_from_dict(response.to_dict())
    assert response2.__class__ is HtmlResponse
    for attribute in HtmlResponse.attributes:
        if attribute in {"request", "certificate"}:
            continue
        assert getattr(response2, attribute) == getattr(response, attribute)


def test_custom_attributes() -> None:
    response = CustomResponse("https://example.com", custom="value")
    response2 = response_from_dict(response.to_dict())
    assert isinstance(response2, CustomResponse)
    assert response2.custom == "value"


def test_custom_instance_attributes() -> None:
    response = DynamicResponse("https://example.com", custom="value")
    response2 = response_from_dict(response.to_dict())
    assert isinstance(response2, DynamicResponse)
    assert response2.custom == "value"


def test_crawl_attributes_left_out() -> None:
    response = Response(
        "https://example.com",
        request=Request("https://example.com"),
        certificate=object(),
    )
    d = response.to_dict()
    assert "request" not in d
    assert "certificate" not in d
    response2 = response_from_dict(d)
    assert response2.request is None
    assert response2.certificate is None


def test_unknown_class() -> None:
    """Dicts that do not indicate a response class, e.g. cache entries written
    by older Scrapy versions, get a class based on their data."""
    response2 = response_from_dict(
        {
            "url": "https://example.com",
            "status": 200,
            "headers": {b"Content-Type": [b"text/plain"]},
            "body": b"foo",
        }
    )
    assert response2.__class__ is TextResponse
    assert response2.text == "foo"
