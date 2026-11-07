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
    cookies: dict[str, str] = {}
    for header in parsed_args.headers or ():
        val: str | None
        if ":" in header:
            name, val = header.split(":", 1)
            val = val.strip() or None
        elif header.endswith(";") and header[:-1].strip():
            name, val = header[:-1], ""
        else:
            continue
        name = name.strip()
        if name.title() == "Cookie":
            for name, morsel in SimpleCookie(val or "").items():
                cookies[name] = morsel.value
        else:
            headers.append((name, val))

    for cookie_param in parsed_args.cookies or ():
        # curl can treat this parameter as either "key=value; key2=value2" pairs, or a filename.
        # Scrapy will only support key-value pairs.
        if "=" not in cookie_param:
            continue
        for name, morsel in SimpleCookie(cookie_param).items():
            cookies[name] = morsel.value

    if parsed_args.auth:
        user, _, password = parsed_args.auth.partition(":")
        headers.append(("Authorization", basic_auth_header(user, password)))

    return headers, cookies


def _normalize_curl_command(curl_command: str) -> str:
    """Normalize Bash ANSI-C quote prefixes for shlex."""
    result: list[str] = []
    in_single_quote = False
    in_double_quote = False
    escaped = False

    i = 0
    while i < len(curl_command):
        char = curl_command[i]

        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\" and not in_single_quote:
            result.append(char)
            escaped = True
        elif char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            result.append(char)
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            result.append(char)
        elif (
            char == "$"
            and i + 1 < len(curl_command)
            and curl_command[i + 1] == "'"
            and not in_single_quote
            and not in_double_quote
        ):
            result.append("'")
            in_single_quote = True
            i += 1
        else:
            result.append(char)

        i += 1

    return "".join(result)


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

    curl_args = split(_normalize_curl_command(curl_command))

    if not curl_args or curl_args[0] != "curl":
        raise ValueError('A curl command must start with "curl"')

    parsed_args, argv = curl_parser.parse_known_args(curl_args[1:])

    url, unused = _select_url(curl_args[1:], parsed_args, argv)
    # Keep reporting every word that was not used: the unrecognized options
    # themselves and any positional candidate that turned out to be the
    # value of one of those options or an extra URL.
    argv = [arg for arg in argv if arg.startswith("-")] + unused

    if argv:
        msg = f"Unrecognized options: {', '.join(argv)}"
        if ignore_unknown_options:
            warnings.warn(msg, stacklevel=2)
        else:
            raise ValueError(msg)

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
