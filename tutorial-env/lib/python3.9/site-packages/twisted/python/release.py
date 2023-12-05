# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A release-automation toolkit.

Don't use this outside of Twisted.

Maintainer: Christopher Armstrong
"""


import os

# errors


class DirectoryExists(OSError):
    """
    Some directory exists when it shouldn't.
    """

    pass


class DirectoryDoesntExist(OSError):
    """
    Some directory doesn't exist when it should.
    """

    pass


class CommandFailed(OSError):
    pass


# utilities


def sh(command, null=True, prompt=False):
    """
    I'll try to execute C{command}, and if C{prompt} is true, I'll
    ask before running it.  If the command returns something other
    than 0, I'll raise C{CommandFailed(command)}.
    """
    print("--$", command)

    if prompt:
        if input("run ?? ").startswith("n"):
            return
    if null:
        command = "%s > /dev/null" % command
    if os.system(command) != 0:
        raise CommandFailed(command)


def runChdirSafe(f, *args, **kw):
    origdir = os.path.abspath(".")
    try:
        return f(*args, **kw)
    finally:
        os.chdir(origdir)
