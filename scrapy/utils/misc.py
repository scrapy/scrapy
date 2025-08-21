"""Helper functions which don't fit anywhere else"""

from __future__ import annotations

import ast
import hashlib
import inspect
import io
import os
import re
import warnings
from collections import deque
from contextlib import contextmanager
from functools import partial
from importlib import import_module
from pkgutil import iter_modules
from typing import IO, TYPE_CHECKING, Any, TypeVar, cast

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.item import Item
from scrapy.utils.datatypes import LocalWeakReferencedCache

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from types import ModuleType

    from typing_extensions import Self

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
        return cast("Iterable[Any]", arg)
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


def build_from_crawler(
    objcls: type[T], crawler: Crawler, /, *args: Any, **kwargs: Any
) -> T:
    """Construct a class instance using its ``from_crawler()`` or ``__init__()`` constructor.

    .. versionadded:: 2.12

    ``*args`` and ``**kwargs`` are forwarded to the constructor.

    Raises ``TypeError`` if the resulting instance is ``None``.
    """
    if hasattr(objcls, "from_crawler"):
        instance = objcls.from_crawler(crawler, *args, **kwargs)  # type: ignore[attr-defined]
        method_name = "from_crawler"
    else:
        instance = objcls(*args, **kwargs)
        method_name = "__new__"
    if instance is None:
        raise TypeError(f"{objcls.__qualname__}.{method_name} returned None")
    return cast("T", instance)


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


class MemoryviewReader:
    """
    File-like reader over internal buffer of bytes or bytearray using memoryview.

    Basic read:
    >>> r = MemoryviewReader.from_anystr("hello world")
    >>> r.read(5), r.read()
    (b'hello', b' world')

    Read lines:
    >>> r = MemoryviewReader(b"a\\nb\\nc")
    >>> r.readline(99), r.readline(1), r.readline(), r.readline(), r.readline(99)
    (b'a\\n', b'b', b'\\n', b'c', b'')

    Iterate lines:
    >>> list(MemoryviewReader(b"x\\ny"))
    [b'x\\n', b'y']

    Seek/tell:
    >>> r = MemoryviewReader(memoryview(b"abcdef"))
    >>> r.read(3), r.tell()
    (b'abc', 3)
    >>> r.seek(0), r.read(2)
    (0, b'ab')
    >>> r.seek(2, io.SEEK_CUR), r.read(2)
    (4, b'ef')
    >>> r.seek(-3, io.SEEK_END), r.read(99)
    (3, b'def')

    Errors:
    >>> r.seek(0, 99)
    Traceback (most recent call last):
    ...
    ValueError: Invalid whence
    >>> r.seek(-10, io.SEEK_SET)
    Traceback (most recent call last):
    ...
    ValueError: Seek out of range
    >>> r.seek(10, io.SEEK_SET)
    Traceback (most recent call last):
    ...
    ValueError: Seek out of range
    """  # noqa: D301

    __slots__ = ("_mv", "_pos", "size")

    def __init__(self, buf: bytes | bytearray | memoryview):
        if not isinstance(buf, memoryview):
            buf = memoryview(buf)
        self._mv = buf
        self._pos = 0
        self.size = len(self._mv)

    @classmethod
    def from_anystr(cls, str_or_bytes: str | bytes) -> Self:
        return (
            cls(str_or_bytes)
            if isinstance(str_or_bytes, bytes)
            else cls(str_or_bytes.encode())
        )

    def read(self, amount: int = -1, /) -> bytes:
        if amount < 0:
            end = self.size
        else:
            end = self._pos + amount
            if end > self.size:  # pylint: disable=consider-using-min-builtin # noqa: PLR1730
                end = self.size

        start = self._pos
        self._pos = end
        return self._mv[start:end].tobytes()

    def readline(self, amount: int = -1, /) -> bytes:
        if self._pos >= self.size:
            return b""

        if amount < 0:
            end = self.size
        else:
            end = self._pos + amount
            if end > self.size:  # pylint: disable=consider-using-min-builtin # noqa: PLR1730
                end = self.size

        start = self._pos
        i = start
        while i < end:
            if self._mv[i] == 10:  # ord('\n')
                i += 1  # include newline
                break
            i += 1

        self._pos = i
        return self._mv[start:i].tobytes()

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> bytes:
        line = self.readline()
        if not line:
            raise StopIteration
        return line

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == io.SEEK_SET:
            new = offset
        elif whence == io.SEEK_CUR:
            new = self._pos + offset
        elif whence == io.SEEK_END:
            new = self.size + offset
        else:
            raise ValueError("Invalid whence")
        if not (0 <= new <= self.size):  # pylint: disable=superfluous-parens
            raise ValueError("Seek out of range")
        self._pos = new
        return self._pos

    def tell(self) -> int:
        return self._pos
