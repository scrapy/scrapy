"""
This module contains essential stuff that should've come with Python itself ;)
"""

from __future__ import annotations

import gc
import inspect
import re
import sys
import warnings
import weakref
from collections.abc import AsyncIterable, Iterable, Mapping
from functools import partial, wraps
from itertools import chain
from typing import TYPE_CHECKING, Any, TypeVar, overload

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.asyncgen import as_async_generator

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator
    from re import Pattern

    # typing.Concatenate and typing.ParamSpec require Python 3.10
    from typing_extensions import Concatenate, ParamSpec

    _P = ParamSpec("_P")

_T = TypeVar("_T")
_KT = TypeVar("_KT")
_VT = TypeVar("_VT")


def flatten(x: Iterable[Any]) -> list[Any]:
    """flatten(sequence) -> list

    Returns a single, flat list which contains all elements retrieved
    from the sequence and all recursively contained sub-sequences
    (iterables).

    Examples:
    >>> [1, 2, [3,4], (5,6)]
    [1, 2, [3, 4], (5, 6)]
    >>> flatten([[[1,2,3], (42,None)], [4,5], [6], 7, (8,9,10)])
    [1, 2, 3, 42, None, 4, 5, 6, 7, 8, 9, 10]
    >>> flatten(["foo", "bar"])
    ['foo', 'bar']
    >>> flatten(["foo", ["baz", 42], "bar"])
    ['foo', 'baz', 42, 'bar']
    """
    warnings.warn(
        "The flatten function is deprecated and will be removed in a future version of Scrapy.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return list(iflatten(x))


def iflatten(x: Iterable[Any]) -> Iterable[Any]:
    """iflatten(sequence) -> iterator

    Similar to ``.flatten()``, but returns iterator instead"""
    warnings.warn(
        "The iflatten function is deprecated and will be removed in a future version of Scrapy.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    for el in x:
        if is_listlike(el):
            yield from iflatten(el)
        else:
            yield el


def is_listlike(x: Any) -> bool:
    """
    >>> is_listlike("foo")
    False
    >>> is_listlike(5)
    False
    >>> is_listlike(b"foo")
    False
    >>> is_listlike([b"foo"])
    True
    >>> is_listlike((b"foo",))
    True
    >>> is_listlike({})
    True
    >>> is_listlike(set())
    True
    >>> is_listlike((x for x in range(3)))
    True
    >>> is_listlike(range(5))
    True
    """
    return hasattr(x, "__iter__") and not isinstance(x, (str, bytes))


def unique(list_: Iterable[_T], key: Callable[[_T], Any] = lambda x: x) -> list[_T]:
    """efficient function to uniquify a list preserving item order"""
    seen = set()
    result: list[_T] = []
    for item in list_:
        seenkey = key(item)
        if seenkey in seen:
            continue
        seen.add(seenkey)
        result.append(item)
    return result


def to_unicode(
    text: str | bytes, encoding: str | None = None, errors: str = "strict"
) -> str:
    """Return the unicode representation of a bytes object ``text``. If
    ``text`` is already an unicode object, return it as-is."""
    if isinstance(text, str):
        return text
    if not isinstance(text, (bytes, str)):
        raise TypeError(
            "to_unicode must receive a bytes or str "
            f"object, got {type(text).__name__}"
        )
    if encoding is None:
        encoding = "utf-8"
    return text.decode(encoding, errors)


def to_bytes(
    text: str | bytes, encoding: str | None = None, errors: str = "strict"
) -> bytes:
    """Return the binary representation of ``text``. If ``text``
    is already a bytes object, return it as-is."""
    if isinstance(text, bytes):
        return text
    if not isinstance(text, str):
        raise TypeError(
            "to_bytes must receive a str or bytes " f"object, got {type(text).__name__}"
        )
    if encoding is None:
        encoding = "utf-8"
    return text.encode(encoding, errors)


def re_rsearch(
    pattern: str | Pattern[str], text: str, chunk_size: int = 1024
) -> tuple[int, int] | None:
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

    def _chunk_iter() -> Iterable[tuple[str, int]]:
        offset = len(text)
        while True:
            offset -= chunk_size * 1024
            if offset <= 0:
                break
            yield (text[offset:], offset)
        yield (text, 0)

    if isinstance(pattern, str):
        pattern = re.compile(pattern)

    for chunk, offset in _chunk_iter():
        matches = list(pattern.finditer(chunk))
        if matches:
            start, end = matches[-1].span()
            return offset + start, offset + end
    return None


_SelfT = TypeVar("_SelfT")


def memoizemethod_noargs(
    method: Callable[Concatenate[_SelfT, _P], _T]
) -> Callable[Concatenate[_SelfT, _P], _T]:
    """Decorator to cache the result of a method (without arguments) using a
    weak reference to its object
    """
    cache: weakref.WeakKeyDictionary[_SelfT, _T] = weakref.WeakKeyDictionary()

    @wraps(method)
    def new_method(self: _SelfT, *args: _P.args, **kwargs: _P.kwargs) -> _T:
        if self not in cache:
            cache[self] = method(self, *args, **kwargs)
        return cache[self]

    return new_method


_BINARYCHARS = {
    i for i in range(32) if to_bytes(chr(i)) not in {b"\0", b"\t", b"\n", b"\r"}
}


def binary_is_text(data: bytes) -> bool:
    """Returns ``True`` if the given ``data`` argument (a ``bytes`` object)
    does not contain unprintable control characters.
    """
    if not isinstance(data, bytes):
        raise TypeError(f"data must be bytes, got '{type(data).__name__}'")
    return all(c not in _BINARYCHARS for c in data)


def get_func_args(func: Callable[..., Any], stripself: bool = False) -> list[str]:
    """Return the argument name list of a callable object"""
    if not callable(func):
        raise TypeError(f"func must be callable, got '{type(func).__name__}'")

    args: list[str] = []
    try:
        sig = inspect.signature(func)
    except ValueError:
        return args

    if isinstance(func, partial):
        partial_args = func.args
        partial_kw = func.keywords

        for name, param in sig.parameters.items():
            if param.name in partial_args:
                continue
            if partial_kw and param.name in partial_kw:
                continue
            args.append(name)
    else:
        for name in sig.parameters.keys():
            args.append(name)

    if stripself and args and args[0] == "self":
        args = args[1:]
    return args


def get_spec(func: Callable[..., Any]) -> tuple[list[str], dict[str, Any]]:
    """Returns (args, kwargs) tuple for a function
    >>> import re
    >>> get_spec(re.match)
    (['pattern', 'string'], {'flags': 0})

    >>> class Test:
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
        spec = inspect.getfullargspec(func)
    elif hasattr(func, "__call__"):  # noqa: B004
        spec = inspect.getfullargspec(func.__call__)
    else:
        raise TypeError(f"{type(func)} is not callable")

    defaults: tuple[Any, ...] = spec.defaults or ()

    firstdefault = len(spec.args) - len(defaults)
    args = spec.args[:firstdefault]
    kwargs = dict(zip(spec.args[firstdefault:], defaults))
    return args, kwargs


def equal_attributes(
    obj1: Any, obj2: Any, attributes: list[str | Callable[[Any], Any]] | None
) -> bool:
    """Compare two objects attributes"""
    warnings.warn(
        "The equal_attributes function is deprecated and will be removed in a future version of Scrapy.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    # not attributes given return False by default
    if not attributes:
        return False

    temp1, temp2 = object(), object()
    for attr in attributes:
        # support callables like itemgetter
        if callable(attr):
            if attr(obj1) != attr(obj2):
                return False
        elif getattr(obj1, attr, temp1) != getattr(obj2, attr, temp2):
            return False
    # all attributes equal
    return True


@overload
def without_none_values(iterable: Mapping[_KT, _VT]) -> dict[_KT, _VT]: ...


@overload
def without_none_values(iterable: Iterable[_KT]) -> Iterable[_KT]: ...


def without_none_values(
    iterable: Mapping[_KT, _VT] | Iterable[_KT]
) -> dict[_KT, _VT] | Iterable[_KT]:
    """Return a copy of ``iterable`` with all ``None`` entries removed.

    If ``iterable`` is a mapping, return a dictionary where all pairs that have
    value ``None`` have been removed.
    """
    if isinstance(iterable, Mapping):
        return {k: v for k, v in iterable.items() if v is not None}
    # the iterable __init__ must take another iterable
    return type(iterable)(v for v in iterable if v is not None)  # type: ignore[call-arg]


def global_object_name(obj: Any) -> str:
    """
    Return full name of a global object.

    >>> from scrapy import Request
    >>> global_object_name(Request)
    'scrapy.http.request.Request'
    """
    return f"{obj.__module__}.{obj.__qualname__}"


if hasattr(sys, "pypy_version_info"):

    def garbage_collect() -> None:
        # Collecting weakreferences can take two collections on PyPy.
        gc.collect()
        gc.collect()

else:

    def garbage_collect() -> None:
        gc.collect()


class MutableChain(Iterable[_T]):
    """
    Thin wrapper around itertools.chain, allowing to add iterables "in-place"
    """

    def __init__(self, *args: Iterable[_T]):
        self.data: Iterator[_T] = chain.from_iterable(args)

    def extend(self, *iterables: Iterable[_T]) -> None:
        self.data = chain(self.data, chain.from_iterable(iterables))

    def __iter__(self) -> Iterator[_T]:
        return self

    def __next__(self) -> _T:
        return next(self.data)


async def _async_chain(
    *iterables: Iterable[_T] | AsyncIterable[_T],
) -> AsyncIterator[_T]:
    for it in iterables:
        async for o in as_async_generator(it):
            yield o


class MutableAsyncChain(AsyncIterable[_T]):
    """
    Similar to MutableChain but for async iterables
    """

    def __init__(self, *args: Iterable[_T] | AsyncIterable[_T]):
        self.data: AsyncIterator[_T] = _async_chain(*args)

    def extend(self, *iterables: Iterable[_T] | AsyncIterable[_T]) -> None:
        self.data = _async_chain(self.data, _async_chain(*iterables))

    def __aiter__(self) -> AsyncIterator[_T]:
        return self

    async def __anext__(self) -> _T:
        return await self.data.__anext__()
