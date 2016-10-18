# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#
from twisted.conch.ssh.transport import SSHClientTransport, SSHCiphers
from twisted.python import usage

import sys

class ConchOptions(usage.Options):

    optParameters = [['user', 'l', None, 'Log in using this user name.'],
                     ['identity', 'i', None],
                     ['ciphers', 'c', None],
                     ['macs', 'm', None],
                     ['port', 'p', None, 'Connect to this port.  Server must be on the same port.'],
                     ['option', 'o', None, 'Ignored OpenSSH options'],
                     ['host-key-algorithms', '', None],
                     ['known-hosts', '', None, 'File to check for host keys'],
                     ['user-authentications', '', None, 'Types of user authentications to use.'],
                     ['logfile', '', None, 'File to log to, or - for stdout'],
                   ]

    optFlags = [['version', 'V', 'Display version number only.'],
                ['compress', 'C', 'Enable compression.'],
                ['log', 'v', 'Enable logging (defaults to stderr)'],
                ['nox11', 'x', 'Disable X11 connection forwarding (default)'],
                ['agent', 'A', 'Enable authentication agent forwarding'],
                ['noagent', 'a', 'Disable authentication agent forwarding (default)'],
                ['reconnect', 'r', 'Reconnect to the server if the connection is lost.'],
               ]

    compData = usage.Completions(
        mutuallyExclusive=[("agent", "noagent")],
        optActions={
            "user": usage.CompleteUsernames(),
            "ciphers": usage.CompleteMultiList(
                SSHCiphers.cipherMap.keys(),
                descr='ciphers to choose from'),
            "macs": usage.CompleteMultiList(
                SSHCiphers.macMap.keys(),
                descr='macs to choose from'),
            "host-key-algorithms": usage.CompleteMultiList(
                SSHClientTransport.supportedPublicKeys,
                descr='host key algorithms to choose from'),
            #"user-authentications": usage.CompleteMultiList(?
            # descr='user authentication types' ),
            },
        extraActions=[usage.CompleteUserAtHost(),
                      usage.Completer(descr="command"),
                      usage.Completer(descr='argument',
                                      repeat=True)]
        )

    def __init__(self, *args, **kw):
        usage.Options.__init__(self, *args, **kw)
        self.identitys = []
        self.conns = None

    def opt_identity(self, i):
        """Identity for public-key authentication"""
        self.identitys.append(i)

    def opt_ciphers(self, ciphers):
        "Select encryption algorithms"
        ciphers = ciphers.split(',')
        for cipher in ciphers:
            if cipher not in SSHCiphers.cipherMap:
                sys.exit("Unknown cipher type '%s'" % cipher)
        self['ciphers'] = ciphers


    def opt_macs(self, macs):
        "Specify MAC algorithms"
        macs = macs.split(',')
        for mac in macs:
            if mac not in SSHCiphers.macMap:
                sys.exit("Unknown mac type '%s'" % mac)
        self['macs'] = macs

    def opt_host_key_algorithms(self, hkas):
        "Select host key algorithms"
        hkas = hkas.split(',')
        for hka in hkas:
            if hka not in SSHClientTransport.supportedPublicKeys:
                sys.exit("Unknown host key type '%s'" % hka)
        self['host-key-algorithms'] = hkas

    def opt_user_authentications(self, uas):
        "Choose how to authenticate to the remote server"
        self['user-authentications'] = uas.split(',')

#    def opt_compress(self):
#        "Enable compression"
#        self.enableCompression = 1
#        SSHClientTransport.supportedCompressions[0:1] = ['zlib']
