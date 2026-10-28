from __future__ import annotations

import argparse
import warnings
from http.cookies import SimpleCookie
from shlex import quote, split
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
curl_parser.add_argument("url")
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
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
_ANSI_C_HEX_ESCAPES = {"x": 2, "u": 4, "U": 8}
_HEX_DIGITS = "0123456789abcdefABCDEF"
_OCT_DIGITS = "01234567"


def _find_ansi_c_quote_end(curl_command: str, start: int) -> int | None:
    """Return the index of the quote that closes a ``$'...'`` string."""
    i = start
    while i < len(curl_command):
        if curl_command[i] == "\\":
            i += 2
        elif curl_command[i] == "'":
            return i
        else:
            i += 1
    return None


def _decode_ansi_c_escape(value: str, escape: str, i: int) -> tuple[bytes, int]:
    """Decode the escape ``<backslash><escape>`` whose arguments start at ``value[i]``.

    Return the decoded bytes and the index right after the escape.
    """
    if escape in _ANSI_C_SIMPLE_ESCAPES:
        return _ANSI_C_SIMPLE_ESCAPES[escape].encode(), i
    if escape in _OCT_DIGITS:
        digits = escape
        while len(digits) < 3 and i < len(value) and value[i] in _OCT_DIGITS:
            digits += value[i]
            i += 1
        return bytes([int(digits, 8) & 0xFF]), i
    if escape in _ANSI_C_HEX_ESCAPES:
        digits = ""
        while (
            len(digits) < _ANSI_C_HEX_ESCAPES[escape]
            and i < len(value)
            and value[i] in _HEX_DIGITS
        ):
            digits += value[i]
            i += 1
        if digits and escape == "x":
            return bytes([int(digits, 16)]), i
        if digits:
            return chr(int(digits, 16)).encode(errors="surrogatepass"), i
    elif escape == "c" and i < len(value):
        return bytes([ord(value[i]) & 0x1F]), i + 1
    # Unknown escapes are kept as is.
    return f"\\{escape}".encode(), i


def _decode_ansi_c_string(value: str) -> str:
    """Decode the backslash escapes of a Bash ``$'...'`` string.

    See https://www.gnu.org/software/bash/manual/html_node/ANSI_002dC-Quoting.html
    """
    # \\xHH and \\nnn produce raw bytes, like in Bash, so build bytes and
    # decode them at the end.
    result = bytearray()
    i = 0
    while i < len(value):
        char = value[i]
        if char != "\\" or i + 1 == len(value):
            result += char.encode()
            i += 1
            continue
        decoded, i = _decode_ansi_c_escape(value, value[i + 1], i + 2)
        result += decoded
    try:
        return result.decode()
    except UnicodeDecodeError:
        return result.decode("latin-1")


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
            end = _find_ansi_c_quote_end(curl_command, i + 2)
            if end is None:
                # Unterminated: leave it for shlex to report.
                result.append("'")
                in_single_quote = True
                i += 1
            else:
                result.append(quote(_decode_ansi_c_string(curl_command[i + 2 : end])))
                i = end
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
