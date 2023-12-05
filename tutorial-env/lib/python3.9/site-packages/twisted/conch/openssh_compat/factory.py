# -*- test-case-name: twisted.conch.test.test_openssh_compat -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Factory for reading openssh configuration files: public keys, private keys, and
moduli file.
"""

import errno
import os

from twisted.conch.openssh_compat import primes
from twisted.conch.ssh import common, factory, keys
from twisted.python.util import runAsEffectiveUser


class OpenSSHFactory(factory.SSHFactory):
    dataRoot = "/usr/local/etc"
    # For openbsd which puts moduli in a different directory from keys.
    moduliRoot = "/usr/local/etc"

    def getPublicKeys(self):
        """
        Return the server public keys.
        """
        ks = {}
        for filename in os.listdir(self.dataRoot):
            if filename[:9] == "ssh_host_" and filename[-8:] == "_key.pub":
                try:
                    k = keys.Key.fromFile(os.path.join(self.dataRoot, filename))
                    t = common.getNS(k.blob())[0]
                    ks[t] = k
                except Exception as e:
                    self._log.error(
                        "bad public key file {filename}: {error}",
                        filename=filename,
                        error=e,
                    )
        return ks

    def getPrivateKeys(self):
        """
        Return the server private keys.
        """
        privateKeys = {}
        for filename in os.listdir(self.dataRoot):
            if filename[:9] == "ssh_host_" and filename[-4:] == "_key":
                fullPath = os.path.join(self.dataRoot, filename)
                try:
                    key = keys.Key.fromFile(fullPath)
                except OSError as e:
                    if e.errno == errno.EACCES:
                        # Not allowed, let's switch to root
                        key = runAsEffectiveUser(0, 0, keys.Key.fromFile, fullPath)
                        privateKeys[key.sshType()] = key
                    else:
                        raise
                except Exception as e:
                    self._log.error(
                        "bad public key file {filename}: {error}",
                        filename=filename,
                        error=e,
                    )
                else:
                    privateKeys[key.sshType()] = key
        return privateKeys

    def getPrimes(self):
        try:
            return primes.parseModuliFile(self.moduliRoot + "/moduli")
        except OSError:
            return None
