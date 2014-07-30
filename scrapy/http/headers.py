import six
from w3lib.http import headers_dict_to_raw
from scrapy.utils.datatypes import CaselessDict


class Headers(CaselessDict):
    """Case insensitive http headers dictionary"""

    def __init__(self, seq=None, encoding='utf-8'):
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

    def _tobytes(self, x):
        if isinstance(x, bytes):
            return x
        elif isinstance(x, six.text_type):
            return x.encode(self.encoding)
        elif isinstance(x, int):
            return six.text_type(x).encode(self.encoding)
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

    def __copy__(self):
        return self.__class__(self)
    copy = __copy__


