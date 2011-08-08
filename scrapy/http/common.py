import warnings
from scrapy.exceptions import ScrapyDeprecationWarning

def deprecated_setter(setter, attrname):
    def newsetter(self, value):
        c = self.__class__.__name__
        warnings.warn("Don't modify %s.%s attribute, use %s.replace() instead" % \
            (c, attrname, c), ScrapyDeprecationWarning, stacklevel=2)
        return setter(self, value)
    return newsetter
