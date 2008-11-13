import inspect

from scrapy.contrib.adaptors.extraction import extract, extract_unquoted, ExtractImages
from scrapy.contrib.adaptors.markup import remove_tags, remove_root, unquote
from scrapy.contrib.adaptors.misc import to_unicode, clean_spaces, strip_list, drop_empty, canonicalize_urls, delist, Regex
from scrapy.utils.python import unique, flatten

def adaptor_gen(*args):
    subadaptors = []
    arg_mappings = []
    for subadaptor in args:
        if callable(subadaptor):
            if inspect.isfunction(subadaptor):
                func_args, varargs, varkw, defaults = inspect.getargspec(subadaptor)
                arg_mappings.append(func_args[1:])
            else:
                arg_mappings.append([])
            subadaptors.append(subadaptor)
    
    def _adaptor(value, **kwargs):
        for index, subadaptor in enumerate(subadaptors):
            adaptor_args = dict((key, val) for key, val in kwargs.items() if key in arg_mappings[index])
            value = subadaptor(value, **adaptor_args)
        return value

    return _adaptor
