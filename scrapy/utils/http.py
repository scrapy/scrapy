from base64 import urlsafe_b64encode

def headers_raw_to_dict(headers_raw):
    """
    Convert raw headers (single multi-line string)
    to the dictionary.

    For example:
    >>> headers_raw_to_dict("Content-type: text/html\\n\\rAccept: gzip\\n\\n")
    {'Content-type': ['text/html'], 'Accept': ['gzip']}

    Incorrect input:
    >>> headers_raw_to_dict("Content-typt gzip\\n\\n")
    {}

    Argument is None:
    >>> headers_raw_to_dict(None)
    """
    if headers_raw is None:
        return None
    return dict([
        (header_item[0].strip(), [header_item[1].strip()])
        for header_item
        in [
            header.split(':', 1)
            for header
            in headers_raw.splitlines()]
        if len(header_item) == 2])


def headers_dict_to_raw(headers_dict):
    """
    Returns a raw HTTP headers representation of headers

    For example:
    >>> headers_dict_to_raw({'Content-type': 'text/html', 'Accept': 'gzip'})
    'Content-type: text/html\\r\\nAccept: gzip'
    >>> from twisted.python.util import InsensitiveDict
    >>> td = InsensitiveDict({'Content-type': ['text/html'], 'Accept': ['gzip']})
    >>> headers_dict_to_raw(td)
    'Content-type: text/html\\r\\nAccept: gzip'

    Argument is None:
    >>> headers_dict_to_raw(None)

    """
    if headers_dict is None:
        return None
    raw_lines = []
    for key, value in headers_dict.items():
        if isinstance(value, (str, unicode)):
            raw_lines.append("%s: %s" % (key, value))
        elif isinstance(value, (list, tuple)):
            for v in value:
                raw_lines.append("%s: %s" % (key, v))
    return '\r\n'.join(raw_lines)


def basic_auth_header(username, password):
    """Return `Authorization` header for HTTP Basic Access Authentication (RFC 2617)"""
    return 'Basic ' + urlsafe_b64encode("%s:%s" % (username, password))
