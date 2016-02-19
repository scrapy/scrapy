"""Helper functions which doesn't fit anywhere else"""
import re
import hashlib
from importlib import import_module
from pkgutil import iter_modules

import six
from w3lib.html import replace_entities

from scrapy.utils.python import flatten, to_unicode
from scrapy.item import BaseItem


_ITERABLE_SINGLE_VALUES = dict, BaseItem, six.text_type, bytes


def arg_to_iter(arg):
    """Convert an argument to an iterable. The argument can be a None, single
    value, or an iterable.

    Exception: if arg is a dict, [arg] will be returned
    """
    if arg is None:
        return []
    elif not isinstance(arg, _ITERABLE_SINGLE_VALUES) and hasattr(arg, '__iter__'):
        return arg
    else:
        return [arg]


def load_object(path):
    """Load an object given its absolute object path, and return it.

    object can be a class, function, variable or an instance.
    path ie: 'scrapy.downloadermiddlewares.redirect.RedirectMiddleware'
    """

    try:
        dot = path.rindex('.')
    except ValueError:
        raise ValueError("Error loading object '%s': not a full path" % path)

    module, name = path[:dot], path[dot+1:]
    mod = import_module(module)

    try:
        obj = getattr(mod, name)
    except AttributeError:
        raise NameError("Module '%s' doesn't define any object named '%s'" % (module, name))

    return obj


def walk_modules(path):
    """Loads a module and all its submodules from the given module path and
    returns them. If *any* module throws an exception while importing, that
    exception is thrown back.

    For example: walk_modules('scrapy.utils')
    """

    mods = []
    mod = import_module(path)
    mods.append(mod)
    if hasattr(mod, '__path__'):
        for _, subpath, ispkg in iter_modules(mod.__path__):
            fullpath = path + '.' + subpath
            if ispkg:
                mods += walk_modules(fullpath)
            else:
                submod = import_module(fullpath)
                mods.append(submod)
    return mods


def extract_regex(regex, text, encoding='utf-8'):
    """Extract a list of unicode strings from the given text/encoding using the following policies:

    * if the regex contains a named group called "extract" that will be returned
    * if the regex contains multiple numbered groups, all those will be returned (flattened)
    * if the regex doesn't contain any group the entire regex matching is returned
    """

    if isinstance(regex, six.string_types):
        regex = re.compile(regex, re.UNICODE)

    try:
        strings = [regex.search(text).group('extract')]   # named group
    except:
        strings = regex.findall(text)    # full regex or numbered groups
    strings = flatten(strings)

    if isinstance(text, six.text_type):
        return [replace_entities(s, keep=['lt', 'amp']) for s in strings]
    else:
        return [replace_entities(to_unicode(s, encoding), keep=['lt', 'amp'])
                for s in strings]


def md5sum(file):
    """Calculate the md5 checksum of a file-like object without reading its
    whole content in memory.

    >>> from io import BytesIO
    >>> md5sum(BytesIO(b'file content to hash'))
    '784406af91dd5a54fbb9c84c2236595a'
    """
    m = hashlib.md5()
    while True:
        d = file.read(8096)
        if not d:
            break
        m.update(d)
    return m.hexdigest()

def rel_has_nofollow(rel):
    """Return True if link rel attribute has nofollow type"""
    return True if rel is not None and 'nofollow' in rel.split() else False
    
