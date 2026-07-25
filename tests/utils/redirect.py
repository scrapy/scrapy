from __future__ import annotations

from itertools import product

SCHEME_PARAMS = ("url", "location", "target")
HTTP_SCHEMES = ("http", "https")
NON_HTTP_SCHEMES = ("data", "file", "ftp", "s3", "foo")
REDIRECT_SCHEME_CASES = (
    # http/https → http/https redirects
    *(
        (
            f"{input_scheme}://example.com/a",
            f"{output_scheme}://example.com/b",
            f"{output_scheme}://example.com/b",
        )
        for input_scheme, output_scheme in product(HTTP_SCHEMES, repeat=2)
    ),
    # http/https → data/file/ftp/s3/foo does not redirect
    *(
        (
            f"{input_scheme}://example.com/a",
            f"{output_scheme}://example.com/b",
            None,
        )
        for input_scheme in HTTP_SCHEMES
        for output_scheme in NON_HTTP_SCHEMES
    ),
    # http/https → relative redirects
    *(
        (
            f"{scheme}://example.com/a",
            location,
            f"{scheme}://example.com/b",
        )
        for scheme in HTTP_SCHEMES
        for location in ("//example.com/b", "/b")
    ),
    # Note: We do not test data/file/ftp/s3 schemes for the initial URL
    # because their download handlers cannot return a status code of 3xx.
)
