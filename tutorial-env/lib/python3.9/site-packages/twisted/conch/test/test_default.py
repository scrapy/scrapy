# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.client.default}.
"""


import sys
from unittest import skipIf

from twisted.conch.error import ConchError
from twisted.conch.test import keydata
from twisted.python.compat import nativeString
from twisted.python.filepath import FilePath
from twisted.python.reflect import requireModule
from twisted.python.runtime import platform
from twisted.test.proto_helpers import StringTransport
from twisted.trial.unittest import TestCase

doSkip = False
skipReason = ""

if requireModule("cryptography") and requireModule("pyasn1"):
    from twisted.conch.client import default
    from twisted.conch.client.agent import SSHAgentClient
    from twisted.conch.client.default import SSHUserAuthClient
    from twisted.conch.client.options import ConchOptions
    from twisted.conch.ssh.keys import Key
else:
    doSkip = True
    skipReason = "cryptography and PyASN1 required for twisted.conch.client.default."
    skip = skipReason  # no SSL available, skip the entire module

if platform.isWindows():
    doSkip = True
    skipReason = (
        "genericAnswers and getPassword does not work on Windows."
        " Should be fixed as part of fixing bug 6409 and 6410"
    )

if not sys.stdin.isatty():
    doSkip = True
    skipReason = "sys.stdin is not an interactive tty"
if not sys.stdout.isatty():
    doSkip = True
    skipReason = "sys.stdout is not an interactive tty"


class SSHUserAuthClientTests(TestCase):
    """
    Tests for L{SSHUserAuthClient}.

    @type rsaPublic: L{Key}
    @ivar rsaPublic: A public RSA key.
    """

    def setUp(self):
        self.rsaPublic = Key.fromString(keydata.publicRSA_openssh)
        self.tmpdir = FilePath(self.mktemp())
        self.tmpdir.makedirs()
        self.rsaFile = self.tmpdir.child("id_rsa")
        self.rsaFile.setContent(keydata.privateRSA_openssh)
        self.tmpdir.child("id_rsa.pub").setContent(keydata.publicRSA_openssh)

    def test_signDataWithAgent(self):
        """
        When connected to an agent, L{SSHUserAuthClient} can use it to
        request signatures of particular data with a particular L{Key}.
        """
        client = SSHUserAuthClient(b"user", ConchOptions(), None)
        agent = SSHAgentClient()
        transport = StringTransport()
        agent.makeConnection(transport)
        client.keyAgent = agent
        cleartext = b"Sign here"
        client.signData(self.rsaPublic, cleartext)
        self.assertEqual(
            transport.value(),
            b"\x00\x00\x01\x2d\r\x00\x00\x01\x17"
            + self.rsaPublic.blob()
            + b"\x00\x00\x00\t"
            + cleartext
            + b"\x00\x00\x00\x00",
        )

    def test_agentGetPublicKey(self):
        """
        L{SSHUserAuthClient} looks up public keys from the agent using the
        L{SSHAgentClient} class.  That L{SSHAgentClient.getPublicKey} returns a
        L{Key} object with one of the public keys in the agent.  If no more
        keys are present, it returns L{None}.
        """
        agent = SSHAgentClient()
        agent.blobs = [self.rsaPublic.blob()]
        key = agent.getPublicKey()
        self.assertTrue(key.isPublic())
        self.assertEqual(key, self.rsaPublic)
        self.assertIsNone(agent.getPublicKey())

    def test_getPublicKeyFromFile(self):
        """
        L{SSHUserAuthClient.getPublicKey()} is able to get a public key from
        the first file described by its options' C{identitys} list, and return
        the corresponding public L{Key} object.
        """
        options = ConchOptions()
        options.identitys = [self.rsaFile.path]
        client = SSHUserAuthClient(b"user", options, None)
        key = client.getPublicKey()
        self.assertTrue(key.isPublic())
        self.assertEqual(key, self.rsaPublic)

    def test_getPublicKeyAgentFallback(self):
        """
        If an agent is present, but doesn't return a key,
        L{SSHUserAuthClient.getPublicKey} continue with the normal key lookup.
        """
        options = ConchOptions()
        options.identitys = [self.rsaFile.path]
        agent = SSHAgentClient()
        client = SSHUserAuthClient(b"user", options, None)
        client.keyAgent = agent
        key = client.getPublicKey()
        self.assertTrue(key.isPublic())
        self.assertEqual(key, self.rsaPublic)

    def test_getPublicKeyBadKeyError(self):
        """
        If L{keys.Key.fromFile} raises a L{keys.BadKeyError}, the
        L{SSHUserAuthClient.getPublicKey} tries again to get a public key by
        calling itself recursively.
        """
        options = ConchOptions()
        self.tmpdir.child("id_dsa.pub").setContent(keydata.publicDSA_openssh)
        dsaFile = self.tmpdir.child("id_dsa")
        dsaFile.setContent(keydata.privateDSA_openssh)
        options.identitys = [self.rsaFile.path, dsaFile.path]
        self.tmpdir.child("id_rsa.pub").setContent(b"not a key!")
        client = SSHUserAuthClient(b"user", options, None)
        key = client.getPublicKey()
        self.assertTrue(key.isPublic())
        self.assertEqual(key, Key.fromString(keydata.publicDSA_openssh))
        self.assertEqual(client.usedFiles, [self.rsaFile.path, dsaFile.path])

    def test_getPrivateKey(self):
        """
        L{SSHUserAuthClient.getPrivateKey} will load a private key from the
        last used file populated by L{SSHUserAuthClient.getPublicKey}, and
        return a L{Deferred} which fires with the corresponding private L{Key}.
        """
        rsaPrivate = Key.fromString(keydata.privateRSA_openssh)
        options = ConchOptions()
        options.identitys = [self.rsaFile.path]
        client = SSHUserAuthClient(b"user", options, None)
        # Populate the list of used files
        client.getPublicKey()

        def _cbGetPrivateKey(key):
            self.assertFalse(key.isPublic())
            self.assertEqual(key, rsaPrivate)

        return client.getPrivateKey().addCallback(_cbGetPrivateKey)

    def test_getPrivateKeyPassphrase(self):
        """
        L{SSHUserAuthClient} can get a private key from a file, and return a
        Deferred called back with a private L{Key} object, even if the key is
        encrypted.
        """
        rsaPrivate = Key.fromString(keydata.privateRSA_openssh)
        passphrase = b"this is the passphrase"
        self.rsaFile.setContent(rsaPrivate.toString("openssh", passphrase=passphrase))
        options = ConchOptions()
        options.identitys = [self.rsaFile.path]
        client = SSHUserAuthClient(b"user", options, None)
        # Populate the list of used files
        client.getPublicKey()

        def _getPassword(prompt):
            self.assertEqual(
                prompt, f"Enter passphrase for key '{self.rsaFile.path}': "
            )
            return nativeString(passphrase)

        def _cbGetPrivateKey(key):
            self.assertFalse(key.isPublic())
            self.assertEqual(key, rsaPrivate)

        self.patch(client, "_getPassword", _getPassword)
        return client.getPrivateKey().addCallback(_cbGetPrivateKey)

    @skipIf(doSkip, skipReason)
    def test_getPassword(self):
        """
        Get the password using
        L{twisted.conch.client.default.SSHUserAuthClient.getPassword}
        """

        class FakeTransport:
            def __init__(self, host):
                self.transport = self
                self.host = host

            def getPeer(self):
                return self

        options = ConchOptions()
        client = SSHUserAuthClient(b"user", options, None)
        client.transport = FakeTransport("127.0.0.1")

        def getpass(prompt):
            self.assertEqual(prompt, "user@127.0.0.1's password: ")
            return "bad password"

        self.patch(default.getpass, "getpass", getpass)
        d = client.getPassword()
        d.addCallback(self.assertEqual, b"bad password")
        return d

    @skipIf(doSkip, skipReason)
    def test_getPasswordPrompt(self):
        """
        Get the password using
        L{twisted.conch.client.default.SSHUserAuthClient.getPassword}
        using a different prompt.
        """
        options = ConchOptions()
        client = SSHUserAuthClient(b"user", options, None)
        prompt = b"Give up your password"

        def getpass(p):
            self.assertEqual(p, nativeString(prompt))
            return "bad password"

        self.patch(default.getpass, "getpass", getpass)
        d = client.getPassword(prompt)
        d.addCallback(self.assertEqual, b"bad password")
        return d

    @skipIf(doSkip, skipReason)
    def test_getPasswordConchError(self):
        """
        Get the password using
        L{twisted.conch.client.default.SSHUserAuthClient.getPassword}
        and trigger a {twisted.conch.error import ConchError}.
        """
        options = ConchOptions()
        client = SSHUserAuthClient(b"user", options, None)

        def getpass(prompt):
            raise KeyboardInterrupt("User pressed CTRL-C")

        self.patch(default.getpass, "getpass", getpass)
        stdout, stdin = sys.stdout, sys.stdin
        d = client.getPassword(b"?")

        @d.addErrback
        def check_sys(fail):
            self.assertEqual([stdout, stdin], [sys.stdout, sys.stdin])
            return fail

        self.assertFailure(d, ConchError)

    @skipIf(doSkip, skipReason)
    def test_getGenericAnswers(self):
        """
        L{twisted.conch.client.default.SSHUserAuthClient.getGenericAnswers}
        """
        options = ConchOptions()
        client = SSHUserAuthClient(b"user", options, None)

        def getpass(prompt):
            self.assertEqual(prompt, "pass prompt")
            return "getpass"

        self.patch(default.getpass, "getpass", getpass)

        def raw_input(prompt):
            self.assertEqual(prompt, "raw_input prompt")
            return "raw_input"

        self.patch(default, "_input", raw_input)
        d = client.getGenericAnswers(
            b"Name",
            b"Instruction",
            [(b"pass prompt", False), (b"raw_input prompt", True)],
        )
        d.addCallback(self.assertListEqual, ["getpass", "raw_input"])
        return d


class ConchOptionsParsing(TestCase):
    """
    Options parsing.
    """

    def test_macs(self):
        """
        Specify MAC algorithms.
        """
        opts = ConchOptions()
        e = self.assertRaises(SystemExit, opts.opt_macs, "invalid-mac")
        self.assertIn("Unknown mac type", e.code)
        opts = ConchOptions()
        opts.opt_macs("hmac-sha2-512")
        self.assertEqual(opts["macs"], [b"hmac-sha2-512"])
        opts.opt_macs(b"hmac-sha2-512")
        self.assertEqual(opts["macs"], [b"hmac-sha2-512"])
        opts.opt_macs("hmac-sha2-256,hmac-sha1,hmac-md5")
        self.assertEqual(opts["macs"], [b"hmac-sha2-256", b"hmac-sha1", b"hmac-md5"])

    def test_host_key_algorithms(self):
        """
        Specify host key algorithms.
        """
        opts = ConchOptions()
        e = self.assertRaises(SystemExit, opts.opt_host_key_algorithms, "invalid-key")
        self.assertIn("Unknown host key type", e.code)
        opts = ConchOptions()
        opts.opt_host_key_algorithms("ssh-rsa")
        self.assertEqual(opts["host-key-algorithms"], [b"ssh-rsa"])
        opts.opt_host_key_algorithms(b"ssh-dss")
        self.assertEqual(opts["host-key-algorithms"], [b"ssh-dss"])
        opts.opt_host_key_algorithms("ssh-rsa,ssh-dss")
        self.assertEqual(opts["host-key-algorithms"], [b"ssh-rsa", b"ssh-dss"])
