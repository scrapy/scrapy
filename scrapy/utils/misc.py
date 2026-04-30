"""Helper functions which don't fit anywhere else"""

from __future__ import annotations

import ast
import hashlib
import inspect
import os
import re
import warnings
from collections import deque
from contextlib import contextmanager
from functools import partial
from importlib import import_module
from pkgutil import iter_modules
from typing import IO, TYPE_CHECKING, Any, ParamSpec, Protocol, TypeVar, overload

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.item import Item
from scrapy.utils.datatypes import LocalWeakReferencedCache

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from types import ModuleType

    from scrapy import Spider
    from scrapy.crawler import Crawler


_ITERABLE_SINGLE_VALUES = dict, Item, str, bytes
_ITER_T = TypeVar("_ITER_T", bound=dict | Item | str | bytes)
_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)
_P = ParamSpec("_P")


@overload
def arg_to_iter(arg: None) -> tuple[()]: ...
@overload
def arg_to_iter(arg: _ITER_T) -> Iterable[_ITER_T]: ...
@overload
def arg_to_iter(arg: Iterable[_T]) -> Iterable[_T]: ...
@overload
def arg_to_iter(arg: _T) -> Iterable[_T]: ...
def arg_to_iter(arg: Any) -> Iterable[Any]:
    """Convert an argument to an iterable. The argument can be a None, single
    value, or an iterable.

    Exception: if arg is a dict, [arg] will be returned
    """
    if arg is None:
        return ()
    if not isinstance(arg, _ITERABLE_SINGLE_VALUES) and hasattr(arg, "__iter__"):
        return arg
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
        raise ValueError(f"Error loading object '{path}': not a full path") from None

    module, name = path[:dot], path[dot + 1 :]
    mod = import_module(module)

    try:
        obj = getattr(mod, name)
    except AttributeError:
        raise NameError(
            f"Module '{module}' doesn't define any object named '{name}'"
        ) from None

    return obj


def walk_modules_iter(path: str) -> Iterable[ModuleType]:
    """Loads a module and all its submodules from the given module path and
    returns them. If *any* module throws an exception while importing, that
    exception is thrown back.

    For example:
    >>> list(walk_modules_iter('scrapy.utils'))
    [<module 'scrapy.utils' from '...'>, ...]
    >>> gen = walk_modules_iter('scrapy.utils.nonexistent') # error not raised until the generator is consumed
    >>> list(gen)
    Traceback (most recent call last):
        ...
    ModuleNotFoundError: No module named 'scrapy.utils.nonexistent'
    """

    mod = import_module(path)
    yield mod
    if hasattr(mod, "__path__"):
        for _, subpath, ispkg in iter_modules(mod.__path__):
            fullpath = path + "." + subpath
            if ispkg:
                yield from walk_modules_iter(fullpath)
            else:
                yield import_module(fullpath)


def walk_modules(path: str) -> list[ModuleType]:  # pragma: no cover
    """
    Loads a module and all its submodules from the given module path and
    returns them. If *any* module throws an exception while importing, that
    exception is thrown back.
    """
    warnings.warn(
        (
            "The scrapy.utils.misc.walk_modules function is deprecated and will be "
            "removed in a future version of Scrapy. "
            "Use scrapy.utils.misc.walk_modules_iter instead."
        ),
        ScrapyDeprecationWarning,
        stacklevel=2,
    )

    return list(walk_modules_iter(path))


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
    m = hashlib.md5()  # noqa: S324
    while True:
        d = file.read(8096)
        if not d:
            break
        m.update(d)
    return m.hexdigest()


def rel_has_nofollow(rel: str | None) -> bool:
    """Return True if link rel attribute has nofollow type"""
    return rel is not None and "nofollow" in rel.replace(",", " ").split()


class SupportsFromCrawler(Protocol[_T_co, _P]):
    @classmethod
    def from_crawler(
        cls, crawler: Crawler, /, *args: _P.args, **kwargs: _P.kwargs
    ) -> _T_co: ...


@overload
def build_from_crawler(
    objcls: SupportsFromCrawler[_T_co, _P],
    crawler: Crawler,
    /,
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T_co: ...


@overload
def build_from_crawler(
    objcls: Callable[_P, _T_co],
    crawler: Crawler,
    /,
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T_co: ...


def build_from_crawler(
    objcls: Any,
    crawler: Crawler,
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Construct a class instance using its ``from_crawler()`` or ``__init__()`` constructor.

    .. versionadded:: 2.12

    ``*args`` and ``**kwargs`` are forwarded to the constructor.

    Raises ``TypeError`` if the resulting instance is ``None``.
    """
    if hasattr(objcls, "from_crawler"):
        instance = objcls.from_crawler(crawler, *args, **kwargs)
        method_name = "from_crawler"
    else:
        instance = objcls(*args, **kwargs)
        method_name = "__new__"
    if instance is None:
        raise TypeError(f"{objcls.__qualname__}.{method_name} returned None")
    return instance


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


def is_generator_with_return_value(callable: Callable[..., Any]) -> bool:  # noqa: A002
    """
    Returns True if a callable is a generator function which includes a
    'return' statement with a value different than None, False otherwise
    """
    if callable in _generator_callbacks_cache:
        return bool(_generator_callbacks_cache[callable])

    def returns_none(return_node: ast.Return) -> bool:
        value = return_node.value
        return value is None or (
            isinstance(value, ast.Constant) and value.value is None
        )

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
    spider: Spider,
    callable: Callable[..., Any],  # noqa: A002
) -> None:
    """
    Logs a warning if a callable is a generator function and includes
    a 'return' statement with a value different than None
    """
    if not spider.settings.getbool("WARN_ON_GENERATOR_RETURN_VALUE"):
        return
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
