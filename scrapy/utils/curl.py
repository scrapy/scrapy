from __future__ import annotations


import argparse
import warnings
from http.cookies import SimpleCookie
from shlex import split
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import urlparse
from w3lib.http import basic_auth_header

if TYPE_CHECKING:
    from collections.abc import Sequence


class DataAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        value = str(values)
        # curl merges repeated -d/--data/--data-raw options into a single body
        # joined with "&"; mirror that instead of keeping only the last one.
        previous = getattr(namespace, self.dest, None)
        if previous is not None:
            value = f"{previous}&{value}"
        setattr(namespace, self.dest, value)


class CurlParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        error_msg = f"There was an error parsing the curl command: {message}"
        raise ValueError(error_msg)


curl_parser = CurlParser()
curl_parser.add_argument("urls", nargs="*")
curl_parser.add_argument("-H", "--header", dest="headers", action="append")
curl_parser.add_argument("-X", "--request", dest="method")
curl_parser.add_argument("-b", "--cookie", dest="cookies", action="append")
curl_parser.add_argument("-d", "--data", "--data-raw", dest="data", action=DataAction)
curl_parser.add_argument("-u", "--user", dest="auth")

safe_to_ignore_arguments = [
    ["--compressed"],
    # `--compressed` argument is not safe to ignore, but it's included here
    # because the `HttpCompressionMiddleware` is enabled by default
    ["-s", "--silent"],
    ["-v", "--verbose"],
    ["-#", "--progress-bar"],
]
for argument in safe_to_ignore_arguments:
    curl_parser.add_argument(*argument, action="store_true")


def _select_url(
    curl_args: list[str], parsed_args: argparse.Namespace, argv: list[str]
) -> tuple[str, list[str]]:
    """Pick the URL out of the words that are not known option values.

    argparse hands the value of an unrecognized option to a positional, so
    in "curl -x http://proxy https://example.com" the proxy address is a
    positional candidate just like the real URL. A candidate that directly
    follows an unrecognized option is that option's value, not the URL.
    Returns the URL and the positional candidates that were not picked, so
    the caller can still report them as unrecognized.
    """
    unknown_options = {arg.split("=", 1)[0] for arg in argv if arg.startswith("-")}
    candidates = set(parsed_args.urls) | {
        arg for arg in argv if not arg.startswith("-")
    }
    ordered = [arg for arg in curl_args if arg in candidates]
    urls = [
        arg
        for index, arg in enumerate(curl_args)
        if arg in candidates
        and (index == 0 or curl_args[index - 1].split("=", 1)[0] not in unknown_options)
    ]
    if urls:
        url = urls[0]
    elif ordered:
        # An unrecognized flag that takes no value (e.g. -k) leaves the URL
        # directly after it, so the filter above dropped the URL as well.
        # Prefer a candidate with a scheme, as the URL is the one word in a
        # curl command that normally carries one.
        url = next((arg for arg in ordered if "://" in arg), ordered[0])
    else:
        curl_parser.error("the following arguments are required: url")
    return url, [arg for arg in ordered if arg != url]


def _parse_headers_and_cookies(
    parsed_args: argparse.Namespace,
) -> tuple[list[tuple[str, str | bytes | None]], dict[str, str]]:
    headers: list[tuple[str, str | bytes | None]] = []
    cookies = {}
    for header in parsed_args.headers or []:
        if not isinstance(header, str):
            continue
        name, value = header.split(":", 1)
        name = name.strip()
        value = value.strip()
        if name.lower() == "cookie":
            cookies.update(SimpleCookie(value))  # type: ignore[arg-type]
        else:
            headers.append((name, value))
    for cookie in parsed_args.cookies or []:
        if cookie:
            cookies.update(SimpleCookie(cookie))  # type: ignore[arg-type]
    return headers, cookies


def curl_to_request_kwargs(
    curl_command: str, ignore_unknown_options: bool = True
) -> dict[str, Any]:
    """Convert a curl command to a :class:`~scrapy.Request` keyword arguments.

    :param curl_command: The curl command to convert.
    :param ignore_unknown_options: If ``True``, unrecognized options are
        ignored, issuing a warning about them, and the request is returned.
        If ``False``, a :exc:`ValueError` is raised when an unrecognized
        option is found.
    """

    def exhaustive_descape(value: str) -> str:
        """Descape repeatedly, to work around curl's lack of support for e.g.
        ``\\$``.
        """
        result = value
        while True:
            new_result = result.encode().decode("unicode_escape")
            if new_result == result:
                return new_result
            result = new_result

    def escape_data(value: str | None) -> str | None:
        # Use get() instead of [] to disable the "***" fallback added in
        # shlex 3.13.
        quote = SHLEX_QUOTE_CHARS.get("'", "'")
        return value.replace("'", f"'{quote}'") if value else None

    curl_args = split(curl_command)

    if not curl_args or curl_args[0] != "curl":
        raise ValueError("A curl command must start with 'curl'")

    parsed_args, argv = curl_parser.parse_known_args(curl_args[1:])

    url, unused = _select_url(curl_args[1:], parsed_args, argv)
    # Keep reporting every word that was not used: the unrecognized options
    # themselves and any positional candidate that turned out to be the
    # value of one of those options or an extra URL.
    argv = [arg for arg in argv if arg.startswith("-")] + unused

    if argv:
        msg = f"Unrecognized options: {', '.join(argv)}"
        if ignore_unknown_options:
            warnings.warn(msg, UserWarning, stacklevel=2)
        else:
            raise ValueError(msg)

    # curl automatically prepends 'http' if the scheme is missing, but Request
    # needs the scheme to work
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme or "http"
    url = url.replace(parsed_url.scheme, scheme, 1)

    headers, cookies = _parse_headers_and_cookies(parsed_args)

    body = None
    if parsed_args.data:
        body = parsed_args.data

    auth = None
    if parsed_args.auth:
        auth = basic_auth_header(*parsed_args.auth.split(":", 1))

    method = parsed_args.method
    if not method:
        method = "POST" if body else "GET"

    request_kwargs: dict[str, Any] = {"method": method, "url": url}
    if headers:
        request_kwargs["headers"] = headers
    if cookies:
        request_kwargs["cookies"] = cookies
    if body:
        request_kwargs["body"] = body
    if auth:
        request_kwargs["headers"] = [*request_kwargs.get("headers", []), auth]

    return request_kwargs
