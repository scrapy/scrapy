# -*- test-case-name: twisted.web.test.test_httpauth -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Resource traversal integration with L{twisted.cred} to allow for
authentication and authorization of HTTP requests.
"""


from twisted.web._auth.basic import BasicCredentialFactory
from twisted.web._auth.digest import DigestCredentialFactory

# Expose HTTP authentication classes here.
from twisted.web._auth.wrapper import HTTPAuthSessionWrapper

__all__ = [
    "HTTPAuthSessionWrapper",
    "BasicCredentialFactory",
    "DigestCredentialFactory",
]
