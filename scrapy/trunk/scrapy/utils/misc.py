"""
Auxiliary functions which doesn't fit anywhere else
"""
from __future__ import with_statement

import re
import string
import hashlib
import csv

from twisted.internet import defer

from scrapy.utils.python import flatten, unicode_to_str
from scrapy.utils.markup import remove_entities
from scrapy.utils.defer import defer_succeed

def arg_to_list(arg):
    """Convert an argument to list, so that it can be iterated. The argument
    can be a None, single value, or an iterable.

    This is meant to be used in functions for arguments which can be either
    None, single valued or multi-valued.
    """
    if arg is None:
        return []
    elif hasattr(arg, '__iter__'):
        return list(arg)
    else:
        return [arg]

def arg_to_iter(arg):
    """Convert an argument to an iterable. The argument can be a None, single
    value, or an iterable.
    """
    if arg is None:
        return []
    elif hasattr(arg, '__iter__'):
        return arg
    else:
        return [arg]

def dict_updatedefault(D, E, **F):
    """
    updatedefault(D, E, **F) -> None.

    Update D from E and F: for k in E: D.setdefault(k, E[k])
    (if E has keys else: for (k, v) in E: D.setdefault(k, v))
    then: for k in F: D.setdefault(k, F[k])
    """
    for k in E:
        if isinstance(k, tuple):
            k, v = k
        else:
            v = E[k]
        D.setdefault(k, v)

    for k in F:
        D.setdefault(k, F[k])

def memoize(cache, hash):
    def decorator(func):
        def wrapper(*args, **kwargs):
            key = hash(*args, **kwargs)
            if key in cache:
                return defer_succeed(cache[key])

            def _store(_):
                cache[key] = _
                return _

            result = func(*args, **kwargs)
            if isinstance(result, defer.Deferred):
                return result.addBoth(_store)
            cache[key] = result
            return result
        return wrapper
    return decorator

def stats_getpath(dict_, path, default=None):
    for key in path.split('/'):
        if key in dict_:
            dict_ = dict_[key]
        else:
            return default
    return dict_

def load_object(path):
    """Load an object given its absolute object path, and return it.

    object can be a class, function, variable o instance.
    path ie: 'scrapy.contrib.downloadermiddelware.redirect.RedirectMiddleware'
    """

    try:
        dot = path.rindex('.')
    except ValueError:
        raise ValueError, "Error loading object '%s': not a full path" % path

    module, name = path[:dot], path[dot+1:]
    try:
        mod = __import__(module, {}, {}, [''])
    except ImportError, e:
        raise ImportError, "Error loading object '%s': %s" % (path, e)

    try:
        obj = getattr(mod, name)
    except AttributeError:
        raise NameError, "Module '%s' doesn't define any object named '%s'" % (module, name)

    return obj
load_class = load_object # backwards compatibility, but isnt going to be available for too long.

def extract_regex(regex, text, encoding):
    """Extract a list of unicode strings from the given text/encoding using the following policies:

    * if the regex contains a named group called "extract" that will be returned
    * if the regex contains multiple numbered groups, all those will be returned (flattened)
    * if the regex doesn't contain any group the entire regex matching is returned
    """

    if isinstance(regex, basestring):
        regex = re.compile(regex)

    try:
        strings = [regex.search(text).group('extract')]   # named group
    except:
        strings = regex.findall(text)    # full regex or numbered groups
    strings = flatten(strings)

    if isinstance(text, unicode):
        return [remove_entities(s, keep=['lt', 'amp']) for s in strings]
    else:
        return [remove_entities(unicode(s, encoding), keep=['lt', 'amp']) for s in strings]

def hash_values(*values):
    """Hash a series of non-None values.

    For example:
    >>> hash_values('some', 'values', 'to', 'hash')
    'f37f5dc65beaaea35af05e16e26d439fd150c576'
    """
    hash = hashlib.sha1()
    for value in values:
        if value is None:
            message = "hash_values was passed None at argument index %d" % list(values).index(None)
            raise ValueError(message)
        hash.update(value)
    return hash.hexdigest()


def render_templatefile(path, **kwargs):
    with open(path, 'rb') as file:
        raw = file.read()

    content = string.Template(raw).substitute(**kwargs)

    with open(path, 'wb') as file:
        file.write(content)


def items_to_csv(file, items, delimiter=';', headers=None):
    """
    This function takes a list of items and stores their attributes
    in a csv file given in 'file' (which can be either a descriptor, or a filename).
    The saved attributes are either the ones found in the 'headers' parameter
    (if specified) or the first item's list of public attributes.
    The written file will be encoded as utf-8.
    """
    if not items or not hasattr(items, '__iter__'):
        return

    if isinstance(file, basestring):
        file = open(file, 'ab+')
    csv_file = csv.writer(file, delimiter=delimiter, quoting=csv.QUOTE_ALL)
    header = headers or sorted([key for key in items[0].__dict__.keys() if not key.startswith('_')])
    if not file.tell():
        csv_file.writerow(header)

    for item in items:
        row = []
        for attrib in header:
            value = getattr(item, attrib, None)
            value = unicode_to_str(value) if isinstance(value, basestring) else value
            row.append(value)
        csv_file.writerow(row)


CAMELCASE_INVALID_CHARS = re.compile('[^a-zA-Z]')
def string_camelcase(string):
    """ Convert a word  to its CamelCase version and remove invalid chars

    >>> string_camelcase('lost-pound')
    'LostPound'

    >>> string_camelcase('missing_images')
    'MissingImages'

    """
    return CAMELCASE_INVALID_CHARS.sub('', string.title())

