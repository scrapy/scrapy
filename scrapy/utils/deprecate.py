"""Some helpers for deprecation messages"""

import warnings

from scrapy.exceptions import ScrapyDeprecationWarning

def attribute(obj, oldattr, newattr, version='0.12'):
    cname = obj.__class__.__name__
    warnings.warn("%s.%s attribute is deprecated and will be no longer supported "
        "in Scrapy %s, use %s.%s attribute instead" % \
        (cname, oldattr, version, cname, newattr), ScrapyDeprecationWarning, stacklevel=3)


def warn_when_subclassed(mro_len, message, category=ScrapyDeprecationWarning):
    """
    Return a metaclass that causes classes to
    issue a warning when they are subclassed.
    """
    class Metaclass(type):
        def __init__(cls, name, bases, clsdict):
            if len(cls.mro()) > mro_len:
                warnings.warn(message, category, stacklevel=2)
            super(Metaclass, cls).__init__(name, bases, clsdict)
    return Metaclass

