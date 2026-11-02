from __future__ import annotations

from pathlib import Path

import pytest

from scrapy.http import BodyFileResponse, Request
from scrapy.utils.response import response_from_dict


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


@pytest.mark.parametrize("path_type", [str, Path])
def test_serialization_round_trip(tmp_path: Path, path_type: type[str | Path]) -> None:
    body_file = path_type(tmp_path / "download.bin")
    response = BodyFileResponse(
        "https://example.com/download",
        body_file=body_file,
        status=206,
        headers={"Content-Type": "application/octet-stream"},
        flags=["partial"],
        request=Request("https://example.com/download"),
    )

    serialized = response.to_dict()
    restored = response_from_dict(serialized)

    assert "body" not in serialized
    assert "request" not in serialized
    assert isinstance(restored, BodyFileResponse)
    assert restored.body_file == body_file
    assert restored.url == response.url
    assert restored.status == response.status
    assert restored.headers == response.headers
    assert restored.flags == response.flags
    assert restored.request is None
    assert not Path(body_file).exists()


def test_copy_preserves_file_backing(tmp_path: Path) -> None:
    request = Request("https://example.com/download")
    response = BodyFileResponse(
        request.url, body_file=tmp_path / "download.bin", request=request
    )

    copied = response.copy()

    assert copied is not response
    assert isinstance(copied, BodyFileResponse)
    assert copied.body_file == response.body_file
    assert copied.request is request
    with pytest.raises(AttributeError, match="not in memory"):
        copied.body
