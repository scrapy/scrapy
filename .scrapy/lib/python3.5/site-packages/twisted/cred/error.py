# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cred errors.
"""

from __future__ import division, absolute_import


class Unauthorized(Exception):
    """Standard unauthorized error."""



class LoginFailed(Exception):
    """
    The user's request to log in failed for some reason.
    """



class UnauthorizedLogin(LoginFailed, Unauthorized):
    """The user was not authorized to log in.
    """



class UnhandledCredentials(LoginFailed):
    """A type of credentials were passed in with no knowledge of how to check
    them.  This is a server configuration error - it means that a protocol was
    connected to a Portal without a CredentialChecker that can check all of its
    potential authentication strategies.
    """



class LoginDenied(LoginFailed):
    """
    The realm rejected this login for some reason.

    Examples of reasons this might be raised include an avatar logging in
    too frequently, a quota having been fully used, or the overall server
    load being too high.
    """
