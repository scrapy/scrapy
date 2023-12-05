# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
General functional-style helpers for disttrial.
"""

from functools import partial, wraps
from typing import Awaitable, Callable, Iterable, Optional, TypeVar

from twisted.internet.defer import Deferred, succeed

_A = TypeVar("_A")
_B = TypeVar("_B")
_C = TypeVar("_C")


def fromOptional(default: _A, optional: Optional[_A]) -> _A:
    """
    Get a definite value from an optional value.

    @param default: The value to return if the optional value is missing.

    @param optional: The optional value to return if it exists.
    """
    if optional is None:
        return default
    return optional


def takeWhile(condition: Callable[[_A], bool], xs: Iterable[_A]) -> Iterable[_A]:
    """
    :return: An iterable over C{xs} that stops when C{condition} returns
        ``False`` based on the value of iterated C{xs}.
    """
    for x in xs:
        if condition(x):
            yield x
        else:
            break


async def sequence(a: Awaitable[_A], b: Awaitable[_B]) -> _B:
    """
    Wait for one action to complete and then another.

    If either action fails, failure is propagated.  If the first action fails,
    the second action is not waited on.
    """
    await a
    return await b


def flip(f: Callable[[_A, _B], _C]) -> Callable[[_B, _A], _C]:
    """
    Create a function like another but with the order of the first two
    arguments flipped.
    """

    @wraps(f)
    def g(b, a):
        return f(a, b)

    return g


def compose(fx: Callable[[_B], _C], fy: Callable[[_A], _B]) -> Callable[[_A], _C]:
    """
    Create a function that calls one function with an argument and then
    another function with the result of the first function.
    """

    @wraps(fx)
    @wraps(fy)
    def g(a):
        return fx(fy(a))

    return g


# Discard the result of an awaitable and substitute None in its place.
#
# Ignore the `Cannot infer type argument 1 of "compose"`
# https://github.com/python/mypy/issues/6220
discardResult: Callable[[Awaitable[_A]], Deferred[None]] = compose(  # type: ignore[misc]
    Deferred.fromCoroutine,
    partial(flip(sequence), succeed(None)),
)


async def iterateWhile(
    predicate: Callable[[_A], bool],
    action: Callable[[], Awaitable[_A]],
) -> _A:
    """
    Call a function repeatedly until its result fails to satisfy a predicate.

    @param predicate: The check to apply.

    @param action: The function to call.

    @return: The result of C{action} which did not satisfy C{predicate}.
    """
    while True:
        result = await action()
        if not predicate(result):
            return result


def countingCalls(f: Callable[[int], _A]) -> Callable[[], _A]:
    """
    Wrap a function with another that automatically passes an integer counter
    of the number of calls that have gone through the wrapper.
    """
    counter = 0

    def g():
        nonlocal counter
        try:
            result = f(counter)
        finally:
            counter += 1
        return result

    return g
