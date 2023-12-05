# -*- test-case-name: twisted.application.runner.test.test_exit -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
System exit support.
"""

import typing
from enum import IntEnum
from sys import exit as sysexit, stderr, stdout
from typing import Union

try:
    import posix as Status
except ImportError:

    class Status:  # type: ignore[no-redef]
        """
        Object to hang C{EX_*} values off of as a substitute for L{posix}.
        """

        EX__BASE = 64

        EX_OK = 0
        EX_USAGE = EX__BASE
        EX_DATAERR = EX__BASE + 1
        EX_NOINPUT = EX__BASE + 2
        EX_NOUSER = EX__BASE + 3
        EX_NOHOST = EX__BASE + 4
        EX_UNAVAILABLE = EX__BASE + 5
        EX_SOFTWARE = EX__BASE + 6
        EX_OSERR = EX__BASE + 7
        EX_OSFILE = EX__BASE + 8
        EX_CANTCREAT = EX__BASE + 9
        EX_IOERR = EX__BASE + 10
        EX_TEMPFAIL = EX__BASE + 11
        EX_PROTOCOL = EX__BASE + 12
        EX_NOPERM = EX__BASE + 13
        EX_CONFIG = EX__BASE + 14


class ExitStatus(IntEnum):
    """
    Standard exit status codes for system programs.

    @cvar EX_OK: Successful termination.
    @cvar EX_USAGE: Command line usage error.
    @cvar EX_DATAERR: Data format error.
    @cvar EX_NOINPUT: Cannot open input.
    @cvar EX_NOUSER: Addressee unknown.
    @cvar EX_NOHOST: Host name unknown.
    @cvar EX_UNAVAILABLE: Service unavailable.
    @cvar EX_SOFTWARE: Internal software error.
    @cvar EX_OSERR: System error (e.g., can't fork).
    @cvar EX_OSFILE: Critical OS file missing.
    @cvar EX_CANTCREAT: Can't create (user) output file.
    @cvar EX_IOERR: Input/output error.
    @cvar EX_TEMPFAIL: Temporary failure; the user is invited to retry.
    @cvar EX_PROTOCOL: Remote error in protocol.
    @cvar EX_NOPERM: Permission denied.
    @cvar EX_CONFIG: Configuration error.
    """

    EX_OK = Status.EX_OK
    EX_USAGE = Status.EX_USAGE
    EX_DATAERR = Status.EX_DATAERR
    EX_NOINPUT = Status.EX_NOINPUT
    EX_NOUSER = Status.EX_NOUSER
    EX_NOHOST = Status.EX_NOHOST
    EX_UNAVAILABLE = Status.EX_UNAVAILABLE
    EX_SOFTWARE = Status.EX_SOFTWARE
    EX_OSERR = Status.EX_OSERR
    EX_OSFILE = Status.EX_OSFILE
    EX_CANTCREAT = Status.EX_CANTCREAT
    EX_IOERR = Status.EX_IOERR
    EX_TEMPFAIL = Status.EX_TEMPFAIL
    EX_PROTOCOL = Status.EX_PROTOCOL
    EX_NOPERM = Status.EX_NOPERM
    EX_CONFIG = Status.EX_CONFIG


def exit(status: Union[int, ExitStatus], message: str = "") -> "typing.NoReturn":
    """
    Exit the python interpreter with the given status and an optional message.

    @param status: An exit status. An appropriate value from L{ExitStatus} is
        recommended.
    @param message: An optional message to print.
    """
    if message:
        if status == ExitStatus.EX_OK:
            out = stdout
        else:
            out = stderr
        out.write(message)
        out.write("\n")

    sysexit(status)
