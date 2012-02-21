import codecs

from w3lib.encoding import resolve_encoding

def encoding_exists(encoding):
    """Returns ``True`` if encoding is valid, otherwise returns ``False``"""
    try:
        codecs.lookup(resolve_encoding(encoding))
    except LookupError:
        return False
    return True
