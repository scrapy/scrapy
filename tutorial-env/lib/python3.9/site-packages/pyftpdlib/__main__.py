# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

"""
Start a stand alone anonymous FTP server from the command line as in:

$ python3 -m pyftpdlib
"""

import logging
import optparse
import os
import sys

from . import __ver__
from ._compat import getcwdu
from .authorizers import DummyAuthorizer
from .handlers import FTPHandler
from .log import config_logging
from .servers import FTPServer


class CustomizedOptionFormatter(optparse.IndentedHelpFormatter):
    """Formats options shown in help in a prettier way."""

    def format_option(self, option):
        result = []
        opts = self.option_strings[option]
        result.append('  %s\n' % opts)
        if option.help:
            help_text = '     %s\n\n' % self.expand_default(option)
            result.append(help_text)
        return ''.join(result)


def main():
    """Start a stand alone anonymous FTP server."""
    usage = "python3 -m pyftpdlib [options]"
    parser = optparse.OptionParser(usage=usage, description=main.__doc__,
                                   formatter=CustomizedOptionFormatter())
    parser.add_option('-i', '--interface', default=None, metavar="ADDRESS",
                      help="specify the interface to run on (default all "
                           "interfaces)")
    parser.add_option('-p', '--port', type="int", default=2121, metavar="PORT",
                      help="specify port number to run on (default 2121)")
    parser.add_option('-w', '--write', action="store_true", default=False,
                      help="grants write access for logged in user "
                           "(default read-only)")
    parser.add_option('-d', '--directory', default=getcwdu(), metavar="FOLDER",
                      help="specify the directory to share (default current "
                           "directory)")
    parser.add_option('-n', '--nat-address', default=None, metavar="ADDRESS",
                      help="the NAT address to use for passive connections")
    parser.add_option('-r', '--range', default=None, metavar="FROM-TO",
                      help="the range of TCP ports to use for passive "
                           "connections (e.g. -r 8000-9000)")
    parser.add_option('-D', '--debug', action='store_true',
                      help="enable DEBUG logging level")
    parser.add_option('-v', '--version', action='store_true',
                      help="print pyftpdlib version and exit")
    parser.add_option('-V', '--verbose', action='store_true',
                      help="activate a more verbose logging")
    parser.add_option('-u', '--username', type=str, default=None,
                      help="specify username to login with (anonymous login "
                           "will be disabled and password required "
                           "if supplied)")
    parser.add_option('-P', '--password', type=str, default=None,
                      help="specify a password to login with (username "
                           "required to be useful)")

    options, args = parser.parse_args()
    if options.version:
        sys.exit("pyftpdlib %s" % __ver__)
    if options.debug:
        config_logging(level=logging.DEBUG)

    passive_ports = None
    if options.range:
        try:
            start, stop = options.range.split('-')
            start = int(start)
            stop = int(stop)
        except ValueError:
            parser.error('invalid argument passed to -r option')
        else:
            passive_ports = list(range(start, stop + 1))
    # On recent Windows versions, if address is not specified and IPv6
    # is installed the socket will listen on IPv6 by default; in this
    # case we force IPv4 instead.
    if os.name in ('nt', 'ce') and not options.interface:
        options.interface = '0.0.0.0'

    authorizer = DummyAuthorizer()
    perm = "elradfmwMT" if options.write else "elr"
    if options.username:
        if not options.password:
            parser.error(
                "if username (-u) is supplied, password ('-P') is required")
        authorizer.add_user(options.username,
                            options.password,
                            options.directory,
                            perm=perm)
    else:
        authorizer.add_anonymous(options.directory, perm=perm)

    handler = FTPHandler
    handler.authorizer = authorizer
    handler.masquerade_address = options.nat_address
    handler.passive_ports = passive_ports

    ftpd = FTPServer((options.interface, options.port), FTPHandler)
    # On Windows specify a timeout for the underlying select() so
    # that the server can be interrupted with CTRL + C.
    try:
        ftpd.serve_forever(timeout=2 if os.name == 'nt' else None)
    finally:
        ftpd.close_all()


if __name__ == '__main__':
    main()
