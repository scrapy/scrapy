# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.systemd}.
"""


import os
from typing import Dict, Mapping, Sequence

from hamcrest import assert_that, equal_to, not_
from hypothesis import given
from hypothesis.strategies import dictionaries, integers, lists

from twisted.python.systemd import ListenFDs
from twisted.trial.unittest import SynchronousTestCase
from .strategies import systemdDescriptorNames


def buildEnvironment(count: int, pid: object) -> Dict[str, str]:
    """
    @param count: The number of file descriptors to indicate as inherited.

    @param pid: The pid of the inheriting process to indicate.

    @return: A copy of the current process environment with the I{systemd}
        file descriptor inheritance-related environment variables added to it.
    """
    result = os.environ.copy()
    result["LISTEN_FDS"] = str(count)
    result["LISTEN_FDNAMES"] = ":".join([f"{n}.socket" for n in range(count)])
    result["LISTEN_PID"] = str(pid)
    return result


class ListenFDsTests(SynchronousTestCase):
    """
    Apply tests to L{ListenFDs}, constructed based on an environment dictionary.
    """

    @given(lists(systemdDescriptorNames(), min_size=0, max_size=10))
    def test_fromEnvironmentEquivalence(self, names: Sequence[str]) -> None:
        """
        The L{ListenFDs} and L{ListenFDs.fromEnvironment} constructors are
        equivalent for their respective representations of the same
        information.

        @param names: The names of the file descriptors to represent as
            inherited in the test environment given to the parser.  The number
            of descriptors represented will equal the length of this list.
        """
        numFDs = len(names)
        descriptors = list(range(ListenFDs._START, ListenFDs._START + numFDs))
        fds = ListenFDs.fromEnvironment(
            {
                "LISTEN_PID": str(os.getpid()),
                "LISTEN_FDS": str(numFDs),
                "LISTEN_FDNAMES": ":".join(names),
            }
        )
        assert_that(fds, equal_to(ListenFDs(descriptors, tuple(names))))

    def test_defaultEnviron(self) -> None:
        """
        If the process environment is not explicitly passed to
        L{ListenFDs.fromEnvironment}, the real process environment dictionary
        is used.
        """
        self.patch(os, "environ", buildEnvironment(5, os.getpid()))
        sddaemon = ListenFDs.fromEnvironment()
        self.assertEqual(list(range(3, 3 + 5)), sddaemon.inheritedDescriptors())

    def test_secondEnvironment(self) -> None:
        """
        L{ListenFDs.fromEnvironment} removes information about the
        inherited file descriptors from the environment mapping so that the
        same inherited file descriptors cannot be handled repeatedly from
        multiple L{ListenFDs} instances.
        """
        env = buildEnvironment(3, os.getpid())
        first = ListenFDs.fromEnvironment(environ=env)
        second = ListenFDs.fromEnvironment(environ=env)
        self.assertEqual(list(range(3, 6)), first.inheritedDescriptors())
        self.assertEqual([], second.inheritedDescriptors())

    def test_mismatchedPID(self) -> None:
        """
        If the current process PID does not match the PID in the
        environment then the systemd variables in the environment were set for
        a different process (perhaps our parent) and the inherited descriptors
        are not intended for this process so L{ListenFDs.inheritedDescriptors}
        returns an empty list.
        """
        env = buildEnvironment(3, os.getpid() + 1)
        sddaemon = ListenFDs.fromEnvironment(environ=env)
        self.assertEqual([], sddaemon.inheritedDescriptors())

    def test_missingPIDVariable(self) -> None:
        """
        If the I{LISTEN_PID} environment variable is not present then
        there is no clear indication that any file descriptors were inherited
        by this process so L{ListenFDs.inheritedDescriptors} returns an empty
        list.
        """
        env = buildEnvironment(3, os.getpid())
        del env["LISTEN_PID"]
        sddaemon = ListenFDs.fromEnvironment(environ=env)
        self.assertEqual([], sddaemon.inheritedDescriptors())

    def test_nonIntegerPIDVariable(self) -> None:
        """
        If the I{LISTEN_PID} environment variable is set to a string that cannot
        be parsed as an integer, no inherited descriptors are reported.
        """
        env = buildEnvironment(3, "hello, world")
        sddaemon = ListenFDs.fromEnvironment(environ=env)
        self.assertEqual([], sddaemon.inheritedDescriptors())

    def test_missingFDSVariable(self) -> None:
        """
        If the I{LISTEN_FDS} and I{LISTEN_FDNAMES} environment variables
        are not present, no inherited descriptors are reported.
        """
        env = buildEnvironment(3, os.getpid())
        del env["LISTEN_FDS"]
        del env["LISTEN_FDNAMES"]
        sddaemon = ListenFDs.fromEnvironment(environ=env)
        self.assertEqual([], sddaemon.inheritedDescriptors())

    def test_nonIntegerFDSVariable(self) -> None:
        """
        If the I{LISTEN_FDS} environment variable is set to a string that cannot
        be parsed as an integer, no inherited descriptors are reported.
        """
        env = buildEnvironment(3, os.getpid())
        env["LISTEN_FDS"] = "hello, world"
        sddaemon = ListenFDs.fromEnvironment(environ=env)
        self.assertEqual([], sddaemon.inheritedDescriptors())

    @given(lists(integers(min_value=0, max_value=10), unique=True))
    def test_inheritedDescriptors(self, descriptors: Sequence[int]) -> None:
        """
        L{ListenFDs.inheritedDescriptors} returns a copy of the inherited
        descriptors list.
        """
        names = tuple(map(str, descriptors))
        fds = ListenFDs(descriptors, names)
        fdsCopy = fds.inheritedDescriptors()
        assert_that(descriptors, equal_to(fdsCopy))
        fdsCopy.append(1)
        assert_that(descriptors, not_(equal_to(fdsCopy)))

    @given(dictionaries(systemdDescriptorNames(), integers(min_value=0), max_size=10))
    def test_inheritedNamedDescriptors(self, expected: Mapping[str, int]) -> None:
        """
        L{ListenFDs.inheritedNamedDescriptors} returns a mapping from the
        descriptor names to their integer values, with items formed by
        pairwise combination of the input descriptors and names.
        """
        items = list(expected.items())
        names = [name for name, _ in items]
        descriptors = [fd for _, fd in items]
        fds = ListenFDs(descriptors, names)
        assert_that(fds.inheritedNamedDescriptors(), equal_to(expected))

    @given(lists(integers(min_value=0, max_value=10), unique=True))
    def test_repeated(self, descriptors: Sequence[int]) -> None:
        """
        Any subsequent calls to C{inheritedDescriptors} and
        C{inheritedNamedDescriptors} return the same list.
        """
        names = tuple(map(str, descriptors))
        sddaemon = ListenFDs(descriptors, names)
        self.assertEqual(
            sddaemon.inheritedDescriptors(), sddaemon.inheritedDescriptors()
        )
        self.assertEqual(
            sddaemon.inheritedNamedDescriptors(), sddaemon.inheritedNamedDescriptors()
        )
