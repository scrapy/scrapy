"""
Auxiliary functions which doesn't fit anywhere else
"""
from __future__ import with_statement
from contextlib import closing

import os
import re
import gzip
import hashlib
import csv

from twisted.internet import defer

from scrapy.utils.python import flatten, unicode_to_str
from scrapy.utils.markup import remove_entities
from scrapy.utils.defer import defer_succeed

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


def md5sum(buffer):
    """Calculate the md5 checksum of a file

    >>> from StringIO import StringIO
    >>> md5sum(StringIO('file content to hash'))
    '784406af91dd5a54fbb9c84c2236595a'

    """
    m = hashlib.md5()
    buffer.seek(0)
    while 1:
        d = buffer.read(8096)
        if not d:
            break
        m.update(d)
    return m.hexdigest()


def gzip_file(logfile):
    """Gzip a file in place, just like gzip unix command

    >>> import gzip
    >>> import tempfile
    >>> logfile = tempfile.mktemp()
    >>> handle = open(logfile, 'wb')
    >>> handle.write('something to compress')
    >>> handle.close()
    >>> logfile_gz = gzip_file(logfile)
    >>> gzip.open(logfile_gz).read()
    'something to compress'
    """
    logfile_gz = '%s.gz' % logfile
    with closing(gzip.open(logfile_gz, 'wb')) as f_out:
        with open(logfile) as f_in:
            f_out.writelines(f_in)
    os.remove(logfile)
    return logfile_gz


