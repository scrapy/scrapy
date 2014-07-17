"""
This module contains essential stuff that should've come with Python itself ;)

It also contains functions (or functionality) which is in Python versions
higher than 2.5 which used to be the lowest version supported by Scrapy.

"""
import os
import re
import inspect
import weakref
import errno
import six
from functools import partial, wraps


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
    seen = set()
    result = []
    for item in list_:
        seenkey = key(item)
        if seenkey in seen:
            continue
        seen.add(seenkey)
        result.append(item)
    return result


def str_to_unicode(text, encoding=None, errors='strict'):
    """Return the unicode representation of text in the given encoding. Unlike
    .encode(encoding) this function can be applied directly to a unicode
    object without the risk of double-decoding problems (which can happen if
    you don't use the default 'ascii' encoding)
    """

    if encoding is None:
        encoding = 'utf-8'
    if isinstance(text, str):
        return text.decode(encoding, errors)
    elif isinstance(text, unicode):
        return text
    else:
        raise TypeError('str_to_unicode must receive a str or unicode object, got %s' % type(text).__name__)

def unicode_to_str(text, encoding=None, errors='strict'):
    """Return the str representation of text in the given encoding. Unlike
    .encode(encoding) this function can be applied directly to a str
    object without the risk of double-decoding problems (which can happen if
    you don't use the default 'ascii' encoding)
    """

    if encoding is None:
        encoding = 'utf-8'
    if isinstance(text, unicode):
        return text.encode(encoding, errors)
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

def memoizemethod_noargs(method):
    """Decorator to cache the result of a method (without arguments) using a
    weak reference to its object
    """
    cache = weakref.WeakKeyDictionary()
    @wraps(method)
    def new_method(self, *args, **kwargs):
        if self not in cache:
            cache[self] = method(self, *args, **kwargs)
        return cache[self]
    return new_method

_BINARYCHARS = set(map(chr, range(32))) - set(["\0", "\t", "\n", "\r"])

def isbinarytext(text):
    """Return True if the given text is considered binary, or false
    otherwise, by looking for binary bytes at their chars
    """
    assert isinstance(text, str), "text must be str, got '%s'" % type(text).__name__
    return any(c in _BINARYCHARS for c in text)

def get_func_args(func, stripself=False):
    """Return the argument name list of a callable"""
    if inspect.isfunction(func):
        func_args, _, _, _ = inspect.getargspec(func)
    elif inspect.isclass(func):
        return get_func_args(func.__init__, True)
    elif inspect.ismethod(func):
        return get_func_args(func.__func__, True)
    elif inspect.ismethoddescriptor(func):
        return []
    elif isinstance(func, partial):
        return [x for x in get_func_args(func.func)[len(func.args):]
                if not (func.keywords and x in func.keywords)]
    elif hasattr(func, '__call__'):
        if inspect.isroutine(func):
            return []
        elif getattr(func, '__name__', None) == '__call__':
            return []
        else:
            return get_func_args(func.__call__, True)
    else:
        raise TypeError('%s is not callable' % type(func))
    if stripself:
        func_args.pop(0)
    return func_args

def get_spec(func):
    """Returns (args, kwargs) tuple for a function
    >>> import re
    >>> get_spec(re.match)
    (['pattern', 'string'], {'flags': 0})

    >>> class Test(object):
    ...     def __call__(self, val):
    ...         pass
    ...     def method(self, val, flags=0):
    ...         pass

    >>> get_spec(Test)
    (['self', 'val'], {})

    >>> get_spec(Test.method)
    (['self', 'val'], {'flags': 0})

    >>> get_spec(Test().method)
    (['self', 'val'], {'flags': 0})
    """

    if inspect.isfunction(func) or inspect.ismethod(func):
        spec = inspect.getargspec(func)
    elif hasattr(func, '__call__'):
        spec = inspect.getargspec(func.__call__)
    else:
        raise TypeError('%s is not callable' % type(func))

    defaults = spec.defaults or []

    firstdefault = len(spec.args) - len(defaults)
    args = spec.args[:firstdefault]
    kwargs = dict(zip(spec.args[firstdefault:], defaults))
    return args, kwargs

def equal_attributes(obj1, obj2, attributes):
    """Compare two objects attributes"""
    # not attributes given return False by default
    if not attributes:
        return False

    for attr in attributes:
        # support callables like itemgetter
        if callable(attr):
            if not attr(obj1) == attr(obj2):
                return False
        else:
            # check that objects has attribute
            if not hasattr(obj1, attr):
                return False
            if not hasattr(obj2, attr):
                return False
            # compare object attributes
            if not getattr(obj1, attr) == getattr(obj2, attr):
                return False
    # all attributes equal
    return True


class WeakKeyCache(object):

    def __init__(self, default_factory):
        self.default_factory = default_factory
        self._weakdict = weakref.WeakKeyDictionary()

    def __getitem__(self, key):
        if key not in self._weakdict:
            self._weakdict[key] = self.default_factory(key)
        return self._weakdict[key]


def stringify_dict(dct_or_tuples, encoding='utf-8', keys_only=True):
    """Return a (new) dict with the unicode keys (and values if, keys_only is
    False) of the given dict converted to strings. `dct_or_tuples` can be a
    dict or a list of tuples, like any dict constructor supports.
    """
    d = {}
    for k, v in six.iteritems(dict(dct_or_tuples)):
        k = k.encode(encoding) if isinstance(k, unicode) else k
        if not keys_only:
            v = v.encode(encoding) if isinstance(v, unicode) else v
        d[k] = v
    return d

def is_writable(path):
    """Return True if the given path can be written (if it exists) or created
    (if it doesn't exist)
    """
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    else:
        return os.access(os.path.dirname(path), os.W_OK)

def setattr_default(obj, name, value):
    """Set attribute value, but only if it's not already set. Similar to
    setdefault() for dicts.
    """
    if not hasattr(obj, name):
        setattr(obj, name, value)


def retry_on_eintr(function, *args, **kw):
    """Run a function and retry it while getting EINTR errors"""
    while True:
        try:
            return function(*args, **kw)
        except IOError as e:
            if e.errno != errno.EINTR:
                raise
