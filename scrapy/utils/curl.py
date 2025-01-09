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
        if value.startswith("$"):
            value = value[1:]
        setattr(namespace, self.dest, value)


class CurlParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        error_msg = f"There was an error parsing the curl command: {message}"
        raise ValueError(error_msg)


curl_parser = CurlParser()
curl_parser.add_argument("url")
curl_parser.add_argument("-H", "--header", dest="headers", action="append")
curl_parser.add_argument("-X", "--request", dest="method")
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


def _parse_headers_and_cookies(
    parsed_args: argparse.Namespace,
) -> tuple[list[tuple[str, bytes]], dict[str, str]]:
    headers: list[tuple[str, bytes]] = []
    cookies: dict[str, str] = {}
    for header in parsed_args.headers or ():
        name, val = header.split(":", 1)
        name = name.strip()
        val = val.strip()
        if name.title() == "Cookie":
            for name, morsel in SimpleCookie(val).items():
                cookies[name] = morsel.value
        else:
            headers.append((name, val))

    if parsed_args.auth:
        user, password = parsed_args.auth.split(":", 1)
        headers.append(("Authorization", basic_auth_header(user, password)))

    return headers, cookies


def curl_to_request_kwargs(
    curl_command: str, ignore_unknown_options: bool = True
) -> dict[str, Any]:
    """Convert a cURL command syntax to Request kwargs.

    :param str curl_command: string containing the curl command
    :param bool ignore_unknown_options: If true, only a warning is emitted when
                                        cURL options are unknown. Otherwise
                                        raises an error. (default: True)
    :return: dictionary of Request kwargs
    """

    curl_args = split(curl_command)

    if curl_args[0] != "curl":
        raise ValueError('A curl command must start with "curl"')

    parsed_args, argv = curl_parser.parse_known_args(curl_args[1:])

    if argv:
        msg = f'Unrecognized options: {", ".join(argv)}'
        if ignore_unknown_options:
            warnings.warn(msg)
        else:
            raise ValueError(msg)

    url = parsed_args.url

    # curl automatically prepends 'http' if the scheme is missing, but Request
    # needs the scheme to work
    parsed_url = urlparse(url)
    if not parsed_url.scheme:
        url = "http://" + url

    method = parsed_args.method or "GET"

    result: dict[str, Any] = {"method": method.upper(), "url": url}

    headers, cookies = _parse_headers_and_cookies(parsed_args)

    if headers:
        result["headers"] = headers
    if cookies:
        result["cookies"] = cookies
    if parsed_args.data:
        result["body"] = parsed_args.data
        if not parsed_args.method:
            # if the "data" is specified but the "method" is not specified,
            # the default method is 'POST'
            result["method"] = "POST"

    return result
