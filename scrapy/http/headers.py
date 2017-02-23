import six
from w3lib.http import headers_dict_to_raw
from scrapy.utils.datatypes import CaselessDict
from scrapy.utils.python import to_unicode


class Headers(CaselessDict):
    """Case insensitive http headers dictionary"""

    def __init__(self, seq=None, encoding=None):
        """Initialize headers object.

        Parameters
        ----------
        seq : items, optional
            Headers items.
        encoding : str, optional
            Encoding used for encoding/decoding header values. If not given,
            default for encoding is UTF-8 and for decoding UTF-8 with
            ISO-8859-1 fallback.

        """
        self.encoding = encoding
        super(Headers, self).__init__(seq)

    def normkey(self, key):
        """Normalize key to bytes"""
        return self._tobytes(key.title())

    def normvalue(self, value):
        """Normalize values to bytes"""
        if value is None:
            value = []
        elif isinstance(value, (six.text_type, bytes)):
            value = [value]
        elif not hasattr(value, '__iter__'):
            value = [value]

        return [self._tobytes(x) for x in value]

    def _tobytes(self, x, default_encoding='utf-8'):
        encoding = self.encoding or default_encoding
        if isinstance(x, bytes):
            return x
        elif isinstance(x, six.text_type):
            return x.encode(encoding)
        elif isinstance(x, int):
            return six.text_type(x).encode(encoding)
        else:
            raise TypeError('Unsupported value type: {}'.format(type(x)))

    def __getitem__(self, key):
        try:
            return super(Headers, self).__getitem__(key)[-1]
        except IndexError:
            return None

    def get(self, key, def_val=None):
        try:
            return super(Headers, self).get(key, def_val)[-1]
        except IndexError:
            return None

    def getlist(self, key, def_val=None):
        try:
            return super(Headers, self).__getitem__(key)
        except KeyError:
            if def_val is not None:
                return self.normvalue(def_val)
            return []

    def setlist(self, key, list_):
        self[key] = list_

    def setlistdefault(self, key, default_list=()):
        return self.setdefault(key, default_list)

    def appendlist(self, key, value):
        lst = self.getlist(key)
        lst.extend(self.normvalue(value))
        self[key] = lst

    def items(self):
        return list(self.iteritems())

    def iteritems(self):
        return ((k, self.getlist(k)) for k in self.keys())

    def values(self):
        return [self[k] for k in self.keys()]

    def to_string(self):
        return headers_dict_to_raw(self)

    def to_unicode_dict(self, encoding=None):
        """ Return headers as a CaselessDict with unicode keys
        and unicode values. Multiple values are joined with ','.

        Parameters
        ----------
        encoding : str or list, optional
            A encoding or list of encodings to use for decoding headers. If an
            encoding was passed in the constructor, that value is used for
            decoding bytes into unicod strings. Otherwise attempts to decode
            the values using UTF-8 and fallbacks to ISO-8859-1.

        """
        encoding = encoding or self.encoding
        if encoding is None:
            encoding_list = ['utf-8', 'iso-8859-1']
        elif isinstance(encoding, (list, tuple)):
            encoding_list = encoding
        else:
            encoding_list = [encoding]

        return CaselessDict(
            (self._decode(key, *encoding_list),
             self._decode(b','.join(value), *encoding_list))
            for key, value in self.items()
        )

    def _decode(self, value, *encodings):
        for encoding in encodings[:-1]:
            try:
                return to_unicode(value, encoding=encoding)
            except UnicodeDecodeError:
                pass
        return to_unicode(value, encoding=encodings[-1])

    def __copy__(self):
        return self.__class__(self)
    copy = __copy__
