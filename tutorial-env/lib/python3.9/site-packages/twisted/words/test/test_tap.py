# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.cred import credentials, error
from twisted.trial import unittest
from twisted.words import tap


class WordsTapTests(unittest.TestCase):
    """
    Ensures that the twisted.words.tap API works.
    """

    PASSWD_TEXT = b"admin:admin\njoe:foo\n"
    admin = credentials.UsernamePassword(b"admin", b"admin")
    joeWrong = credentials.UsernamePassword(b"joe", b"bar")

    def setUp(self):
        """
        Create a file with two users.
        """
        self.filename = self.mktemp()
        self.file = open(self.filename, "wb")
        self.file.write(self.PASSWD_TEXT)
        self.file.flush()

    def tearDown(self):
        """
        Close the dummy user database.
        """
        self.file.close()

    def test_hostname(self):
        """
        Tests that the --hostname parameter gets passed to Options.
        """
        opt = tap.Options()
        opt.parseOptions(["--hostname", "myhost"])
        self.assertEqual(opt["hostname"], "myhost")

    def test_passwd(self):
        """
        Tests the --passwd command for backwards-compatibility.
        """
        opt = tap.Options()
        opt.parseOptions(["--passwd", self.file.name])
        self._loginTest(opt)

    def test_auth(self):
        """
        Tests that the --auth command generates a checker.
        """
        opt = tap.Options()
        opt.parseOptions(["--auth", "file:" + self.file.name])
        self._loginTest(opt)

    def _loginTest(self, opt):
        """
        This method executes both positive and negative authentication
        tests against whatever credentials checker has been stored in
        the Options class.

        @param opt: An instance of L{tap.Options}.
        """
        self.assertEqual(len(opt["credCheckers"]), 1)
        checker = opt["credCheckers"][0]
        self.assertFailure(
            checker.requestAvatarId(self.joeWrong), error.UnauthorizedLogin
        )

        def _gotAvatar(username):
            self.assertEqual(username, self.admin.username)

        return checker.requestAvatarId(self.admin).addCallback(_gotAvatar)
