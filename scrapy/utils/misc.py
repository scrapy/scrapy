"""Helper functions which don't fit anywhere else"""

from __future__ import annotations

import ast
import hashlib
import inspect
import os
import re
import warnings
from collections import deque
from collections.abc import Iterable
from contextlib import contextmanager
from functools import partial
from importlib import import_module
from pkgutil import iter_modules
from typing import IO, TYPE_CHECKING, Any, TypeVar, cast

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.item import Item
from scrapy.utils.datatypes import LocalWeakReferencedCache

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import ModuleType

    from scrapy import Spider
    from scrapy.crawler import Crawler


_ITERABLE_SINGLE_VALUES = dict, Item, str, bytes
T = TypeVar("T")


def arg_to_iter(arg: Any) -> Iterable[Any]:
    """Convert an argument to an iterable. The argument can be a None, single
    value, or an iterable.

    Exception: if arg is a dict, [arg] will be returned
    """
    if arg is None:
        return []
    if not isinstance(arg, _ITERABLE_SINGLE_VALUES) and hasattr(arg, "__iter__"):
        return cast(Iterable[Any], arg)
    return [arg]


def load_object(path: str | Callable[..., Any]) -> Any:
    """Load an object given its absolute object path, and return it.

    The object can be the import path of a class, function, variable or an
    instance, e.g. 'scrapy.downloadermiddlewares.redirect.RedirectMiddleware'.

    If ``path`` is not a string, but is a callable object, such as a class or
    a function, then return it as is.
    """

    if not isinstance(path, str):
        if callable(path):
            return path
        raise TypeError(
            f"Unexpected argument type, expected string or object, got: {type(path)}"
        )

    try:
        dot = path.rindex(".")
    except ValueError:
        raise ValueError(f"Error loading object '{path}': not a full path")

    module, name = path[:dot], path[dot + 1 :]
    mod = import_module(module)

    try:
        obj = getattr(mod, name)
    except AttributeError:
        raise NameError(f"Module '{module}' doesn't define any object named '{name}'")

    return obj


def walk_modules(path: str) -> list[ModuleType]:
    """Loads a module and all its submodules from the given module path and
    returns them. If *any* module throws an exception while importing, that
    exception is thrown back.

    For example: walk_modules('scrapy.utils')
    """

    mods: list[ModuleType] = []
    mod = import_module(path)
    mods.append(mod)
    if hasattr(mod, "__path__"):
        for _, subpath, ispkg in iter_modules(mod.__path__):
            fullpath = path + "." + subpath
            if ispkg:
                mods += walk_modules(fullpath)
            else:
                submod = import_module(fullpath)
                mods.append(submod)
    return mods


def md5sum(file: IO[bytes]) -> str:
    """Calculate the md5 checksum of a file-like object without reading its
    whole content in memory.

    >>> from io import BytesIO
    >>> md5sum(BytesIO(b'file content to hash'))
    '784406af91dd5a54fbb9c84c2236595a'
    """
    warnings.warn(
        (
            "The scrapy.utils.misc.md5sum function is deprecated and will be "
            "removed in a future version of Scrapy."
        ),
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    m = hashlib.md5()  # nosec
    while True:
        d = file.read(8096)
        if not d:
            break
        m.update(d)
    return m.hexdigest()


def rel_has_nofollow(rel: str | None) -> bool:
    """Return True if link rel attribute has nofollow type"""
    return rel is not None and "nofollow" in rel.replace(",", " ").split()


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
    warnings.warn(
        "The create_instance() function is deprecated. "
        "Please use build_from_crawler() instead.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )

    if settings is None:
        if crawler is None:
            raise ValueError("Specify at least one of settings and crawler.")
        settings = crawler.settings
    if crawler and hasattr(objcls, "from_crawler"):
        instance = objcls.from_crawler(crawler, *args, **kwargs)
        method_name = "from_crawler"
    elif hasattr(objcls, "from_settings"):
        instance = objcls.from_settings(settings, *args, **kwargs)
        method_name = "from_settings"
    else:
        instance = objcls(*args, **kwargs)
        method_name = "__new__"
    if instance is None:
        raise TypeError(f"{objcls.__qualname__}.{method_name} returned None")
    return instance


def build_from_crawler(
    objcls: type[T], crawler: Crawler, /, *args: Any, **kwargs: Any
) -> T:
    """Construct a class instance using its ``from_crawler`` or ``from_settings`` constructor.

    ``*args`` and ``**kwargs`` are forwarded to the constructor.

    Raises ``TypeError`` if the resulting instance is ``None``.
    """
    if hasattr(objcls, "from_crawler"):
        instance = objcls.from_crawler(crawler, *args, **kwargs)  # type: ignore[attr-defined]
        method_name = "from_crawler"
    elif hasattr(objcls, "from_settings"):
        warnings.warn(
            f"{objcls.__qualname__} has from_settings() but not from_crawler()."
            " This is deprecated and calling from_settings() will be removed in a future"
            " Scrapy version. You can implement a simple from_crawler() that calls"
            " from_settings() with crawler.settings.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        instance = objcls.from_settings(crawler.settings, *args, **kwargs)  # type: ignore[attr-defined]
        method_name = "from_settings"
    else:
        instance = objcls(*args, **kwargs)
        method_name = "__new__"
    if instance is None:
        raise TypeError(f"{objcls.__qualname__}.{method_name} returned None")
    return cast(T, instance)


@contextmanager
def set_environ(**kwargs: str) -> Iterator[None]:
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


def walk_callable(node: ast.AST) -> Iterable[ast.AST]:
    """Similar to ``ast.walk``, but walks only function body and skips nested
    functions defined within the node.
    """
    todo: deque[ast.AST] = deque([node])
    walked_func_def = False
    while todo:
        node = todo.popleft()
        if isinstance(node, ast.FunctionDef):
            if walked_func_def:
                continue
            walked_func_def = True
        todo.extend(ast.iter_child_nodes(node))
        yield node


_generator_callbacks_cache = LocalWeakReferencedCache(limit=128)


def is_generator_with_return_value(callable: Callable[..., Any]) -> bool:
    """
    Returns True if a callable is a generator function which includes a
    'return' statement with a value different than None, False otherwise
    """
    if callable in _generator_callbacks_cache:
        return bool(_generator_callbacks_cache[callable])

    def returns_none(return_node: ast.Return) -> bool:
        value = return_node.value
        return value is None or isinstance(value, ast.Constant) and value.value is None

    if inspect.isgeneratorfunction(callable):
        func = callable
        while isinstance(func, partial):
            func = func.func

        src = inspect.getsource(func)
        pattern = re.compile(r"(^[\t ]+)")
        code = pattern.sub("", src)

        match = pattern.match(src)  # finds indentation
        if match:
            code = re.sub(f"\n{match.group(0)}", "\n", code)  # remove indentation

        tree = ast.parse(code)
        for node in walk_callable(tree):
            if isinstance(node, ast.Return) and not returns_none(node):
                _generator_callbacks_cache[callable] = True
                return bool(_generator_callbacks_cache[callable])

    _generator_callbacks_cache[callable] = False
    return bool(_generator_callbacks_cache[callable])


def warn_on_generator_with_return_value(
    spider: Spider, callable: Callable[..., Any]
) -> None:
    """
    Logs a warning if a callable is a generator function and includes
    a 'return' statement with a value different than None
    """
    try:
        if is_generator_with_return_value(callable):
            warnings.warn(
                f'The "{spider.__class__.__name__}.{callable.__name__}" method is '
                'a generator and includes a "return" statement with a value '
                "different than None. This could lead to unexpected behaviour. Please see "
                "https://docs.python.org/3/reference/simple_stmts.html#the-return-statement "
                'for details about the semantics of the "return" statement within generators',
                stacklevel=2,
            )
    except IndentationError:
        callable_name = spider.__class__.__name__ + "." + callable.__name__
        warnings.warn(
            f'Unable to determine whether or not "{callable_name}" is a generator with a return value. '
            "This will not prevent your code from working, but it prevents Scrapy from detecting "
            f'potential issues in your implementation of "{callable_name}". Please, report this in the '
            "Scrapy issue tracker (https://github.com/scrapy/scrapy/issues), "
            f'including the code of "{callable_name}"',
            stacklevel=2,
        )
