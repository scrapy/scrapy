from scrapy.utils.python import flatten
from scrapy.utils.decorator import deprecated

class XPathSelectorList(list):

    def __getslice__(self, i, j):
        return self.__class__(list.__getslice__(self, i, j))

    def select(self, xpath):
        return self.__class__(flatten([x.select(xpath) for x in self]))

    def re(self, regex):
        return flatten([x.re(regex) for x in self])

    def extract(self):
        return [x.extract() for x in self]

    def extract_unquoted(self):
        return [x.extract_unquoted() for x in self]

    @deprecated(use_instead='XPathSelectorList.select')
    def x(self, xpath):
        return self.select(xpath)
