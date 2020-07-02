"""Helper functions which don't fit anywhere else"""
import ast
import inspect
import os
import re
import hashlib
import warnings
from contextlib import contextmanager
from importlib import import_module
from pkgutil import iter_modules
from textwrap import dedent

from w3lib.html import replace_entities

from scrapy.utils.datatypes import LocalWeakReferencedCache
from scrapy.utils.python import flatten, to_unicode
from scrapy.item import _BaseItem


_ITERABLE_SINGLE_VALUES = dict, _BaseItem, str, bytes


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

    object can be the import path of a class, function, variable or an
    instance, e.g. 'scrapy.downloadermiddlewares.redirect.RedirectMiddleware'
    """

    try:
        dot = path.rindex('.')
    except ValueError:
        raise ValueError("Error loading object '%s': not a full path" % path)

    module, name = path[:dot], path[dot + 1:]
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

    if isinstance(regex, str):
        regex = re.compile(regex, re.UNICODE)

    try:
        strings = [regex.search(text).group('extract')]   # named group
    except Exception:
        strings = regex.findall(text)    # full regex or numbered groups
    strings = flatten(strings)

    if isinstance(text, str):
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
    return rel is not None and 'nofollow' in rel.split()


def create_instance(objcls, settings, crawler, *args, **kwargs):
    """Construct a class instance using its ``from_crawler`` or
    ``from_settings`` constructors, if available.

    At least one of ``settings`` and ``crawler`` needs to be different from
    ``None``. If ``settings `` is ``None``, ``crawler.settings`` will be used.
    If ``crawler`` is ``None``, only the ``from_settings`` constructor will be
    tried.

    ``*args`` and ``**kwargs`` are forwarded to the constructors.

    Raises ``ValueError`` if both ``settings`` and ``crawler`` are ``None``.

    .. versionchanged:: 2.2
       Raises ``TypeError`` if the resulting instance is ``None`` (e.g. if an
       extension has not been implemented correctly).
    """
    if settings is None:
        if crawler is None:
            raise ValueError("Specify at least one of settings and crawler.")
        settings = crawler.settings
    if crawler and hasattr(objcls, 'from_crawler'):
        instance = objcls.from_crawler(crawler, *args, **kwargs)
        method_name = 'from_crawler'
    elif hasattr(objcls, 'from_settings'):
        instance = objcls.from_settings(settings, *args, **kwargs)
        method_name = 'from_settings'
    else:
        instance = objcls(*args, **kwargs)
        method_name = '__new__'
    if instance is None:
        raise TypeError("%s.%s returned None" % (objcls.__qualname__, method_name))
    return instance


@contextmanager
def set_environ(**kwargs):
    """Temporarily set environment variables inside the context manager and
    fully restore previous environment afterwards
    """

    original_env = {k: os.environ.get(k) for k in kwargs}
    os.environ.update(kwargs)
    try:
        yield
    finally:
        for k, v in original_env.items():
            if v is None:
                del os.environ[k]
            else:
                os.environ[k] = v


_generator_callbacks_cache = LocalWeakReferencedCache(limit=128)


def is_generator_with_return_value(callable):
    """
    Returns True if a callable is a generator function which includes a
    'return' statement with a value different than None, False otherwise
    """
    if callable in _generator_callbacks_cache:
        return _generator_callbacks_cache[callable]

    def returns_none(return_node):
        value = return_node.value
        return value is None or isinstance(value, ast.NameConstant) and value.value is None

    if inspect.isgeneratorfunction(callable):
        tree = ast.parse(dedent(inspect.getsource(callable)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and not returns_none(node):
                _generator_callbacks_cache[callable] = True
                return _generator_callbacks_cache[callable]

    _generator_callbacks_cache[callable] = False
    return _generator_callbacks_cache[callable]


def warn_on_generator_with_return_value(spider, callable):
    """
    Logs a warning if a callable is a generator function and includes
    a 'return' statement with a value different than None
    """
    if is_generator_with_return_value(callable):
        warnings.warn(
            'The "{}.{}" method is a generator and includes a "return" statement with a '
            'value different than None. This could lead to unexpected behaviour. Please see '
            'https://docs.python.org/3/reference/simple_stmts.html#the-return-statement '
            'for details about the semantics of the "return" statement within generators'
            .format(spider.__class__.__name__, callable.__name__), stacklevel=2,
        )
