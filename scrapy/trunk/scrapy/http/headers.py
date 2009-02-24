from scrapy.utils.datatypes import CaselessDict
from scrapy.utils.http import headers_dict_to_raw


class Headers(CaselessDict):
    def __init__(self, seq=None, encoding='utf-8'):
        self.encoding = encoding
        super(Headers, self).__init__(seq)

    def normkey(self, key):
        """Headers must not be unicode"""
        if isinstance(key, unicode):
            key = key.encode(self.encoding)
        return key.title()

    def normvalue(self, value):
        """Headers must not be unicode"""
        if isinstance(value, unicode):
            value = value.encode(self.encoding)
        return value

    def to_string(self):
        return headers_dict_to_raw(self)
