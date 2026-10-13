from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from scrapy.exceptions import ChecksumError

if TYPE_CHECKING:
    from scrapy.http import Request, Response


class ChecksumMiddleware:
    """Verifies response bodies against the checksums declared in the
    :reqmeta:`expected_checksum` request meta key.

    .. versionadded:: VERSION
    """

    def process_response(self, request: Request, response: Response) -> Response:
        for algorithm, checksum in request.meta.get("expected_checksum", {}).items():
            expected = (
                bytes.fromhex(checksum) if isinstance(checksum, str) else checksum
            )
            if hashlib.new(algorithm, response.body).digest() != expected:
                raise ChecksumError(
                    f"The {algorithm} checksum of the response body of {request} "
                    f"does not match the expected checksum."
                )
        return response
