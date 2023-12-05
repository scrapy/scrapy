# -*- test-case-name: twisted.conch.test.test_knownhosts,twisted.conch.test.test_default -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Various classes and functions for implementing user-interaction in the
command-line conch client.

You probably shouldn't use anything in this module directly, since it assumes
you are sitting at an interactive terminal.  For example, to programmatically
interact with a known_hosts database, use L{twisted.conch.client.knownhosts}.
"""

import contextlib
import getpass
import io
import os
import sys
from base64 import decodebytes

from twisted.conch.client import agent
from twisted.conch.client.knownhosts import ConsoleUI, KnownHostsFile
from twisted.conch.error import ConchError
from twisted.conch.ssh import common, keys, userauth
from twisted.internet import defer, protocol, reactor
from twisted.python.compat import nativeString
from twisted.python.filepath import FilePath

# The default location of the known hosts file (probably should be parsed out
# of an ssh config file someday).
_KNOWN_HOSTS = "~/.ssh/known_hosts"


# This name is bound so that the unit tests can use 'patch' to override it.
_open = open
_input = input


def verifyHostKey(transport, host, pubKey, fingerprint):
    """
    Verify a host's key.

    This function is a gross vestige of some bad factoring in the client
    internals.  The actual implementation, and a better signature of this logic
    is in L{KnownHostsFile.verifyHostKey}.  This function is not deprecated yet
    because the callers have not yet been rehabilitated, but they should
    eventually be changed to call that method instead.

    However, this function does perform two functions not implemented by
    L{KnownHostsFile.verifyHostKey}.  It determines the path to the user's
    known_hosts file based on the options (which should really be the options
    object's job), and it provides an opener to L{ConsoleUI} which opens
    '/dev/tty' so that the user will be prompted on the tty of the process even
    if the input and output of the process has been redirected.  This latter
    part is, somewhat obviously, not portable, but I don't know of a portable
    equivalent that could be used.

    @param host: Due to a bug in L{SSHClientTransport.verifyHostKey}, this is
    always the dotted-quad IP address of the host being connected to.
    @type host: L{str}

    @param transport: the client transport which is attempting to connect to
    the given host.
    @type transport: L{SSHClientTransport}

    @param fingerprint: the fingerprint of the given public key, in
    xx:xx:xx:... format.  This is ignored in favor of getting the fingerprint
    from the key itself.
    @type fingerprint: L{str}

    @param pubKey: The public key of the server being connected to.
    @type pubKey: L{str}

    @return: a L{Deferred} which fires with C{1} if the key was successfully
    verified, or fails if the key could not be successfully verified.  Failure
    types may include L{HostKeyChanged}, L{UserRejectedKey}, L{IOError} or
    L{KeyboardInterrupt}.
    """
    actualHost = transport.factory.options["host"]
    actualKey = keys.Key.fromString(pubKey)
    kh = KnownHostsFile.fromPath(
        FilePath(
            transport.factory.options["known-hosts"] or os.path.expanduser(_KNOWN_HOSTS)
        )
    )
    ui = ConsoleUI(lambda: _open("/dev/tty", "r+b", buffering=0))
    return kh.verifyHostKey(ui, actualHost, host, actualKey)


def isInKnownHosts(host, pubKey, options):
    """
    Checks to see if host is in the known_hosts file for the user.

    @return: 0 if it isn't, 1 if it is and is the same, 2 if it's changed.
    @rtype: L{int}
    """
    keyType = common.getNS(pubKey)[0]
    retVal = 0

    if not options["known-hosts"] and not os.path.exists(os.path.expanduser("~/.ssh/")):
        print("Creating ~/.ssh directory...")
        os.mkdir(os.path.expanduser("~/.ssh"))
    kh_file = options["known-hosts"] or _KNOWN_HOSTS
    try:
        known_hosts = open(os.path.expanduser(kh_file), "rb")
    except OSError:
        return 0
    with known_hosts:
        for line in known_hosts.readlines():
            split = line.split()
            if len(split) < 3:
                continue
            hosts, hostKeyType, encodedKey = split[:3]
            if host not in hosts.split(b","):  # incorrect host
                continue
            if hostKeyType != keyType:  # incorrect type of key
                continue
            try:
                decodedKey = decodebytes(encodedKey)
            except BaseException:
                continue
            if decodedKey == pubKey:
                return 1
            else:
                retVal = 2
    return retVal


def getHostKeyAlgorithms(host, options):
    """
    Look in known_hosts for a key corresponding to C{host}.
    This can be used to change the order of supported key types
    in the KEXINIT packet.

    @type host: L{str}
    @param host: the host to check in known_hosts
    @type options: L{twisted.conch.client.options.ConchOptions}
    @param options: options passed to client
    @return: L{list} of L{str} representing key types or L{None}.
    """
    knownHosts = KnownHostsFile.fromPath(
        FilePath(options["known-hosts"] or os.path.expanduser(_KNOWN_HOSTS))
    )
    keyTypes = []
    for entry in knownHosts.iterentries():
        if entry.matchesHost(host):
            if entry.keyType not in keyTypes:
                keyTypes.append(entry.keyType)
    return keyTypes or None


class SSHUserAuthClient(userauth.SSHUserAuthClient):
    def __init__(self, user, options, *args):
        userauth.SSHUserAuthClient.__init__(self, user, *args)
        self.keyAgent = None
        self.options = options
        self.usedFiles = []
        if not options.identitys:
            options.identitys = ["~/.ssh/id_rsa", "~/.ssh/id_dsa"]

    def serviceStarted(self):
        if "SSH_AUTH_SOCK" in os.environ and not self.options["noagent"]:
            self._log.debug(
                "using SSH agent {authSock!r}", authSock=os.environ["SSH_AUTH_SOCK"]
            )
            cc = protocol.ClientCreator(reactor, agent.SSHAgentClient)
            d = cc.connectUNIX(os.environ["SSH_AUTH_SOCK"])
            d.addCallback(self._setAgent)
            d.addErrback(self._ebSetAgent)
        else:
            userauth.SSHUserAuthClient.serviceStarted(self)

    def serviceStopped(self):
        if self.keyAgent:
            self.keyAgent.transport.loseConnection()
            self.keyAgent = None

    def _setAgent(self, a):
        self.keyAgent = a
        d = self.keyAgent.getPublicKeys()
        d.addBoth(self._ebSetAgent)
        return d

    def _ebSetAgent(self, f):
        userauth.SSHUserAuthClient.serviceStarted(self)

    def _getPassword(self, prompt):
        """
        Prompt for a password using L{getpass.getpass}.

        @param prompt: Written on tty to ask for the input.
        @type prompt: L{str}
        @return: The input.
        @rtype: L{str}
        """
        with self._replaceStdoutStdin():
            try:
                p = getpass.getpass(prompt)
                return p
            except (KeyboardInterrupt, OSError):
                print()
                raise ConchError("PEBKAC")

    def getPassword(self, prompt=None):
        if prompt:
            prompt = nativeString(prompt)
        else:
            prompt = "{}@{}'s password: ".format(
                nativeString(self.user),
                self.transport.transport.getPeer().host,
            )
        try:
            # We don't know the encoding the other side is using,
            # signaling that is not part of the SSH protocol. But
            # using our defaultencoding is better than just going for
            # ASCII.
            p = self._getPassword(prompt).encode(sys.getdefaultencoding())
            return defer.succeed(p)
        except ConchError:
            return defer.fail()

    def getPublicKey(self):
        """
        Get a public key from the key agent if possible, otherwise look in
        the next configured identity file for one.
        """
        if self.keyAgent:
            key = self.keyAgent.getPublicKey()
            if key is not None:
                return key
        files = [x for x in self.options.identitys if x not in self.usedFiles]
        self._log.debug(
            "public key identities: {identities}\n{files}",
            identities=self.options.identitys,
            files=files,
        )
        if not files:
            return None
        file = files[0]
        self.usedFiles.append(file)
        file = os.path.expanduser(file)
        file += ".pub"
        if not os.path.exists(file):
            return self.getPublicKey()  # try again
        try:
            return keys.Key.fromFile(file)
        except keys.BadKeyError:
            return self.getPublicKey()  # try again

    def signData(self, publicKey, signData):
        """
        Extend the base signing behavior by using an SSH agent to sign the
        data, if one is available.

        @type publicKey: L{Key}
        @type signData: L{bytes}
        """
        if not self.usedFiles:  # agent key
            return self.keyAgent.signData(publicKey.blob(), signData)
        else:
            return userauth.SSHUserAuthClient.signData(self, publicKey, signData)

    def getPrivateKey(self):
        """
        Try to load the private key from the last used file identified by
        C{getPublicKey}, potentially asking for the passphrase if the key is
        encrypted.
        """
        file = os.path.expanduser(self.usedFiles[-1])
        if not os.path.exists(file):
            return None
        try:
            return defer.succeed(keys.Key.fromFile(file))
        except keys.EncryptedKeyError:
            for i in range(3):
                prompt = "Enter passphrase for key '%s': " % self.usedFiles[-1]
                try:
                    p = self._getPassword(prompt).encode(sys.getfilesystemencoding())
                    return defer.succeed(keys.Key.fromFile(file, passphrase=p))
                except (keys.BadKeyError, ConchError):
                    pass
                return defer.fail(ConchError("bad password"))
            raise
        except KeyboardInterrupt:
            print()
            reactor.stop()

    def getGenericAnswers(self, name, instruction, prompts):
        responses = []
        with self._replaceStdoutStdin():
            if name:
                print(name.decode("utf-8"))
            if instruction:
                print(instruction.decode("utf-8"))
            for prompt, echo in prompts:
                prompt = prompt.decode("utf-8")
                if echo:
                    responses.append(_input(prompt))
                else:
                    responses.append(getpass.getpass(prompt))
        return defer.succeed(responses)

    @classmethod
    def _openTty(cls):
        """
        Open /dev/tty as two streams one in read, one in write mode,
        and return them.

        @return: File objects for reading and writing to /dev/tty,
                 corresponding to standard input and standard output.
        @rtype: A L{tuple} of L{io.TextIOWrapper} on Python 3.
        """
        stdin = io.TextIOWrapper(open("/dev/tty", "rb"))
        stdout = io.TextIOWrapper(open("/dev/tty", "wb"))
        return stdin, stdout

    @classmethod
    @contextlib.contextmanager
    def _replaceStdoutStdin(cls):
        """
        Contextmanager that replaces stdout and stdin with /dev/tty
        and resets them when it is done.
        """
        oldout, oldin = sys.stdout, sys.stdin
        sys.stdin, sys.stdout = cls._openTty()
        try:
            yield
        finally:
            sys.stdout.close()
            sys.stdin.close()
            sys.stdout, sys.stdin = oldout, oldin
