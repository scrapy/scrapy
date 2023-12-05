from base64 import b64encode
from typing import Any, List, MutableMapping, Optional, AnyStr, Sequence, Union, Mapping
from w3lib.util import to_bytes, to_unicode

HeadersDictInput = Mapping[bytes, Union[Any, Sequence[bytes]]]
HeadersDictOutput = MutableMapping[bytes, List[bytes]]


def headers_raw_to_dict(headers_raw: Optional[bytes]) -> Optional[HeadersDictOutput]:
    r"""
    Convert raw headers (single multi-line bytestring)
    to a dictionary.

    For example:

    >>> import w3lib.http
    >>> w3lib.http.headers_raw_to_dict(b"Content-type: text/html\n\rAccept: gzip\n\n")   # doctest: +SKIP
    {'Content-type': ['text/html'], 'Accept': ['gzip']}

    Incorrect input:

    >>> w3lib.http.headers_raw_to_dict(b"Content-typt gzip\n\n")
    {}
    >>>

    Argument is ``None`` (return ``None``):

    >>> w3lib.http.headers_raw_to_dict(None)
    >>>

    """

    if headers_raw is None:
        return None
    headers = headers_raw.splitlines()
    headers_tuples = [header.split(b":", 1) for header in headers]

    result_dict: HeadersDictOutput = {}
    for header_item in headers_tuples:
        if not len(header_item) == 2:
            continue

        item_key = header_item[0].strip()
        item_value = header_item[1].strip()

        if item_key in result_dict:
            result_dict[item_key].append(item_value)
        else:
            result_dict[item_key] = [item_value]

    return result_dict


def headers_dict_to_raw(headers_dict: Optional[HeadersDictInput]) -> Optional[bytes]:
    r"""
    Returns a raw HTTP headers representation of headers

    For example:

    >>> import w3lib.http
    >>> w3lib.http.headers_dict_to_raw({b'Content-type': b'text/html', b'Accept': b'gzip'}) # doctest: +SKIP
    'Content-type: text/html\\r\\nAccept: gzip'
    >>>

    Note that keys and values must be bytes.

    Argument is ``None`` (returns ``None``):

    >>> w3lib.http.headers_dict_to_raw(None)
    >>>

    """

    if headers_dict is None:
        return None
    raw_lines = []
    for key, value in headers_dict.items():
        if isinstance(value, bytes):
            raw_lines.append(b": ".join([key, value]))
        elif isinstance(value, (list, tuple)):
            for v in value:
                raw_lines.append(b": ".join([key, v]))
    return b"\r\n".join(raw_lines)


def basic_auth_header(
    username: AnyStr, password: AnyStr, encoding: str = "ISO-8859-1"
) -> bytes:
    """
    Return an `Authorization` header field value for `HTTP Basic Access Authentication (RFC 2617)`_

    >>> import w3lib.http
    >>> w3lib.http.basic_auth_header('someuser', 'somepass')
    'Basic c29tZXVzZXI6c29tZXBhc3M='

    .. _HTTP Basic Access Authentication (RFC 2617): http://www.ietf.org/rfc/rfc2617.txt

    """

    auth = f"{to_unicode(username)}:{to_unicode(password)}"
    # XXX: RFC 2617 doesn't define encoding, but ISO-8859-1
    # seems to be the most widely used encoding here. See also:
    # http://greenbytes.de/tech/webdav/draft-ietf-httpauth-basicauth-enc-latest.html
    return b"Basic " + b64encode(to_bytes(auth, encoding=encoding))
