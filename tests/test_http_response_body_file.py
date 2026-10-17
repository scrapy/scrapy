from __future__ import annotations

import pytest

from scrapy.http import BodyFileResponse


def test_body() -> None:
    response = BodyFileResponse("https://example.com", body_file="body")
    with pytest.raises(AttributeError, match="written to 'body'"):
        response.body


def test_replace() -> None:
    response = BodyFileResponse("https://example.com", body_file="body")
    new_response = response.replace(status=404)
    assert isinstance(new_response, BodyFileResponse)
    assert new_response.body_file == "body"
    assert new_response.status == 404
    with pytest.raises(TypeError, match="does not take a body"):
        response.replace(body=b"body")
