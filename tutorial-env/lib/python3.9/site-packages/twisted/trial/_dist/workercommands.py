# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Commands for telling a worker to load tests or run tests.

@since: 12.3
"""

from twisted.protocols.amp import Boolean, Command, Unicode

NativeString = Unicode


class Run(Command):
    """
    Run a test.
    """

    arguments = [(b"testCase", NativeString())]
    response = [(b"success", Boolean())]


class Start(Command):
    """
    Set up the worker process, giving the running directory.
    """

    arguments = [(b"directory", NativeString())]
    response = [(b"success", Boolean())]
