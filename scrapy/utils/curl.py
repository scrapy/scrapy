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
curl_parser.add_argument(
    "-d",
    "--data",
    "--data-raw",
    "--data-ascii",
    "--data-binary",
    dest="data",
    action=DataAction,
)
curl_parser.add_argument("--json", dest="json", action="append")
curl_parser.add_argument("-u", "--user", dest="auth")
curl_parser.add_argument("-A", "--user-agent", dest="user_agent")
curl_parser.add_argument("-e", "--referer", dest="referer")
curl_parser.add_argument("-x", "--proxy", dest="proxy")
curl_parser.add_argument("-G", "--get", dest="get", action="store_true")
curl_parser.add_argument("-I", "--head", dest="head", action="store_true")


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


def _option_headers(
    parsed_args: argparse.Namespace,
    headers: list[tuple[str, str | bytes | None]],
) -> None:
    # curl replaces a header that an option sets when -H provides it
    header_names = {name.lower() for name, _ in headers}
    options = [
        ("User-Agent", parsed_args.user_agent),
        ("Referer", parsed_args.referer),
    ]
    if parsed_args.json is not None:
        options += [
            ("Content-Type", "application/json"),
            ("Accept", "application/json"),
        ]
    headers.extend(
        (name, value)
        for name, value in options
        if value is not None and name.lower() not in header_names
    )


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
        if not name:
            # an HTTP/2 pseudo-header (":authority: ..."), not a real header
            continue
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

    _option_headers(parsed_args, headers)

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


def _select_url(
    curl_args: list[str], parsed_args: argparse.Namespace, argv: list[str]
) -> str:
    # argparse does not know whether an unrecognized option takes a value,
    # so such a value lands in urls and the actual URL can end up in argv.
    # A positional that directly follows an unrecognized option is its
    # value; every other positional is a URL candidate.
    unrecognized = {arg for arg in argv if arg.startswith("-")}
    positionals = set(parsed_args.urls)
    positionals.update(arg for arg in argv if not arg.startswith("-"))
    urls = [
        arg
        for i, arg in enumerate(curl_args[1:], start=1)
        if arg in positionals and curl_args[i - 1] not in unrecognized
    ]
    if not urls:
        # every positional followed an unrecognized option, so those
        # options did not take a value after all
        urls = [arg for arg in curl_args[1:] if arg in positionals]
    if not urls:
        curl_parser.error("the following arguments are required: url")
    # an unrecognized flag can still precede the URL, so prefer a
    # candidate that has a scheme
    return next((u for u in urls if "://" in u), urls[0])


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

    if argv:
        msg = f"Unrecognized options: {', '.join(argv)}"
        if ignore_unknown_options:
            warnings.warn(msg, stacklevel=2)
        else:
            raise ValueError(msg)

    url = _select_url(curl_args, parsed_args, argv)

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
    # --json payloads merge into the body the way -d values do
    data = "&".join(filter(None, (parsed_args.data, *(parsed_args.json or ()))))
    if data and parsed_args.get:
        # -G appends the data to the URL query instead of sending a body
        sep = "&" if urlparse(url).query else "?"
        result["url"] = f"{url}{sep}{data}"
    elif data:
        result["body"] = data
        if not parsed_args.method:
            # if the "data" is specified but the "method" is not specified,
            # the default method is 'POST'
            result["method"] = "POST"
    if parsed_args.head and not parsed_args.method:
        result["method"] = "HEAD"
    if parsed_args.proxy:
        proxy = parsed_args.proxy
        result["meta"] = {"proxy": proxy if "://" in proxy else f"http://{proxy}"}

    return result
