from __future__ import annotations

import argparse
import re
import warnings
from http.cookies import SimpleCookie
from shlex import quote, split
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import urlparse, urlsplit, urlunsplit

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
curl_parser.add_argument("url")
curl_parser.add_argument("-H", "--header", dest="headers", action="append")
curl_parser.add_argument("-X", "--request", dest="method")
curl_parser.add_argument("-b", "--cookie", dest="cookies", action="append")
curl_parser.add_argument(
    "-d",
    "--data",
    "--data-raw",
    "--data-binary",
    "--data-ascii",
    dest="data",
    action=DataAction,
)
curl_parser.add_argument("--json", dest="json", action=DataAction)
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


def _parse_headers_and_cookies(
    parsed_args: argparse.Namespace,
) -> tuple[list[tuple[str, str | bytes | None]], dict[str, str]]:
    headers: list[tuple[str, str | bytes | None]] = []
    cookies: dict[str, str] = {}
    for header in parsed_args.headers or ():
        if header.lstrip().startswith(":"):
            # HTTP/2 pseudo-header (e.g. ":authority: example.org"), which
            # some browsers include when copying a request as cURL. It is
            # not a real header, and parsing it would produce a header with
            # an empty name.
            continue
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

    _add_option_headers(headers, parsed_args)

    return headers, cookies


def _add_option_headers(
    headers: list[tuple[str, str | bytes | None]],
    parsed_args: argparse.Namespace,
) -> None:
    """Add the headers implied by options such as -A/--user-agent.

    An explicit -H header wins over the value of the corresponding
    option, as it does in curl.
    """
    header_names = {name.lower() for name, _ in headers}
    if parsed_args.user_agent is not None and "user-agent" not in header_names:
        headers.append(("User-Agent", parsed_args.user_agent))
    if parsed_args.referer is not None and "referer" not in header_names:
        headers.append(("Referer", parsed_args.referer))
    if parsed_args.json is not None:
        if "content-type" not in header_names:
            headers.append(("Content-Type", "application/json"))
        if "accept" not in header_names:
            headers.append(("Accept", "application/json"))


_ANSI_C_QUOTED_RE = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.DOTALL)
# https://www.gnu.org/software/bash/manual/html_node/ANSI_002dC-Quoting.html
_ANSI_C_ESCAPE_RE = re.compile(
    r"\\(?:([abeEfnrtv\\'\"?])|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|c(\\\\?|.))"
    # A run of octal and hex escapes, each of them a byte.
    r"|((?:\\(?:[0-7]{1,3}|x[0-9A-Fa-f]{1,2}))+)",
    re.DOTALL,
)
_ANSI_C_SIMPLE_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}
# Maps the surrogates that the surrogateescape error handler uses for
# undecodable bytes to the Latin-1 characters of those bytes.
_SURROGATE_ESCAPES_TO_LATIN1 = {0xDC00 + byte: byte for byte in range(0x80, 0x100)}


def _decode_ansi_c_escape(match: re.Match[str]) -> str:
    simple, short_unicode, long_unicode, control, byte_escapes = match.groups()
    if simple is not None:
        return _ANSI_C_SIMPLE_ESCAPES.get(simple, simple)
    if control is not None:
        # \c\\ counts as \c followed by a single backslash.
        return "\x7f" if control == "?" else chr(ord(control[0]) & 0x1F)
    if byte_escapes is not None:
        data = bytes(
            int(escape[1:], 16) if escape[0] == "x" else int(escape, 8) & 0xFF
            for escape in byte_escapes.split("\\")[1:]
        )
        # Bash (printf %q) writes non-ASCII characters as their UTF-8 bytes,
        # while Firefox writes characters below U+0100 as \xHH, so bytes that
        # are not valid UTF-8 are read as Latin-1.
        return data.decode("utf-8", "surrogateescape").translate(
            _SURROGATE_ESCAPES_TO_LATIN1
        )
    return chr(int(short_unicode or long_unicode, 16))


def _decode_ansi_c_string(value: str) -> str:
    """Decode *value*, the contents of a Bash ``$'...'`` string."""
    decoded = _ANSI_C_ESCAPE_RE.sub(_decode_ansi_c_escape, value)
    # Bash cuts the string at the first NUL byte.
    decoded = decoded.partition("\0")[0]
    # Firefox writes characters above U+FFFF as a UTF-16 surrogate pair of
    # \u escapes; join them, and fail on unpaired surrogates.
    return decoded.encode("utf-16-le", "surrogatepass").decode("utf-16-le")


def _normalize_curl_command(curl_command: str) -> str:
    """Replace Bash ANSI-C quoted strings with their value quoted for shlex."""
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
            and not in_single_quote
            and not in_double_quote
            and (match := _ANSI_C_QUOTED_RE.match(curl_command, i))
        ):
            result.append(quote(_decode_ansi_c_string(match[1])))
            i = match.end()
            continue
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

    if argv:
        msg = f"Unrecognized options: {', '.join(argv)}"
        if ignore_unknown_options:
            warnings.warn(msg, stacklevel=2)
        else:
            raise ValueError(msg)

    url = parsed_args.url

    # curl automatically prepends 'http' if the scheme is missing, but Request
    # needs the scheme to work
    parsed_url = urlparse(url)
    if not parsed_url.scheme:
        url = "http://" + url

    # Data from the -d/--data-* and --json options forms a single payload.
    data = "&".join(part for part in (parsed_args.data, parsed_args.json) if part)

    if data and parsed_args.get:
        # With -G/--get, curl appends the data to the URL query string
        # instead of sending it in the body of a POST request.
        url_parts = urlsplit(url)
        query = f"{url_parts.query}&{data}" if url_parts.query else data
        url = urlunsplit(url_parts._replace(query=query))
        data = ""

    method = parsed_args.method or "GET"
    if parsed_args.head and not parsed_args.method:
        method = "HEAD"

    result: dict[str, Any] = {"method": method.upper(), "url": url}

    headers, cookies = _parse_headers_and_cookies(parsed_args)

    if headers:
        result["headers"] = headers
    if cookies:
        result["cookies"] = cookies
    if parsed_args.proxy:
        result["meta"] = {"proxy": parsed_args.proxy}
    if data:
        result["body"] = data
        if not parsed_args.method and not parsed_args.head:
            # if the "data" is specified but the "method" is not specified,
            # the default method is 'POST'
            result["method"] = "POST"

    return result
