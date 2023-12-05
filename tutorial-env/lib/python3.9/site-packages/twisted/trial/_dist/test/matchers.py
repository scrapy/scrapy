# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Hamcrest matchers useful throughout the test suite.
"""

__all__ = [
    "matches_result",
    "HasSum",
    "IsSequenceOf",
]

from typing import List, Sequence, Tuple, TypeVar

from hamcrest import (
    contains_exactly,
    contains_string,
    equal_to,
    has_length,
    has_properties,
    instance_of,
)
from hamcrest.core.base_matcher import BaseMatcher
from hamcrest.core.core.allof import AllOf
from hamcrest.core.description import Description
from hamcrest.core.matcher import Matcher
from typing_extensions import Protocol

from twisted.python.failure import Failure

T = TypeVar("T")


class Semigroup(Protocol[T]):
    """
    A type with an associative binary operator.

    Common examples of a semigroup are integers with addition and strings with
    concatenation.
    """

    def __add__(self, other: T) -> T:
        """
        This must be associative: a + (b + c) == (a + b) + c
        """


S = TypeVar("S", bound=Semigroup)


def matches_result(
    successes: Matcher = equal_to(0),
    errors: Matcher = has_length(0),
    failures: Matcher = has_length(0),
    skips: Matcher = has_length(0),
    expectedFailures: Matcher = has_length(0),
    unexpectedSuccesses: Matcher = has_length(0),
) -> Matcher:
    """
    Match a L{TestCase} instances with matching attributes.
    """
    return has_properties(
        {
            "successes": successes,
            "errors": errors,
            "failures": failures,
            "skips": skips,
            "expectedFailures": expectedFailures,
            "unexpectedSuccesses": unexpectedSuccesses,
        }
    )


class HasSum(BaseMatcher[Sequence[S]]):
    """
    Match a sequence the elements of which sum to a value matched by
    another matcher.

    :ivar sumMatcher: The matcher which must match the sum.
    :ivar zero: The zero value for the matched type.
    """

    def __init__(self, sumMatcher: Matcher[S], zero: S) -> None:
        self.sumMatcher = sumMatcher
        self.zero = zero

    def _sum(self, sequence: Sequence[S]) -> S:
        if not sequence:
            return self.zero
        result = self.zero
        for elem in sequence:
            result = result + elem
        return result

    def _matches(self, item: Sequence[S]) -> bool:
        """
        Determine whether the sum of the sequence is matched.
        """
        s = self._sum(item)
        return self.sumMatcher.matches(s)

    def describe_mismatch(self, item: Sequence[S], description: Description) -> None:
        """
        Describe the mismatch.
        """
        s = self._sum(item)
        description.append_description_of(self)
        self.sumMatcher.describe_mismatch(s, description)
        return None

    def describe_to(self, description: Description) -> None:
        """
        Describe this matcher for error messages.
        """
        description.append_text("a sequence with sum ")
        description.append_description_of(self.sumMatcher)
        description.append_text(", ")


class IsSequenceOf(BaseMatcher[Sequence[T]]):
    """
    Match a sequence where every element is matched by another matcher.

    :ivar elementMatcher: The matcher which must match every element of the
        sequence.
    """

    def __init__(self, elementMatcher: Matcher[T]) -> None:
        self.elementMatcher = elementMatcher

    def _matches(self, item: Sequence[T]) -> bool:
        """
        Determine whether every element of the sequence is matched.
        """
        for elem in item:
            if not self.elementMatcher.matches(elem):
                return False
        return True

    def describe_mismatch(self, item: Sequence[T], description: Description) -> None:
        """
        Describe the mismatch.
        """
        for idx, elem in enumerate(item):
            if not self.elementMatcher.matches(elem):
                description.append_description_of(self)
                description.append_text(f"not sequence with element #{idx} {elem!r}")

    def describe_to(self, description: Description) -> None:
        """
        Describe this matcher for error messages.
        """
        description.append_text("a sequence containing only ")
        description.append_description_of(self.elementMatcher)
        description.append_text(", ")


def isFailure(**properties: Matcher[object]) -> Matcher[object]:
    """
    Match an instance of L{Failure} with matching attributes.
    """
    return AllOf(
        instance_of(Failure),
        has_properties(**properties),
    )


def similarFrame(
    functionName: str, fileName: str
) -> Matcher[Sequence[Tuple[str, str, int, List[object], List[object]]]]:
    """
    Match a tuple representation of a frame like those used by
    L{twisted.python.failure.Failure}.
    """
    # The frames depend on exact layout of the source
    # code in files and on the filesystem so we won't
    # bother being very precise here.  Just verify we
    # see some distinctive fragments.
    #
    # In particular, the last frame should be a tuple like
    #
    # (functionName, fileName, someint, [], [])
    return contains_exactly(
        equal_to(functionName),
        contains_string(fileName),  # type: ignore[arg-type]
        instance_of(int),  # type: ignore[arg-type]
        # Unfortunately Failure makes them sometimes tuples, sometimes
        # dict_items.
        has_length(0),  # type: ignore[arg-type]
        has_length(0),  # type: ignore[arg-type]
    )
