# -*- test-case-name: twisted.python.test.test_systemd -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Integration with systemd.

Currently only the minimum APIs necessary for using systemd's socket activation
feature are supported.
"""


__all__ = ["ListenFDs"]

from os import getpid
from typing import Dict, List, Mapping, Optional, Sequence

from attrs import Factory, define


@define
class ListenFDs:
    """
    L{ListenFDs} provides access to file descriptors inherited from systemd.

    Typically L{ListenFDs.fromEnvironment} should be used to construct a new
    instance of L{ListenFDs}.

    @cvar _START: File descriptors inherited from systemd are always
        consecutively numbered, with a fixed lowest "starting" descriptor.  This
        gives the default starting descriptor.  Since this must agree with the
        value systemd is using, it typically should not be overridden.

    @ivar _descriptors: A C{list} of C{int} giving the descriptors which were
        inherited.

    @ivar _names: A L{Sequence} of C{str} giving the names of the descriptors
        which were inherited.
    """

    _descriptors: Sequence[int]
    _names: Sequence[str] = Factory(tuple)

    _START = 3

    @classmethod
    def fromEnvironment(
        cls,
        environ: Optional[Mapping[str, str]] = None,
        start: Optional[int] = None,
    ) -> "ListenFDs":
        """
        @param environ: A dictionary-like object to inspect to discover
            inherited descriptors.  By default, L{None}, indicating that the
            real process environment should be inspected.  The default is
            suitable for typical usage.

        @param start: An integer giving the lowest value of an inherited
            descriptor systemd will give us.  By default, L{None}, indicating
            the known correct (that is, in agreement with systemd) value will be
            used.  The default is suitable for typical usage.

        @return: A new instance of C{cls} which can be used to look up the
            descriptors which have been inherited.
        """
        if environ is None:
            from os import environ as _environ

            environ = _environ
        if start is None:
            start = cls._START

        if str(getpid()) == environ.get("LISTEN_PID"):
            descriptors: List[int] = _parseDescriptors(start, environ)
            names: Sequence[str] = _parseNames(environ)
        else:
            descriptors = []
            names = ()

        # They may both be missing (consistent with not running under systemd
        # at all) or they may both be present (consistent with running under
        # systemd 227 or newer).  It is not allowed for only one to be present
        # or for the values to disagree with each other (per
        # systemd.socket(5), systemd will use a default value based on the
        # socket unit name if the socket unit doesn't explicitly define a name
        # with FileDescriptorName).
        if len(names) != len(descriptors):
            return cls([], ())

        return cls(descriptors, names)

    def inheritedDescriptors(self) -> List[int]:
        """
        @return: The configured descriptors.
        """
        return list(self._descriptors)

    def inheritedNamedDescriptors(self) -> Dict[str, int]:
        """
        @return: A mapping from the names of configured descriptors to
            their integer values.
        """
        return dict(zip(self._names, self._descriptors))


def _parseDescriptors(start: int, environ: Mapping[str, str]) -> List[int]:
    """
    Parse the I{LISTEN_FDS} environment variable supplied by systemd.

    @param start: systemd provides only a count of the number of descriptors
        that have been inherited.  This is the integer value of the first
        inherited descriptor.  Subsequent inherited descriptors are numbered
        counting up from here.  See L{ListenFDs._START}.

    @param environ: The environment variable mapping in which to look for the
        value to parse.

    @return: The integer values of the inherited file descriptors, in order.
    """
    try:
        count = int(environ["LISTEN_FDS"])
    except (KeyError, ValueError):
        return []
    else:
        descriptors = list(range(start, start + count))

        # Remove the information from the environment so that a second
        # `ListenFDs` cannot find the same information.  This is a precaution
        # against some application code accidentally trying to handle the same
        # inherited descriptor more than once - which probably wouldn't work.
        #
        # This precaution is perhaps somewhat questionable since it is up to
        # the application itself to know whether its handling of the file
        # descriptor will actually be safe.  Also, nothing stops an
        # application from getting the same descriptor more than once using
        # multiple calls to `ListenFDs.inheritedDescriptors()` on the same
        # `ListenFDs` instance.
        del environ["LISTEN_PID"], environ["LISTEN_FDS"]
        return descriptors


def _parseNames(environ: Mapping[str, str]) -> Sequence[str]:
    """
    Parse the I{LISTEN_FDNAMES} environment variable supplied by systemd.

    @param environ: The environment variable mapping in which to look for the
        value to parse.

    @return: The names of the inherited descriptors, in order.
    """
    names = environ.get("LISTEN_FDNAMES", "")
    if len(names) > 0:
        return tuple(names.split(":"))
    return ()
