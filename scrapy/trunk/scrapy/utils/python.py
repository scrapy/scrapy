"""
This module contains essential stuff that should've come with Python itself ;)

It also contains functions (or functionality) which is in Python versions
higher than 2.5 which is the lowest version supported by Scrapy.

"""
import re
import os
import fnmatch
import inspect
from shutil import copy2, copystat
from sgmllib import SGMLParser

class FixedSGMLParser(SGMLParser):
    """The SGMLParser that comes with Python has a bug in the convert_charref()
    method. This is the same class with the bug fixed"""

    def convert_charref(self, name):
        """This method fixes a bug in Python's SGMLParser."""
        try:
            n = int(name)
        except ValueError:
            return
        if not 0 <= n <= 127 : # ASCII ends at 127, not 255
            return
        return self.convert_codepoint(n)


def flatten(x):
    """flatten(sequence) -> list

    Returns a single, flat list which contains all elements retrieved
    from the sequence and all recursively contained sub-sequences
    (iterables).

    Examples:
    >>> [1, 2, [3,4], (5,6)]
    [1, 2, [3, 4], (5, 6)]
    >>> flatten([[[1,2,3], (42,None)], [4,5], [6], 7, (8,9,10)])
    [1, 2, 3, 42, None, 4, 5, 6, 7, 8, 9, 10]"""

    result = []
    for el in x:
        if hasattr(el, "__iter__"):
            result.extend(flatten(el))
        else:
            result.append(el)
    return result


def unique(list_, key=lambda x: x):
    """efficient function to uniquify a list preserving item order"""
    seen = {}
    result = []
    for item in list_:
        seenkey = key(item)
        if seenkey in seen: 
            continue
        seen[seenkey] = 1
        result.append(item)
    return result


def str_to_unicode(text, encoding='utf-8'):
    """Return the unicode representation of text in the given encoding. Unlike
    .encode(encoding) this function can be applied directly to a unicode
    object without the risk of double-decoding problems (which can happen if
    you don't use the default 'ascii' encoding)
    """
    
    if isinstance(text, str):
        return text.decode(encoding)
    elif isinstance(text, unicode):
        return text
    else:
        raise TypeError('str_to_unicode must receive a str or unicode object, got %s' % type(text).__name__)

def unicode_to_str(text, encoding='utf-8'):
    """Return the str representation of text in the given encoding. Unlike
    .encode(encoding) this function can be applied directly to a str
    object without the risk of double-decoding problems (which can happen if
    you don't use the default 'ascii' encoding)
    """

    if isinstance(text, unicode):
        return text.encode(encoding)
    elif isinstance(text, str):
        return text
    else:
        raise TypeError('unicode_to_str must receive a unicode or str object, got %s' % type(text).__name__)

def re_rsearch(pattern, text, chunk_size=1024):
    """
    This function does a reverse search in a text using a regular expression
    given in the attribute 'pattern'.
    Since the re module does not provide this functionality, we have to find for
    the expression into chunks of text extracted from the end (for the sake of efficiency).
    At first, a chunk of 'chunk_size' kilobytes is extracted from the end, and searched for
    the pattern. If the pattern is not found, another chunk is extracted, and another
    search is performed.
    This process continues until a match is found, or until the whole file is read.
    In case the pattern wasn't found, None is returned, otherwise it returns a tuple containing
    the start position of the match, and the ending (regarding the entire text).
    """
    def _chunk_iter():
        offset = len(text)
        while True:
            offset -= (chunk_size * 1024)
            if offset <= 0:
                break
            yield (text[offset:], offset)
        yield (text, 0)

    pattern = re.compile(pattern) if isinstance(pattern, basestring) else pattern
    for chunk, offset in _chunk_iter():
        matches = [match for match in pattern.finditer(chunk)]
        if matches:
            return (offset + matches[-1].span()[0], offset + matches[-1].span()[1])
    return None

def memoizemethod(cacheattr):
    """A memoize decorator for methods, which caches calls to instance methods
    into an attribute of the same instance (which must be dict). Calls with
    different arguments will be cached in different buckets.

    This has the advantage that, when the instance is collected (by the garbage
    collector) the cache is collected as well.

    Descriptors are required to implement this functionality. See why at:
    http://blog.ianbicking.org/2008/10/24/decorators-and-descriptors/

    Example:

    class A(object):
            def __init__(self):
            self.cache = {}
            @memoizemethod('cache')
        def calculate(self, arg1, arg2):
            # expensive code here

    All calls to calculate() method of A instances will be cached in their
    cache (instance) attribute, which must be a dict.

    """

    class MemoizeMethod(object):

        def __init__(self, function):
            self.function = function

        def __get__(self, obj, objtype=None):
            if obj is None:
                return self
            new_func = self.function.__get__(obj, objtype)
            return self.__class__(new_func)

        def __call__(self, *args, **kwargs):
            method = self.function
            cache = getattr(method.im_self, cacheattr)
            key = (method.im_func, tuple(args), frozenset(kwargs.items()))
            if key not in cache:
                cache[key] = method(*args, **kwargs)
            return cache[key]

    return MemoizeMethod

_BINARYCHARS = set(map(chr, range(32))) - set(["\0", "\t", "\n", "\r"])

def isbinarytext(text):
    """Return True if the given text is considered binary, or false
    otherwise, by looking for binary bytes at their chars
    """
    assert isinstance(text, str), "text must be str, got '%s'" % type(text).__name__
    return any(c in _BINARYCHARS for c in text)


# ----- shutil.copytree function from Python 2.6 adds ignore argument ---- #

try:
    WindowsError
except NameError:
    WindowsError = None

class Error(EnvironmentError):
    pass

def ignore_patterns(*patterns):
    def _ignore_patterns(path, names):
        ignored_names = []
        for pattern in patterns:
            ignored_names.extend(fnmatch.filter(names, pattern))
        return set(ignored_names)
    return _ignore_patterns

def copytree(src, dst, symlinks=False, ignore=None):
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    os.makedirs(dst)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks, ignore)
            else:
                copy2(srcname, dstname)
            # XXX What about devices, sockets etc.?
        except (IOError, os.error), why:
            errors.append((srcname, dstname, str(why)))
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except Error, err:
            errors.extend(err.args[0])
    try:
        copystat(src, dst)
    except OSError, why:
        if WindowsError is not None and isinstance(why, WindowsError):
            # Copying file access times may fail on Windows
            pass
        else:
            errors.extend((src, dst, str(why)))
    if errors:
        raise Error, errors

# ----- end of shutil.copytree function from Python 2.6 ---- #


def get_func_args(func):
    """Return the argument name list of a callable"""
    if inspect.isfunction(func):
        func_args, _, _, _ = inspect.getargspec(func)
    elif hasattr(func, '__call__'):
        try:
            func_args, _, _, _ = inspect.getargspec(func.__call__)
        except Exception:
            func_args = []
    else:
        raise TypeError('%s is not callable' % type(func))
    return func_args
