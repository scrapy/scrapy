# -*- test-case-name: twisted.test.test_ftp_options -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
I am the support module for making a ftp server with twistd.
"""

import warnings

from twisted.application import internet
from twisted.cred import checkers, portal, strcred
from twisted.protocols import ftp
from twisted.python import deprecate, usage, versions


class Options(usage.Options, strcred.AuthOptionMixin):
    synopsis = """[options].
    WARNING: This FTP server is probably INSECURE do not use it.
    """
    optParameters = [
        ["port", "p", "2121", "set the port number"],
        ["root", "r", "/usr/local/ftp", "define the root of the ftp-site."],
        ["userAnonymous", "", "anonymous", "Name of the anonymous user."],
    ]

    compData = usage.Completions(
        optActions={"root": usage.CompleteDirs(descr="root of the ftp site")}
    )

    longdesc = ""

    def __init__(self, *a, **kw):
        usage.Options.__init__(self, *a, **kw)
        self.addChecker(checkers.AllowAnonymousAccess())

    def opt_password_file(self, filename):
        """
        Specify a file containing username:password login info for
        authenticated connections. (DEPRECATED; see --help-auth instead)
        """
        self["password-file"] = filename
        msg = deprecate.getDeprecationWarningString(
            self.opt_password_file, versions.Version("Twisted", 11, 1, 0)
        )
        warnings.warn(msg, category=DeprecationWarning, stacklevel=2)
        self.addChecker(checkers.FilePasswordDB(filename, cache=True))


def makeService(config):
    f = ftp.FTPFactory()

    r = ftp.FTPRealm(config["root"])
    p = portal.Portal(r, config.get("credCheckers", []))

    f.tld = config["root"]
    f.userAnonymous = config["userAnonymous"]
    f.portal = p
    f.protocol = ftp.FTP

    try:
        portno = int(config["port"])
    except KeyError:
        portno = 2121
    return internet.TCPServer(portno, f)
