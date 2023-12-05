# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

import contextlib
import errno
import ftplib
import io
import logging
import os
import random
import re
import select
import socket
import ssl
import stat
import time


try:
    from StringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

import unittest

from pyftpdlib._compat import PY3
from pyftpdlib._compat import b
from pyftpdlib._compat import super
from pyftpdlib._compat import u
from pyftpdlib.filesystems import AbstractedFS
from pyftpdlib.handlers import SUPPORTS_HYBRID_IPV6
from pyftpdlib.handlers import DTPHandler
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.handlers import ThrottledDTPHandler
from pyftpdlib.handlers import _import_sendfile
from pyftpdlib.ioloop import IOLoop
from pyftpdlib.servers import FTPServer
from pyftpdlib.test import BUFSIZE
from pyftpdlib.test import CI_TESTING
from pyftpdlib.test import GLOBAL_TIMEOUT
from pyftpdlib.test import HOME
from pyftpdlib.test import HOST
from pyftpdlib.test import INTERRUPTED_TRANSF_SIZE
from pyftpdlib.test import OSX
from pyftpdlib.test import PASSWD
from pyftpdlib.test import POSIX
from pyftpdlib.test import SUPPORTS_IPV4
from pyftpdlib.test import SUPPORTS_IPV6
from pyftpdlib.test import SUPPORTS_SENDFILE
from pyftpdlib.test import USER
from pyftpdlib.test import WINDOWS
from pyftpdlib.test import MProcessTestFTPd
from pyftpdlib.test import PyftpdlibTestCase
from pyftpdlib.test import ThreadedTestFTPd
from pyftpdlib.test import close_client
from pyftpdlib.test import disable_log_warning
from pyftpdlib.test import get_server_handler
from pyftpdlib.test import mock
from pyftpdlib.test import retry_on_failure
from pyftpdlib.test import safe_rmpath
from pyftpdlib.test import touch


sendfile = _import_sendfile()


class TestFtpAuthentication(PyftpdlibTestCase):
    """Test: USER, PASS, REIN."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.testfn = self.get_testfn()
        self.file = open(self.testfn, 'w+b')
        self.dummyfile = BytesIO()

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        if not self.file.closed:
            self.file.close()
        if not self.dummyfile.closed:
            self.dummyfile.close()
        super().tearDown()

    def assert_auth_failed(self, user, passwd):
        self.assertRaisesRegex(ftplib.error_perm, '530 Authentication failed',
                               self.client.login, user, passwd)

    def test_auth_ok(self):
        self.client.login(user=USER, passwd=PASSWD)

    def test_anon_auth(self):
        self.client.login(user='anonymous', passwd='anon@')
        self.client.login(user='anonymous', passwd='')
        # supposed to be case sensitive
        self.assert_auth_failed('AnoNymouS', 'foo')
        # empty passwords should be allowed
        self.client.sendcmd('user anonymous')
        self.client.sendcmd('pass ')
        self.client.sendcmd('user anonymous')
        self.client.sendcmd('pass')

    def test_auth_failed(self):
        self.assert_auth_failed(USER, 'wrong')
        self.assert_auth_failed('wrong', PASSWD)
        self.assert_auth_failed('wrong', 'wrong')

    def test_wrong_cmds_order(self):
        self.assertRaisesRegex(ftplib.error_perm, '503 Login with USER first',
                               self.client.sendcmd, 'pass ' + PASSWD)
        self.client.login(user=USER, passwd=PASSWD)
        self.assertRaisesRegex(ftplib.error_perm,
                               "503 User already authenticated.",
                               self.client.sendcmd, 'pass ' + PASSWD)

    def test_max_auth(self):
        self.assert_auth_failed(USER, 'wrong')
        self.assert_auth_failed(USER, 'wrong')
        self.assert_auth_failed(USER, 'wrong')
        # If authentication fails for 3 times ftpd disconnects the
        # client.  We can check if that happens by using self.client.sendcmd()
        # on the 'dead' socket object.  If socket object is really
        # closed it should be raised a socket.error exception (Windows)
        # or a EOFError exception (Linux).
        self.client.sock.settimeout(.1)
        self.assertRaises((socket.error, EOFError), self.client.sendcmd, '')

    def test_rein(self):
        self.client.login(user=USER, passwd=PASSWD)
        self.client.sendcmd('rein')
        # user not authenticated, error response expected
        self.assertRaisesRegex(ftplib.error_perm,
                               '530 Log in with USER and PASS first',
                               self.client.sendcmd, 'pwd')
        # by logging-in again we should be able to execute a
        # file-system command
        self.client.login(user=USER, passwd=PASSWD)
        self.client.sendcmd('pwd')

    @retry_on_failure()
    def test_rein_during_transfer(self):
        # Test REIN while already authenticated and a transfer is
        # in progress.
        self.client.login(user=USER, passwd=PASSWD)
        data = b'abcde12345' * 1000000
        self.file.write(data)
        self.file.close()

        conn = self.client.transfercmd('retr ' + self.testfn)
        with contextlib.closing(conn):
            rein_sent = False
            bytes_recv = 0
            while True:
                chunk = conn.recv(BUFSIZE)
                if not chunk:
                    break
                bytes_recv += len(chunk)
                self.dummyfile.write(chunk)
                if bytes_recv > INTERRUPTED_TRANSF_SIZE and not rein_sent:
                    rein_sent = True
                    # flush account, error response expected
                    self.client.sendcmd('rein')
                    self.assertRaisesRegex(
                        ftplib.error_perm,
                        '530 Log in with USER and PASS first',
                        self.client.dir)

        # a 226 response is expected once transfer finishes
        self.assertEqual(self.client.voidresp()[:3], '226')
        # account is still flushed, error response is still expected
        self.assertRaisesRegex(ftplib.error_perm,
                               '530 Log in with USER and PASS first',
                               self.client.sendcmd, 'size ' + self.testfn)
        # by logging-in again we should be able to execute a
        # filesystem command
        self.client.login(user=USER, passwd=PASSWD)
        self.client.sendcmd('pwd')
        self.dummyfile.seek(0)
        datafile = self.dummyfile.read()
        self.assertEqual(len(data), len(datafile))
        self.assertEqual(hash(data), hash(datafile))

    def test_user(self):
        # Test USER while already authenticated and no transfer
        # is in progress.
        self.client.login(user=USER, passwd=PASSWD)
        self.client.sendcmd('user ' + USER)  # authentication flushed
        self.assertRaisesRegex(ftplib.error_perm,
                               '530 Log in with USER and PASS first',
                               self.client.sendcmd, 'pwd')
        self.client.sendcmd('pass ' + PASSWD)
        self.client.sendcmd('pwd')

    def test_user_during_transfer(self):
        # Test USER while already authenticated and a transfer is
        # in progress.
        self.client.login(user=USER, passwd=PASSWD)
        data = b'abcde12345' * 1000000
        self.file.write(data)
        self.file.close()

        conn = self.client.transfercmd('retr ' + self.testfn)
        with contextlib.closing(conn):
            rein_sent = 0
            bytes_recv = 0
            while True:
                chunk = conn.recv(BUFSIZE)
                if not chunk:
                    break
                bytes_recv += len(chunk)
                self.dummyfile.write(chunk)
                # stop transfer while it isn't finished yet
                if bytes_recv > INTERRUPTED_TRANSF_SIZE and not rein_sent:
                    rein_sent = True
                    # flush account, expect an error response
                    self.client.sendcmd('user ' + USER)
                    self.assertRaisesRegex(
                        ftplib.error_perm,
                        '530 Log in with USER and PASS first',
                        self.client.dir)

            # a 226 response is expected once transfer finishes
            self.assertEqual(self.client.voidresp()[:3], '226')
            # account is still flushed, error response is still expected
            self.assertRaisesRegex(ftplib.error_perm,
                                   '530 Log in with USER and PASS first',
                                   self.client.sendcmd, 'pwd')
            # by logging-in again we should be able to execute a
            # filesystem command
            self.client.sendcmd('pass ' + PASSWD)
            self.client.sendcmd('pwd')
            self.dummyfile.seek(0)
            datafile = self.dummyfile.read()
            self.assertEqual(len(data), len(datafile))
            self.assertEqual(hash(data), hash(datafile))


class TestFtpDummyCmds(PyftpdlibTestCase):
    """Test: TYPE, STRU, MODE, NOOP, SYST, ALLO, HELP, SITE HELP."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def test_type(self):
        self.client.sendcmd('type a')
        self.client.sendcmd('type i')
        self.client.sendcmd('type l7')
        self.client.sendcmd('type l8')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'type ?!?')

    def test_stru(self):
        self.client.sendcmd('stru f')
        self.client.sendcmd('stru F')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'stru p')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'stru r')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'stru ?!?')

    def test_mode(self):
        self.client.sendcmd('mode s')
        self.client.sendcmd('mode S')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'mode b')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'mode c')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'mode ?!?')

    def test_noop(self):
        self.client.sendcmd('noop')

    def test_syst(self):
        self.client.sendcmd('syst')

    def test_allo(self):
        self.client.sendcmd('allo x')

    def test_quit(self):
        self.client.sendcmd('quit')

    def test_help(self):
        self.client.sendcmd('help')
        cmd = random.choice(list(FTPHandler.proto_cmds.keys()))
        self.client.sendcmd('help %s' % cmd)
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'help ?!?')

    def test_site(self):
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'site')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'site ?!?')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'site foo bar')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'sitefoo bar')

    def test_site_help(self):
        self.client.sendcmd('site help')
        self.client.sendcmd('site help help')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'site help ?!?')

    def test_rest(self):
        # Test error conditions only; resumed data transfers are
        # tested later.
        self.client.sendcmd('type i')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'rest')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'rest str')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'rest -1')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'rest 10.1')
        # REST is not supposed to be allowed in ASCII mode
        self.client.sendcmd('type a')
        self.assertRaisesRegex(ftplib.error_perm, 'not allowed in ASCII mode',
                               self.client.sendcmd, 'rest 10')

    def test_feat(self):
        resp = self.client.sendcmd('feat')
        self.assertIn('UTF8', resp)
        self.assertIn('TVFS', resp)

    def test_opts_feat(self):
        self.assertRaises(
            ftplib.error_perm, self.client.sendcmd, 'opts mlst bad_fact')
        self.assertRaises(
            ftplib.error_perm, self.client.sendcmd, 'opts mlst type ;')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'opts not_mlst')
        # utility function which used for extracting the MLST "facts"
        # string from the FEAT response

        def mlst():
            resp = self.client.sendcmd('feat')
            return re.search(r'^\s*MLST\s+(\S+)$', resp, re.MULTILINE).group(1)
        # we rely on "type", "perm", "size", and "modify" facts which
        # are those available on all platforms
        self.assertIn('type*;perm*;size*;modify*;', mlst())
        self.assertEqual(self.client.sendcmd(
            'opts mlst type;'), '200 MLST OPTS type;')
        self.assertEqual(self.client.sendcmd(
            'opts mLSt TypE;'), '200 MLST OPTS type;')
        self.assertIn('type*;perm;size;modify;', mlst())

        self.assertEqual(self.client.sendcmd('opts mlst'), '200 MLST OPTS ')
        self.assertNotIn('*', mlst())

        self.assertEqual(
            self.client.sendcmd('opts mlst fish;cakes;'), '200 MLST OPTS ')
        self.assertNotIn('*', mlst())
        self.assertEqual(self.client.sendcmd('opts mlst fish;cakes;type;'),
                         '200 MLST OPTS type;')
        self.assertIn('type*;perm;size;modify;', mlst())


class TestFtpCmdsSemantic(PyftpdlibTestCase):
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP
    arg_cmds = \
        ['allo', 'appe', 'dele', 'eprt', 'mdtm', 'mfmt', 'mode', 'mkd', 'opts',
         'port', 'rest', 'retr', 'rmd', 'rnfr', 'rnto', 'site', 'size', 'stor',
         'stru', 'type', 'user', 'xmkd', 'xrmd', 'site chmod']

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def test_arg_cmds(self):
        # Test commands requiring an argument.
        expected = "501 Syntax error: command needs an argument."
        for cmd in self.arg_cmds:
            self.client.putcmd(cmd)
            resp = self.client.getmultiline()
            self.assertEqual(resp, expected)

    def test_no_arg_cmds(self):
        # Test commands accepting no arguments.
        expected = "501 Syntax error: command does not accept arguments."
        narg_cmds = ['abor', 'cdup', 'feat', 'noop', 'pasv', 'pwd', 'quit',
                     'rein', 'syst', 'xcup', 'xpwd']
        for cmd in narg_cmds:
            self.client.putcmd(cmd + ' arg')
            resp = self.client.getmultiline()
            self.assertEqual(resp, expected)

    def test_auth_cmds(self):
        # Test those commands requiring client to be authenticated.
        expected = "530 Log in with USER and PASS first."
        self.client.sendcmd('rein')
        for cmd in self.server.handler.proto_cmds:
            cmd = cmd.lower()
            if cmd in ('feat', 'help', 'noop', 'user', 'pass', 'stat', 'syst',
                       'quit', 'site', 'site help', 'pbsz', 'auth', 'prot',
                       'ccc'):
                continue
            if cmd in self.arg_cmds:
                cmd = cmd + ' arg'
            self.client.putcmd(cmd)
            resp = self.client.getmultiline()
            self.assertEqual(resp, expected)

    def test_no_auth_cmds(self):
        # Test those commands that do not require client to be authenticated.
        self.client.sendcmd('rein')
        for cmd in ('feat', 'help', 'noop', 'stat', 'syst', 'site help'):
            self.client.sendcmd(cmd)
        # STAT provided with an argument is equal to LIST hence not allowed
        # if not authenticated
        self.assertRaisesRegex(ftplib.error_perm, '530 Log in with USER',
                               self.client.sendcmd, 'stat /')
        self.client.sendcmd('quit')


class TestFtpFsOperations(PyftpdlibTestCase):
    """Test: PWD, CWD, CDUP, SIZE, RNFR, RNTO, DELE, MKD, RMD, MDTM,
    STAT, MFMT.
    """
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)
        self.tempfile = self.get_testfn()
        self.tempdir = self.get_testfn()
        touch(self.tempfile)
        os.mkdir(self.tempdir)

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def test_cwd(self):
        self.client.cwd(self.tempdir)
        self.assertEqual(self.client.pwd(), '/' + self.tempdir)
        self.assertRaises(ftplib.error_perm, self.client.cwd, 'subtempdir')
        # cwd provided with no arguments is supposed to move us to the
        # root directory
        self.client.sendcmd('cwd')
        self.assertEqual(self.client.pwd(), u('/'))

    def test_pwd(self):
        self.assertEqual(self.client.pwd(), u('/'))
        self.client.cwd(self.tempdir)
        self.assertEqual(self.client.pwd(), '/' + self.tempdir)

    def test_cdup(self):
        subfolder = self.get_testfn(dir=self.tempdir)
        os.mkdir(os.path.join(self.tempdir, subfolder))
        self.assertEqual(self.client.pwd(), u('/'))
        self.client.cwd(self.tempdir)
        self.assertEqual(self.client.pwd(), '/%s' % self.tempdir)
        self.client.cwd(subfolder)
        self.assertEqual(self.client.pwd(),
                         '/%s/%s' % (self.tempdir, subfolder))
        self.client.sendcmd('cdup')
        self.assertEqual(self.client.pwd(), '/%s' % self.tempdir)
        self.client.sendcmd('cdup')
        self.assertEqual(self.client.pwd(), u('/'))

        # make sure we can't escape from root directory
        self.client.sendcmd('cdup')
        self.assertEqual(self.client.pwd(), u('/'))

    def test_mkd(self):
        tempdir = self.get_testfn()
        dirname = self.client.mkd(tempdir)
        # the 257 response is supposed to include the absolute dirname
        self.assertEqual(dirname, '/' + tempdir)
        # make sure we can't create directories which already exist
        # (probably not really necessary);
        # let's use a try/except statement to avoid leaving behind
        # orphaned temporary directory in the event of a test failure.
        try:
            self.client.mkd(tempdir)
        except ftplib.error_perm:
            os.rmdir(tempdir)  # ok
        else:
            self.fail('ftplib.error_perm not raised.')

    def test_rmd(self):
        self.client.rmd(self.tempdir)
        self.assertRaises(ftplib.error_perm, self.client.rmd, self.tempfile)
        # make sure we can't remove the root directory
        self.assertRaisesRegex(ftplib.error_perm,
                               "Can't remove root directory",
                               self.client.rmd, u('/'))

    def test_dele(self):
        self.client.delete(self.tempfile)
        self.assertRaises(ftplib.error_perm, self.client.delete, self.tempdir)

    def test_rnfr_rnto(self):
        # rename file
        tempname = self.get_testfn()
        self.client.rename(self.tempfile, tempname)
        self.client.rename(tempname, self.tempfile)
        # rename dir
        tempname = self.get_testfn()
        self.client.rename(self.tempdir, tempname)
        self.client.rename(tempname, self.tempdir)
        # rnfr/rnto over non-existing paths
        bogus = self.get_testfn()
        self.assertRaises(ftplib.error_perm, self.client.rename, bogus, '/x')
        self.assertRaises(
            ftplib.error_perm, self.client.rename, self.tempfile, u('/'))
        # rnto sent without first specifying the source
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'rnto ' + self.tempfile)

        # make sure we can't rename root directory
        self.assertRaisesRegex(ftplib.error_perm,
                               "Can't rename home directory",
                               self.client.rename, '/', '/x')

    def test_mdtm(self):
        self.client.sendcmd('mdtm ' + self.tempfile)
        bogus = self.get_testfn()
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'mdtm ' + bogus)
        # make sure we can't use mdtm against directories
        try:
            self.client.sendcmd('mdtm ' + self.tempdir)
        except ftplib.error_perm as err:
            self.assertIn("not retrievable", str(err))
        else:
            self.fail('Exception not raised')

    def test_mfmt(self):
        # making sure MFMT is able to modify the timestamp for the file
        test_timestamp = "20170921013410"
        self.client.sendcmd('mfmt ' + test_timestamp + ' ' + self.tempfile)
        resp_time = os.path.getmtime(self.tempfile)
        resp_time_str = time.strftime('%Y%m%d%H%M%S', time.gmtime(resp_time))
        self.assertIn(test_timestamp, resp_time_str)

    def test_invalid_mfmt_timeval(self):
        # testing MFMT with invalid timeval argument
        test_timestamp_with_chars = "B017092101341A"
        test_timestamp_invalid_length = "20170921"

        try:
            self.client.sendcmd(
                'mfmt ' + test_timestamp_with_chars + ' ' + self.tempfile)
        except ftplib.error_perm as err:
            self.assertIn('Invalid time format', str(err))
        else:
            self.fail('Exception not raised')

        try:
            self.client.sendcmd(
                'mfmt ' + test_timestamp_invalid_length + ' ' + self.tempfile)
        except ftplib.error_perm as err:
            self.assertIn('Invalid time format', str(err))
        else:
            self.fail('Exception not raised')

    def test_missing_mfmt_timeval_arg(self):
        # testing missing timeval argument
        try:
            self.client.sendcmd('mfmt ' + self.tempfile)
        except ftplib.error_perm as err:
            self.assertIn('Syntax error', str(err))
        else:
            self.fail('Exception not raised')

    def test_size(self):
        self.client.sendcmd('type a')
        self.assertRaises(ftplib.error_perm, self.client.size, self.tempfile)
        self.client.sendcmd('type i')
        self.client.size(self.tempfile)
        # make sure we can't use size against directories
        try:
            self.client.sendcmd('size ' + self.tempdir)
        except ftplib.error_perm as err:
            self.assertIn("not retrievable", str(err))
        else:
            self.fail('Exception not raised')

    if not hasattr(os, 'chmod'):
        def test_site_chmod(self):
            self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                              'site chmod 777 ' + self.tempfile)
    else:
        def test_site_chmod(self):
            # not enough args
            self.assertRaises(ftplib.error_perm,
                              self.client.sendcmd, 'site chmod 777')
            # bad args
            self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                              'site chmod -177 ' + self.tempfile)
            self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                              'site chmod 778 ' + self.tempfile)
            self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                              'site chmod foo ' + self.tempfile)

            def getmode():
                mode = oct(stat.S_IMODE(os.stat(self.tempfile).st_mode))
                if PY3:
                    mode = mode.replace('o', '')
                return mode

            # on Windows it is possible to set read-only flag only
            if WINDOWS:
                self.client.sendcmd('site chmod 777 ' + self.tempfile)
                self.assertEqual(getmode(), '0666')
                self.client.sendcmd('site chmod 444 ' + self.tempfile)
                self.assertEqual(getmode(), '0444')
                self.client.sendcmd('site chmod 666 ' + self.tempfile)
                self.assertEqual(getmode(), '0666')
            else:
                self.client.sendcmd('site chmod 777 ' + self.tempfile)
                self.assertEqual(getmode(), '0777')
                self.client.sendcmd('site chmod 755 ' + self.tempfile)
                self.assertEqual(getmode(), '0755')
                self.client.sendcmd('site chmod 555 ' + self.tempfile)
                self.assertEqual(getmode(), '0555')


class CustomIO(io.RawIOBase):

    def __init__(self):
        super().__init__()
        self._bytesio = io.BytesIO()

    def seek(self, offset, whence=io.SEEK_SET):
        return self._bytesio.seek(offset, whence)

    def readinto(self, b):
        return self._bytesio.readinto(b)

    def write(self, b):
        return self._bytesio.write(b)


class TestFtpStoreData(PyftpdlibTestCase):
    """Test STOR, STOU, APPE, REST, TYPE."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP
    use_sendfile = None
    use_custom_io = False

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        if self.use_sendfile is not None:
            self.server.handler.use_sendfile = self.use_sendfile
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)
        if self.use_custom_io:
            self.dummy_recvfile = CustomIO()
            self.dummy_sendfile = CustomIO()
        else:
            self.dummy_recvfile = BytesIO()
            self.dummy_sendfile = BytesIO()
        self.testfn = self.get_testfn()

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        self.dummy_recvfile.close()
        self.dummy_sendfile.close()
        if self.use_sendfile is not None:
            self.server.handler.use_sendfile = _import_sendfile() is not None
        super().tearDown()

    def test_stor(self):
        data = b'abcde12345' * 100000
        self.dummy_sendfile.write(data)
        self.dummy_sendfile.seek(0)
        self.client.storbinary('stor ' + self.testfn, self.dummy_sendfile)
        self.client.retrbinary('retr ' + self.testfn,
                               self.dummy_recvfile.write)
        self.dummy_recvfile.seek(0)
        datafile = self.dummy_recvfile.read()
        self.assertEqual(len(data), len(datafile))
        self.assertEqual(hash(data), hash(datafile))

    def test_stor_active(self):
        # Like test_stor but using PORT
        self.client.set_pasv(False)
        self.test_stor()

    @retry_on_failure()
    def test_stor_ascii(self):
        # Test STOR in ASCII mode

        def store(cmd, fp, blocksize=8192):
            # like storbinary() except it sends "type a" instead of
            # "type i" before starting the transfer
            self.client.voidcmd('type a')
            with contextlib.closing(self.client.transfercmd(cmd)) as conn:
                while True:
                    buf = fp.read(blocksize)
                    if not buf:
                        break
                    conn.sendall(buf)
                if isinstance(conn, ssl.SSLSocket):
                    conn.unwrap()
            return self.client.voidresp()

        data = b'abcde12345\r\n' * 100000
        self.dummy_sendfile.write(data)
        self.dummy_sendfile.seek(0)
        store('stor ' + self.testfn, self.dummy_sendfile)
        self.client.retrbinary('retr ' + self.testfn,
                               self.dummy_recvfile.write)
        expected = data.replace(b'\r\n', b(os.linesep))
        self.dummy_recvfile.seek(0)
        datafile = self.dummy_recvfile.read()
        self.assertEqual(len(expected), len(datafile))
        self.assertEqual(hash(expected), hash(datafile))

    @retry_on_failure()
    def test_stor_ascii_2(self):
        # Test that no extra extra carriage returns are added to the
        # file in ASCII mode in case CRLF gets truncated in two chunks
        # (issue 116)

        def store(cmd, fp, blocksize=8192):
            # like storbinary() except it sends "type a" instead of
            # "type i" before starting the transfer
            self.client.voidcmd('type a')
            with contextlib.closing(self.client.transfercmd(cmd)) as conn:
                while True:
                    buf = fp.read(blocksize)
                    if not buf:
                        break
                    conn.sendall(buf)
            return self.client.voidresp()

        old_buffer = DTPHandler.ac_in_buffer_size
        try:
            # set a small buffer so that CRLF gets delivered in two
            # separate chunks: "CRLF", " f", "oo", " CR", "LF", " b", "ar"
            DTPHandler.ac_in_buffer_size = 2
            data = b'\r\n foo \r\n bar'
            self.dummy_sendfile.write(data)
            self.dummy_sendfile.seek(0)
            store('stor ' + self.testfn, self.dummy_sendfile)

            expected = data.replace(b'\r\n', b(os.linesep))
            self.client.retrbinary('retr ' + self.testfn,
                                   self.dummy_recvfile.write)
            self.client.quit()
            self.dummy_recvfile.seek(0)
            self.assertEqual(expected, self.dummy_recvfile.read())
        finally:
            DTPHandler.ac_in_buffer_size = old_buffer

    def test_stou(self):
        data = b'abcde12345' * 100000
        self.dummy_sendfile.write(data)
        self.dummy_sendfile.seek(0)

        self.client.voidcmd('TYPE I')
        # filename comes in as "1xx FILE: <filename>"
        filename = self.client.sendcmd('stou').split('FILE: ')[1]
        try:
            with contextlib.closing(self.client.makeport()) as sock:
                conn, _ = sock.accept()
                with contextlib.closing(conn):
                    conn.settimeout(GLOBAL_TIMEOUT)
                    if hasattr(self.client_class, 'ssl_version'):
                        conn = ssl.wrap_socket(conn)
                    while True:
                        buf = self.dummy_sendfile.read(8192)
                        if not buf:
                            break
                        conn.sendall(buf)
            # transfer finished, a 226 response is expected
            self.assertEqual('226', self.client.voidresp()[:3])
            self.client.retrbinary('retr ' + filename,
                                   self.dummy_recvfile.write)
            self.dummy_recvfile.seek(0)
            datafile = self.dummy_recvfile.read()
            self.assertEqual(len(data), len(datafile))
            self.assertEqual(hash(data), hash(datafile))
        finally:
            # We do not use os.remove() because file could still be
            # locked by ftpd thread.  If DELE through FTP fails try
            # os.remove() as last resort.
            if os.path.exists(filename):
                try:
                    self.client.delete(filename)
                except (ftplib.Error, EOFError, socket.error):
                    safe_rmpath(filename)

    def test_stou_rest(self):
        # Watch for STOU preceded by REST, which makes no sense.
        self.client.sendcmd('type i')
        self.client.sendcmd('rest 10')
        self.assertRaisesRegex(ftplib.error_temp, "Can't STOU while REST",
                               self.client.sendcmd, 'stou')

    def test_stou_orphaned_file(self):
        # Check that no orphaned file gets left behind when STOU fails.
        # Even if STOU fails the file is first created and then erased.
        # Since we can't know the name of the file the best way that
        # we have to test this case is comparing the content of the
        # directory before and after STOU has been issued.
        # Assuming that testfn is supposed to be a "reserved" file
        # name we shouldn't get false positives.
        # login as a limited user in order to make STOU fail
        self.client.login('anonymous', '@nopasswd')
        before = os.listdir(HOME)
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'stou ' + self.testfn)
        after = os.listdir(HOME)
        if before != after:
            for file in after:
                self.assertFalse(file.startswith(self.testfn))

    def test_appe(self):
        data1 = b'abcde12345' * 100000
        self.dummy_sendfile.write(data1)
        self.dummy_sendfile.seek(0)
        self.client.storbinary('stor ' + self.testfn, self.dummy_sendfile)

        data2 = b'fghil67890' * 100000
        self.dummy_sendfile.write(data2)
        self.dummy_sendfile.seek(len(data1))
        self.client.storbinary('appe ' + self.testfn, self.dummy_sendfile)

        self.client.retrbinary(
            "retr " + self.testfn, self.dummy_recvfile.write)
        self.dummy_recvfile.seek(0)
        datafile = self.dummy_recvfile.read()
        self.assertEqual(len(data1 + data2), len(datafile))
        self.assertEqual(hash(data1 + data2), hash(datafile))

    def test_appe_rest(self):
        # Watch for APPE preceded by REST, which makes no sense.
        self.client.sendcmd('type i')
        self.client.sendcmd('rest 10')
        self.assertRaisesRegex(ftplib.error_temp, "Can't APPE while REST",
                               self.client.sendcmd, 'appe x')

    def test_rest_on_stor(self):
        # Test STOR preceded by REST.
        data = b'abcde12345' * 100000
        self.dummy_sendfile.write(data)
        self.dummy_sendfile.seek(0)

        self.client.voidcmd('TYPE I')
        with contextlib.closing(
                self.client.transfercmd('stor ' + self.testfn)) as conn:
            bytes_sent = 0
            while True:
                chunk = self.dummy_sendfile.read(BUFSIZE)
                conn.sendall(chunk)
                bytes_sent += len(chunk)
                # stop transfer while it isn't finished yet
                if bytes_sent >= INTERRUPTED_TRANSF_SIZE or not chunk:
                    break
            if isinstance(conn, ssl.SSLSocket):
                conn.unwrap()

        # transfer wasn't finished yet but server can't know this,
        # hence expect a 226 response
        self.assertEqual('226', self.client.voidresp()[:3])
        # resuming transfer by using a marker value greater than the
        # file size stored on the server should result in an error
        # on stor
        file_size = self.client.size(self.testfn)
        self.assertEqual(file_size, bytes_sent)
        self.client.sendcmd('rest %s' % (file_size + 1))
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'stor ' + self.testfn)
        self.client.sendcmd('rest %s' % bytes_sent)
        self.client.storbinary('stor ' + self.testfn, self.dummy_sendfile)

        self.client.retrbinary('retr ' + self.testfn,
                               self.dummy_recvfile.write)
        self.dummy_sendfile.seek(0)
        self.dummy_recvfile.seek(0)

        data_sendfile = self.dummy_sendfile.read()
        data_recvfile = self.dummy_recvfile.read()
        self.assertEqual(len(data_sendfile), len(data_recvfile))
        self.assertEqual(len(data_sendfile), len(data_recvfile))

    def test_failing_rest_on_stor(self):
        # Test REST -> STOR against a non existing file.
        self.client.sendcmd('type i')
        self.client.sendcmd('rest 10')
        self.assertRaises(ftplib.error_perm, self.client.storbinary,
                          'stor ' + self.testfn, lambda x: x)
        # if the first STOR failed because of REST, the REST marker
        # is supposed to be resetted to 0
        self.dummy_sendfile.write(b'x' * 4096)
        self.dummy_sendfile.seek(0)
        self.client.storbinary('stor ' + self.testfn, self.dummy_sendfile)

    def test_quit_during_transfer(self):
        # RFC-959 states that if QUIT is sent while a transfer is in
        # progress, the connection must remain open for result response
        # and the server will then close it.
        with contextlib.closing(
                self.client.transfercmd('stor ' + self.testfn)) as conn:
            conn.sendall(b'abcde12345' * 50000)
            self.client.sendcmd('quit')
            conn.sendall(b'abcde12345' * 50000)
        # expect the response (transfer ok)
        self.assertEqual('226', self.client.voidresp()[:3])
        # Make sure client has been disconnected.
        # socket.error (Windows) or EOFError (Linux) exception is supposed
        # to be raised in such a case.
        self.client.sock.settimeout(.1)
        self.assertRaises((socket.error, EOFError),
                          self.client.sendcmd, 'noop')

    def test_stor_empty_file(self):
        self.client.storbinary('stor ' + self.testfn, self.dummy_sendfile)
        self.client.quit()
        with open(self.testfn) as f:
            self.assertEqual(f.read(), "")


@unittest.skipUnless(POSIX, "POSIX only")
@unittest.skipIf(not PY3 and sendfile is None,
                 "pysendfile not installed")
class TestFtpStoreDataNoSendfile(TestFtpStoreData):
    """Test STOR, STOU, APPE, REST, TYPE not using sendfile()."""
    use_sendfile = False


class TestFtpStoreDataWithCustomIO(TestFtpStoreData):
    """Test STOR, STOU, APPE, REST, TYPE with custom IO objects()."""
    use_custom_io = True


class TestFtpRetrieveData(PyftpdlibTestCase):
    """Test RETR, REST, TYPE."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP
    use_sendfile = None
    use_custom_io = False

    def retrieve_ascii(self, cmd, callback, blocksize=8192, rest=None):
        """Like retrbinary but uses TYPE A instead."""
        self.client.voidcmd('type a')
        with contextlib.closing(
                self.client.transfercmd(cmd, rest)) as conn:
            conn.settimeout(GLOBAL_TIMEOUT)
            while True:
                data = conn.recv(blocksize)
                if not data:
                    break
                callback(data)
        return self.client.voidresp()

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        if self.use_sendfile is not None:
            self.server.handler.use_sendfile = self.use_sendfile
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)
        self.testfn = self.get_testfn()
        if self.use_custom_io:
            self.dummyfile = CustomIO()
        else:
            self.dummyfile = BytesIO()

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        self.dummyfile.close()
        if self.use_sendfile is not None:
            self.server.handler.use_sendfile = _import_sendfile() is not None
        super().tearDown()

    def test_retr(self):
        data = b'abcde12345' * 100000
        with open(self.testfn, 'wb') as f:
            f.write(data)
        self.client.retrbinary("retr " + self.testfn, self.dummyfile.write)
        self.dummyfile.seek(0)
        datafile = self.dummyfile.read()
        self.assertEqual(len(data), len(datafile))
        self.assertEqual(hash(data), hash(datafile))

        # attempt to retrieve a file which doesn't exist
        bogus = self.get_testfn()
        self.assertRaises(ftplib.error_perm, self.client.retrbinary,
                          "retr " + bogus, lambda x: x)

    def test_retr_ascii(self):
        # Test RETR in ASCII mode.
        data = (b'abcde12345' + b(os.linesep)) * 100000
        with open(self.testfn, 'wb') as f:
            f.write(data)
        self.retrieve_ascii("retr " + self.testfn, self.dummyfile.write)
        expected = data.replace(b(os.linesep), b'\r\n')
        self.dummyfile.seek(0)
        datafile = self.dummyfile.read()
        self.assertEqual(len(expected), len(datafile))
        self.assertEqual(hash(expected), hash(datafile))

    def test_retr_ascii_already_crlf(self):
        # Test ASCII mode RETR for data with CRLF line endings.
        data = b'abcde12345\r\n' * 100000
        with open(self.testfn, 'wb') as f:
            f.write(data)
        self.retrieve_ascii("retr " + self.testfn, self.dummyfile.write)
        self.dummyfile.seek(0)
        datafile = self.dummyfile.read()
        self.assertEqual(len(data), len(datafile))
        self.assertEqual(hash(data), hash(datafile))

    @retry_on_failure()
    def test_restore_on_retr(self):
        data = b'abcde12345' * 1000000
        with open(self.testfn, 'wb') as f:
            f.write(data)

        received_bytes = 0
        self.client.voidcmd('TYPE I')
        with contextlib.closing(
                self.client.transfercmd('retr ' + self.testfn)) as conn:
            conn.settimeout(GLOBAL_TIMEOUT)
            while True:
                chunk = conn.recv(BUFSIZE)
                if not chunk:
                    break
                self.dummyfile.write(chunk)
                received_bytes += len(chunk)
                if received_bytes >= INTERRUPTED_TRANSF_SIZE:
                    break

        # transfer wasn't finished yet so we expect a 426 response
        self.assertEqual(self.client.getline()[:3], "426")

        # resuming transfer by using a marker value greater than the
        # file size stored on the server should result in an error
        # on retr (RFC-1123)
        file_size = self.client.size(self.testfn)
        self.client.sendcmd('rest %s' % (file_size + 1))
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'retr ' + self.testfn)
        # test resume
        self.client.sendcmd('rest %s' % received_bytes)
        self.client.retrbinary("retr " + self.testfn, self.dummyfile.write)
        self.dummyfile.seek(0)
        datafile = self.dummyfile.read()
        self.assertEqual(len(data), len(datafile))
        self.assertEqual(hash(data), hash(datafile))

    def test_retr_empty_file(self):
        touch(self.testfn)
        self.client.retrbinary("retr " + self.testfn, self.dummyfile.write)
        self.dummyfile.seek(0)
        self.assertEqual(self.dummyfile.read(), b"")


@unittest.skipUnless(POSIX, "POSIX only")
@unittest.skipIf(not PY3 and sendfile is None,
                 "pysendfile not installed")
class TestFtpRetrieveDataNoSendfile(TestFtpRetrieveData):
    """Test RETR, REST, TYPE by not using sendfile()."""
    use_sendfile = False


class TestFtpRetrieveDataCustomIO(TestFtpRetrieveData):
    """Test RETR, REST, TYPE using custom IO objects."""
    use_custom_io = True


class TestFtpListingCmds(PyftpdlibTestCase):
    """Test LIST, NLST, argumented STAT."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)
        self.testfn = self.get_testfn()
        touch(self.testfn)

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def _test_listing_cmds(self, cmd):
        """Tests common to LIST NLST and MLSD commands."""
        # assume that no argument has the same meaning of "/"
        l1 = l2 = []
        self.client.retrlines(cmd, l1.append)
        self.client.retrlines(cmd + ' /', l2.append)
        self.assertEqual(l1, l2)
        if cmd.lower() != 'mlsd':
            # if pathname is a file one line is expected
            x = []
            self.client.retrlines('%s ' % cmd + self.testfn, x.append)
            self.assertEqual(len(x), 1)
            self.assertTrue(''.join(x).endswith(self.testfn))
        # non-existent path, 550 response is expected
        bogus = self.get_testfn()
        self.assertRaises(ftplib.error_perm, self.client.retrlines,
                          '%s ' % cmd + bogus, lambda x: x)
        # for an empty directory we excpect that the data channel is
        # opened anyway and that no data is received
        x = []
        tempdir = self.get_testfn()
        os.mkdir(tempdir)
        try:
            self.client.retrlines('%s %s' % (cmd, tempdir), x.append)
            self.assertEqual(x, [])
        finally:
            safe_rmpath(tempdir)

    def test_nlst(self):
        # common tests
        self._test_listing_cmds('nlst')

    def test_list(self):
        # common tests
        self._test_listing_cmds('list')
        # known incorrect pathname arguments (e.g. old clients) are
        # expected to be treated as if pathname would be == '/'
        l1 = l2 = l3 = l4 = l5 = []
        self.client.retrlines('list /', l1.append)
        self.client.retrlines('list -a', l2.append)
        self.client.retrlines('list -l', l3.append)
        self.client.retrlines('list -al', l4.append)
        self.client.retrlines('list -la', l5.append)
        tot = (l1, l2, l3, l4, l5)
        for x in range(len(tot) - 1):
            self.assertEqual(tot[x], tot[x + 1])

    def test_mlst(self):
        # utility function for extracting the line of interest
        def mlstline(cmd):
            return self.client.voidcmd(cmd).split('\n')[1]

        # the fact set must be preceded by a space
        self.assertTrue(mlstline('mlst').startswith(' '))
        # where TVFS is supported, a fully qualified pathname is expected
        self.assertTrue(
            mlstline('mlst ' + self.testfn).endswith('/' + self.testfn))
        self.assertTrue(mlstline('mlst').endswith('/'))
        # assume that no argument has the same meaning of "/"
        self.assertEqual(mlstline('mlst'), mlstline('mlst /'))
        # non-existent path
        bogus = self.get_testfn()
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'mlst ' + bogus)
        # test file/dir notations
        self.assertIn('type=dir', mlstline('mlst'))
        self.assertIn('type=file', mlstline('mlst ' + self.testfn))
        # let's add some tests for OPTS command
        self.client.sendcmd('opts mlst type;')
        self.assertEqual(mlstline('mlst'), ' type=dir; /')
        # where no facts are present, two leading spaces before the
        # pathname are required (RFC-3659)
        self.client.sendcmd('opts mlst')
        self.assertEqual(mlstline('mlst'), '  /')

    def test_mlsd(self):
        # common tests
        self._test_listing_cmds('mlsd')
        dir = self.get_testfn()
        os.mkdir(dir)
        try:
            self.client.retrlines('mlsd ' + self.testfn, lambda x: x)
        except ftplib.error_perm as err:
            resp = str(err)
            # if path is a file a 501 response code is expected
            self.assertEqual(str(resp)[0:3], "501")
        else:
            self.fail("Exception not raised")

    def test_mlsd_all_facts(self):
        feat = self.client.sendcmd('feat')
        # all the facts
        facts = re.search(r'^\s*MLST\s+(\S+)$', feat, re.MULTILINE).group(1)
        facts = facts.replace("*;", ";")
        self.client.sendcmd('opts mlst ' + facts)
        resp = self.client.sendcmd('mlst')

        local = facts[:-1].split(";")
        returned = resp.split("\n")[1].strip()[:-3]
        returned = [x.split("=")[0] for x in returned.split(";")]
        self.assertEqual(sorted(local), sorted(returned))

        self.assertIn("type", resp)
        self.assertIn("size", resp)
        self.assertIn("perm", resp)
        self.assertIn("modify", resp)
        if POSIX:
            self.assertIn("unique", resp)
            self.assertIn("unix.mode", resp)
            self.assertIn("unix.uid", resp)
            self.assertIn("unix.gid", resp)
        elif WINDOWS:
            self.assertIn("create", resp)

    def test_stat(self):
        # Test STAT provided with argument which is equal to LIST
        self.client.sendcmd('stat /')
        self.client.sendcmd('stat ' + self.testfn)
        self.client.putcmd('stat *')
        resp = self.client.getmultiline()
        self.assertEqual(resp, '550 Globbing not supported.')
        bogus = self.get_testfn()
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'stat ' + bogus)

    def test_unforeseen_time_event(self):
        # Emulate a case where the file last modification time is prior
        # to year 1900.  This most likely will never happen unless
        # someone specifically force the last modification time of a
        # file in some way.
        # To do so we temporarily override os.path.getmtime so that it
        # returns a negative value referring to a year prior to 1900.
        # It causes time.localtime/gmtime to raise a ValueError exception
        # which is supposed to be handled by server.
        _getmtime = AbstractedFS.getmtime
        try:
            AbstractedFS.getmtime = lambda x, y: -9000000000
            self.client.sendcmd('stat /')  # test AbstractedFS.format_list()
            self.client.sendcmd('mlst /')  # test AbstractedFS.format_mlsx()
            # make sure client hasn't been disconnected
            self.client.sendcmd('noop')
        finally:
            AbstractedFS.getmtime = _getmtime


class TestFtpAbort(PyftpdlibTestCase):
    """Test: ABOR."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def test_abor_no_data(self):
        # Case 1: ABOR while no data channel is opened: respond with 225.
        resp = self.client.sendcmd('ABOR')
        self.assertEqual('225 No transfer to abort.', resp)
        self.client.retrlines('list', [].append)

    def test_abor_pasv(self):
        # Case 2: user sends a PASV, a data-channel socket is listening
        # but not connected, and ABOR is sent: close listening data
        # socket, respond with 225.
        self.client.makepasv()
        respcode = self.client.sendcmd('ABOR')[:3]
        self.assertEqual('225', respcode)
        self.client.retrlines('list', [].append)

    def test_abor_port(self):
        # Case 3: data channel opened with PASV or PORT, but ABOR sent
        # before a data transfer has been started: close data channel,
        # respond with 225
        self.client.set_pasv(0)
        with contextlib.closing(self.client.makeport()):
            respcode = self.client.sendcmd('ABOR')[:3]
        self.assertEqual('225', respcode)
        self.client.retrlines('list', [].append)

    def test_abor_during_transfer(self):
        # Case 4: ABOR while a data transfer on DTP channel is in
        # progress: close data channel, respond with 426, respond
        # with 226.
        data = b'abcde12345' * 1000000
        testfn = self.get_testfn()
        with open(testfn, 'w+b') as f:
            f.write(data)
        self.client.voidcmd('TYPE I')
        with contextlib.closing(
                self.client.transfercmd('retr ' + testfn)) as conn:
            bytes_recv = 0
            while bytes_recv < 65536:
                chunk = conn.recv(BUFSIZE)
                bytes_recv += len(chunk)

            # stop transfer while it isn't finished yet
            self.client.putcmd('ABOR')

            # transfer isn't finished yet so ftpd should respond with 426
            self.assertEqual(self.client.getline()[:3], "426")

            # transfer successfully aborted, so should now respond
            # with a 226
            self.assertEqual('226', self.client.voidresp()[:3])

    @unittest.skipUnless(hasattr(socket, 'MSG_OOB'), "MSG_OOB not available")
    @unittest.skipIf(OSX, "does not work on OSX")
    def test_oob_abor(self):
        # Send ABOR by following the RFC-959 directives of sending
        # Telnet IP/Synch sequence as OOB data.
        # On some systems like FreeBSD this happened to be a problem
        # due to a different SO_OOBINLINE behavior.
        # On some platforms (e.g. Python CE) the test may fail
        # although the MSG_OOB constant is defined.
        self.client.sock.sendall(b(chr(244)), socket.MSG_OOB)
        self.client.sock.sendall(b(chr(255)), socket.MSG_OOB)
        self.client.sock.sendall(b'abor\r\n')
        self.assertEqual(self.client.getresp()[:3], '225')


class TestThrottleBandwidth(PyftpdlibTestCase):
    """Test ThrottledDTPHandler class."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()

        class CustomDTPHandler(ThrottledDTPHandler):
            # overridden so that the "awake" callback is executed
            # immediately; this way we won't introduce any slowdown
            # and still test the code of interest

            def _throttle_bandwidth(self, *args, **kwargs):
                ThrottledDTPHandler._throttle_bandwidth(self, *args, **kwargs)
                if (self._throttler is not None and not
                        self._throttler.cancelled):
                    self._throttler.call()
                    self._throttler = None

        self.server = self.server_class()
        self.server.handler.dtp_handler = CustomDTPHandler
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)
        self.dummyfile = BytesIO()
        self.testfn = self.get_testfn()

    def tearDown(self):
        close_client(self.client)
        self.server.handler.dtp_handler.read_limit = 0
        self.server.handler.dtp_handler.write_limit = 0
        self.server.handler.dtp_handler = DTPHandler
        self.server.stop()
        if not self.dummyfile.closed:
            self.dummyfile.close()
        super().tearDown()

    def test_throttle_send(self):
        # This test doesn't test the actual speed accuracy, just
        # awakes all that code which implements the throttling.
        # with self.server.lock:
        self.server.handler.dtp_handler.write_limit = 32768
        data = b'abcde12345' * 100000
        with open(self.testfn, 'wb') as file:
            file.write(data)
        self.client.retrbinary("retr " + self.testfn, self.dummyfile.write)
        self.dummyfile.seek(0)
        datafile = self.dummyfile.read()
        self.assertEqual(len(data), len(datafile))
        self.assertEqual(hash(data), hash(datafile))

    def test_throttle_recv(self):
        # This test doesn't test the actual speed accuracy, just
        # awakes all that code which implements the throttling.
        # with self.server.lock:
        self.server.handler.dtp_handler.read_limit = 32768
        data = b'abcde12345' * 100000
        self.dummyfile.write(data)
        self.dummyfile.seek(0)
        self.client.storbinary("stor " + self.testfn, self.dummyfile)
        self.client.quit()  # needed to fix occasional failures
        with open(self.testfn, 'rb') as file:
            file_data = file.read()
        self.assertEqual(len(data), len(file_data))
        self.assertEqual(hash(data), hash(file_data))


class TestTimeouts(PyftpdlibTestCase):
    """Test idle-timeout capabilities of control and data channels.
    Some tests may fail on slow machines.
    """
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = None
        self.client = None
        self.testfn = self.get_testfn()

    def _setUp(self, idle_timeout=300, data_timeout=300, pasv_timeout=30,
               port_timeout=30):
        self.server = self.server_class()
        self.server.handler.timeout = idle_timeout
        self.server.handler.dtp_handler.timeout = data_timeout
        self.server.handler.passive_dtp.timeout = pasv_timeout
        self.server.handler.active_dtp.timeout = port_timeout
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)

    def tearDown(self):
        if self.client is not None and self.server is not None:
            close_client(self.client)
            self.server.handler.timeout = 300
            self.server.handler.dtp_handler.timeout = 300
            self.server.handler.passive_dtp.timeout = 30
            self.server.handler.active_dtp.timeout = 30
            self.server.stop()
        super().tearDown()

    # Note: moved later.

    # def test_idle_timeout(self):
    #     # Test control channel timeout.  The client which does not send
    #     # any command within the time specified in FTPHandler.timeout is
    #     # supposed to be kicked off.
    #     self._setUp(idle_timeout=0.1)
    #     # fail if no msg is received within 1 second
    #     self.client.sock.settimeout(1)
    #     data = self.client.sock.recv(BUFSIZE)
    #     self.assertEqual(data, b"421 Control connection timed out.\r\n")
    #     # ensure client has been kicked off
    #     self.assertRaises((socket.error, EOFError), self.client.sendcmd,
    #                       'noop')

    def test_data_timeout(self):
        # Test data channel timeout.  The client which does not send
        # or receive any data within the time specified in
        # DTPHandler.timeout is supposed to be kicked off.
        self._setUp(data_timeout=0.5 if CI_TESTING else 0.1)
        addr = self.client.makepasv()
        with contextlib.closing(socket.socket()) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.connect(addr)
            # fail if no msg is received within 1 second
            self.client.sock.settimeout(1)
            data = self.client.sock.recv(BUFSIZE)
            self.assertEqual(data, b"421 Data connection timed out.\r\n")
            # ensure client has been kicked off
            self.assertRaises((socket.error, EOFError), self.client.sendcmd,
                              'noop')

    def test_data_timeout_not_reached(self):
        # Impose a timeout for the data channel, then keep sending data for a
        # time which is longer than that to make sure that the code checking
        # whether the transfer stalled for with no progress is executed.
        self._setUp(data_timeout=0.5 if CI_TESTING else 0.1)
        with contextlib.closing(
                self.client.transfercmd('stor ' + self.testfn)) as sock:
            if hasattr(self.client_class, 'ssl_version'):
                sock = ssl.wrap_socket(sock)
            stop_at = time.time() + 0.2
            while time.time() < stop_at:
                sock.send(b'x' * 1024)
            sock.close()
            self.client.voidresp()

    def test_idle_data_timeout1(self):
        # Tests that the control connection timeout is suspended while
        # the data channel is opened
        self._setUp(idle_timeout=0.5 if CI_TESTING else 0.1,
                    data_timeout=0.6 if CI_TESTING else 0.2)
        addr = self.client.makepasv()
        with contextlib.closing(socket.socket()) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.connect(addr)
            # fail if no msg is received within 1 second
            self.client.sock.settimeout(1)
            data = self.client.sock.recv(BUFSIZE)
            self.assertEqual(data, b"421 Data connection timed out.\r\n")
            # ensure client has been kicked off
            self.assertRaises((socket.error, EOFError), self.client.sendcmd,
                              'noop')

    def test_idle_data_timeout2(self):
        # Tests that the control connection timeout is restarted after
        # data channel has been closed
        self._setUp(idle_timeout=0.5 if CI_TESTING else 0.1,
                    data_timeout=0.6 if CI_TESTING else 0.2)
        addr = self.client.makepasv()
        with contextlib.closing(socket.socket()) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.connect(addr)
            # close data channel
            self.client.sendcmd('abor')
            self.client.sock.settimeout(1)
            data = self.client.sock.recv(BUFSIZE)
            self.assertEqual(data, b"421 Control connection timed out.\r\n")
            # ensure client has been kicked off
            self.assertRaises((socket.error, EOFError), self.client.sendcmd,
                              'noop')

    def test_pasv_timeout(self):
        # Test pasv data channel timeout.  The client which does not
        # connect to the listening data socket within the time specified
        # in PassiveDTP.timeout is supposed to receive a 421 response.
        self._setUp(pasv_timeout=0.5 if CI_TESTING else 0.1)
        self.client.makepasv()
        # fail if no msg is received within 1 second
        self.client.sock.settimeout(1)
        data = self.client.sock.recv(BUFSIZE)
        self.assertEqual(data, b"421 Passive data channel timed out.\r\n")
        # client is not expected to be kicked off
        self.client.sendcmd('noop')

    def test_disabled_idle_timeout(self):
        self._setUp(idle_timeout=0)
        self.client.sendcmd('noop')

    def test_disabled_data_timeout(self):
        self._setUp(data_timeout=0)
        addr = self.client.makepasv()
        with contextlib.closing(socket.socket()) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.connect(addr)

    def test_disabled_pasv_timeout(self):
        self._setUp(pasv_timeout=0)
        self.client.makepasv()
        # reset passive socket
        addr = self.client.makepasv()
        with contextlib.closing(socket.socket()) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.connect(addr)

    def test_disabled_port_timeout(self):
        self._setUp(port_timeout=0)
        with contextlib.closing(self.client.makeport()):
            with contextlib.closing(self.client.makeport()):
                pass


class TestConfigurableOptions(PyftpdlibTestCase):
    """Test those daemon options which are commonly modified by user."""
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = None
        self.client = None

    def connect(self):
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)

    def tearDown(self):
        if self.client is not None:
            close_client(self.client)
        # set back options to their original value
        if self.server is not None:
            self.server.server.max_cons = 0
            self.server.server.max_cons_per_ip = 0
            self.server.handler.banner = "pyftpdlib ready."
            self.server.handler.max_login_attempts = 3
            self.server.handler.auth_failed_timeout = 5
            self.server.handler.masquerade_address = None
            self.server.handler.masquerade_address_map = {}
            self.server.handler.permit_privileged_ports = False
            self.server.handler.permit_foreign_addresses = False
            self.server.handler.passive_ports = None
            self.server.handler.use_gmt_times = True
            self.server.handler.tcp_no_delay = hasattr(socket, 'TCP_NODELAY')
            self.server.stop()
        super().tearDown()

    @disable_log_warning
    def test_max_connections(self):
        # Test FTPServer.max_cons attribute
        self.server = self.server_class()
        self.server.server.max_cons = 3
        self.server.start()

        c1 = self.client_class()
        c2 = self.client_class()
        c3 = self.client_class()
        try:
            c1.connect(self.server.host, self.server.port)
            c2.connect(self.server.host, self.server.port)
            self.assertRaises(ftplib.error_temp, c3.connect, self.server.host,
                              self.server.port)
            # with passive data channel established
            c2.quit()
            c1.login(USER, PASSWD)
            c1.makepasv()
            self.assertRaises(ftplib.error_temp, c2.connect, self.server.host,
                              self.server.port)
            # with passive data socket waiting for connection
            c1.login(USER, PASSWD)
            c1.sendcmd('pasv')
            self.assertRaises(ftplib.error_temp, c2.connect, self.server.host,
                              self.server.port)
            # with active data channel established
            c1.login(USER, PASSWD)
            with contextlib.closing(c1.makeport()):
                self.assertRaises(
                    ftplib.error_temp, c2.connect, self.server.host,
                    self.server.port)
        finally:
            for c in (c1, c2, c3):
                try:
                    c.quit()
                except (socket.error, EOFError):  # already disconnected
                    c.close()

    @disable_log_warning
    def test_max_connections_per_ip(self):
        # Test FTPServer.max_cons_per_ip attribute
        self.server = self.server_class()
        self.server.server.max_cons_per_ip = 3
        self.server.start()

        c1 = self.client_class()
        c2 = self.client_class()
        c3 = self.client_class()
        c4 = self.client_class()
        try:
            c1.connect(self.server.host, self.server.port)
            c2.connect(self.server.host, self.server.port)
            c3.connect(self.server.host, self.server.port)
            self.assertRaises(ftplib.error_temp, c4.connect, self.server.host,
                              self.server.port)
            # Make sure client has been disconnected.
            # socket.error (Windows) or EOFError (Linux) exception is
            # supposed to be raised in such a case.
            self.assertRaises((socket.error, EOFError), c4.sendcmd, 'noop')
        finally:
            for c in (c1, c2, c3, c4):
                try:
                    c.quit()
                except (socket.error, EOFError):  # already disconnected
                    c.close()

    def test_banner(self):
        # Test FTPHandler.banner attribute
        self.server = self.server_class()
        self.server.handler.banner = 'hello there'
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.assertEqual(self.client.getwelcome()[4:], 'hello there')

    def test_max_login_attempts(self):
        # Test FTPHandler.max_login_attempts attribute.
        self.server = self.server_class()
        self.server.handler.max_login_attempts = 1
        self.server.handler.auth_failed_timeout = 0
        self.server.start()
        self.connect()
        self.assertRaises(ftplib.error_perm, self.client.login, 'wrong',
                          'wrong')
        # socket.error (Windows) or EOFError (Linux) exceptions are
        # supposed to be raised when attempting to send/recv some data
        # using a disconnected socket
        self.assertRaises((socket.error, EOFError), self.client.sendcmd,
                          'noop')

    def test_masquerade_address(self):
        # Test FTPHandler.masquerade_address attribute
        self.server = self.server_class()
        self.server.handler.masquerade_address = "256.256.256.256"
        self.server.start()
        self.connect()
        host = ftplib.parse227(self.client.sendcmd('PASV'))[0]
        self.assertEqual(host, "256.256.256.256")

    def test_masquerade_address_map(self):
        # Test FTPHandler.masquerade_address_map attribute
        self.server = self.server_class()
        self.server.handler.masquerade_address_map = {self.server.host:
                                                      "128.128.128.128"}
        self.server.start()
        self.connect()
        host = ftplib.parse227(self.client.sendcmd('PASV'))[0]
        self.assertEqual(host, "128.128.128.128")

    def test_passive_ports(self):
        # Test FTPHandler.passive_ports attribute
        self.server = self.server_class()
        _range = list(range(40000, 60000, 200))
        self.server.handler.passive_ports = _range
        self.server.start()
        self.connect()
        self.assertIn(self.client.makepasv()[1], _range)
        self.assertIn(self.client.makepasv()[1], _range)
        self.assertIn(self.client.makepasv()[1], _range)
        self.assertIn(self.client.makepasv()[1], _range)

    @disable_log_warning
    def test_passive_ports_busy(self):
        # If the ports in the configured range are busy it is expected
        # that a kernel-assigned port gets chosen

        with contextlib.closing(socket.socket()) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.bind((HOST, 0))
            port = s.getsockname()[1]
            self.server = self.server_class()
            self.server.handler.passive_ports = [port]
            self.server.start()
            self.connect()
            resulting_port = self.client.makepasv()[1]
            self.assertNotEqual(port, resulting_port)

    @retry_on_failure()
    def test_use_gmt_times(self):
        testfn = self.get_testfn()
        touch(testfn)
        # use GMT time
        self.server = self.server_class()
        self.server.handler.use_gmt_times = True
        self.server.start()
        self.connect()
        gmt1 = self.client.sendcmd('mdtm ' + testfn)
        gmt2 = self.client.sendcmd('mlst ' + testfn)
        gmt3 = self.client.sendcmd('stat ' + testfn)

        # use local time
        self.tearDown()
        self.setUp()
        self.server = self.server_class()
        self.server.handler.use_gmt_times = False
        self.server.start()
        self.connect()
        loc1 = self.client.sendcmd('mdtm ' + testfn)
        loc2 = self.client.sendcmd('mlst ' + testfn)
        loc3 = self.client.sendcmd('stat ' + testfn)

        # if we're not in a GMT time zone times are supposed to be
        # different
        if time.timezone != 0:
            self.assertNotEqual(gmt1, loc1)
            self.assertNotEqual(gmt2, loc2)
            self.assertNotEqual(gmt3, loc3)
        # ...otherwise they should be the same
        else:
            self.assertEqual(gmt1, loc1)
            self.assertEqual(gmt2, loc2)
            self.assertEqual(gmt3, loc3)


class TestCallbacks(PyftpdlibTestCase):
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()

        class Handler(FTPHandler):

            def write(self, text):
                with open(testfn, "at") as f:
                    f.write(text)

            def on_connect(self):
                self.write("on_connect,")

            def on_disconnect(self):
                self.write("on_disconnect,")

            def on_login(self, username):
                self.write("on_login:%s," % username)

            def on_login_failed(self, username, password):
                self.write("on_login_failed:%s+%s," % (username, password))

            def on_logout(self, username):
                self.write("on_logout:%s," % username)

            def on_file_sent(self, file):
                self.write("on_file_sent:%s," % os.path.basename(file))

            def on_file_received(self, file):
                self.write("on_file_received:%s," % os.path.basename(file))

            def on_incomplete_file_sent(self, file):
                self.write(
                    "on_incomplete_file_sent:%s," % os.path.basename(file))

            def on_incomplete_file_received(self, file):
                self.write(
                    "on_incomplete_file_received:%s," % os.path.basename(file))

        self.testfn = testfn = self.get_testfn()
        self.testfn2 = self.get_testfn()
        self.server = self.server_class()
        self.server.server.handler = Handler
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def read_file(self, text):
        stop_at = time.time() + 1
        while time.time() <= stop_at:
            with open(self.testfn) as f:
                data = f.read()
                if data == text:
                    return
            time.sleep(0.01)
        self.fail("data: %r; expected: %r" % (data, text))

    def test_on_disconnect(self):
        self.client.login(USER, PASSWD)
        self.client.close()
        self.read_file('on_connect,on_login:%s,on_disconnect,' % USER)

    def test_on_logout_quit(self):
        self.client.login(USER, PASSWD)
        self.client.sendcmd('quit')
        self.read_file(
            'on_connect,on_login:%s,on_logout:%s,on_disconnect,' % (
                USER, USER))

    def test_on_logout_rein(self):
        self.client.login(USER, PASSWD)
        self.client.sendcmd('rein')
        self.read_file(
            'on_connect,on_login:%s,on_logout:%s,' % (USER, USER))

    def test_on_logout_no_pass(self):
        # make sure on_logout() is not called if USER was provided
        # but not PASS
        self.client.sendcmd("user foo")
        self.read_file('on_connect,')

    def test_on_logout_user_issued_twice(self):
        # At this point user "user" is logged in. Re-login as anonymous,
        # then quit and expect queue == ["user", "anonymous"]
        self.client.login(USER, PASSWD)
        self.client.login("anonymous")
        self.read_file(
            'on_connect,on_login:%s,on_logout:%s,on_login:anonymous,' %
            (USER, USER))

    def test_on_login_failed(self):
        self.assertRaises(
            ftplib.error_perm, self.client.login, 'foo', 'bar?!?')
        self.read_file('on_connect,on_login_failed:foo+bar?!?,')

    def test_on_file_received(self):
        data = b'abcde12345' * 100000
        dummyfile = BytesIO()
        dummyfile.write(data)
        dummyfile.seek(0)
        self.client.login(USER, PASSWD)
        self.client.storbinary('stor ' + self.testfn2, dummyfile)
        self.read_file(
            'on_connect,on_login:%s,on_file_received:%s,' % (
                USER, self.testfn2))

    def test_on_file_sent(self):
        self.client.login(USER, PASSWD)
        data = b'abcde12345' * 100000
        with open(self.testfn2, 'wb') as f:
            f.write(data)
        self.client.retrbinary("retr " + self.testfn2, lambda x: x)
        self.read_file(
            'on_connect,on_login:%s,on_file_sent:%s,' % (USER, self.testfn2))

    @retry_on_failure()
    def test_on_incomplete_file_received(self):
        self.client.login(USER, PASSWD)
        data = b'abcde12345' * 1000000
        dummyfile = BytesIO()
        dummyfile.write(data)
        dummyfile.seek(0)
        with contextlib.closing(
                self.client.transfercmd('stor ' + self.testfn2)) as conn:
            bytes_sent = 0
            while True:
                chunk = dummyfile.read(BUFSIZE)
                conn.sendall(chunk)
                bytes_sent += len(chunk)
                # stop transfer while it isn't finished yet
                if bytes_sent >= INTERRUPTED_TRANSF_SIZE or not chunk:
                    self.client.putcmd('abor')
                    break
        # If a data transfer is in progress server is supposed to send
        # a 426 reply followed by a 226 reply.
        self.assertRaises(ftplib.error_temp, self.client.getresp)  # 426
        self.assertEqual(self.client.getresp()[:3], "226")
        self.read_file(
            'on_connect,on_login:%s,on_incomplete_file_received:%s,' %
            (USER, self.testfn2))

    @retry_on_failure()
    def test_on_incomplete_file_sent(self):
        self.client.login(USER, PASSWD)
        data = b'abcde12345' * 1000000
        with open(self.testfn2, 'wb') as f:
            f.write(data)
        bytes_recv = 0
        with contextlib.closing(self.client.transfercmd(
                                "retr " + self.testfn2, None)) as conn:
            while True:
                chunk = conn.recv(BUFSIZE)
                bytes_recv += len(chunk)
                if bytes_recv >= INTERRUPTED_TRANSF_SIZE or not chunk:
                    break
        self.assertEqual(self.client.getline()[:3], "426")
        self.read_file(
            'on_connect,on_login:%s,on_incomplete_file_sent:%s,' %
            (USER, self.testfn2))


class _TestNetworkProtocols(object):  # noqa
    """Test PASV, EPSV, PORT and EPRT commands.

    Do not use this class directly, let TestIPv4Environment and
    TestIPv6Environment classes use it instead.
    """

    def setUp(self):
        super().setUp()
        self.server = self.server_class((self.HOST, 0))
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)
        if self.client.af == socket.AF_INET:
            self.proto = "1"
            self.other_proto = "2"
        else:
            self.proto = "2"
            self.other_proto = "1"

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def cmdresp(self, cmd):
        """Send a command and return response, also if the command failed."""
        try:
            return self.client.sendcmd(cmd)
        except ftplib.Error as err:
            return str(err)

    @disable_log_warning
    def test_eprt(self):
        if not SUPPORTS_HYBRID_IPV6:
            # test wrong proto
            try:
                self.client.sendcmd('eprt |%s|%s|%s|' % (
                    self.other_proto, self.server.host, self.server.port))
            except ftplib.error_perm as err:
                self.assertEqual(str(err)[0:3], "522")
            else:
                self.fail("Exception not raised")

        # test bad args
        msg = "501 Invalid EPRT format."
        # len('|') > 3
        self.assertEqual(self.cmdresp('eprt ||||'), msg)
        # len('|') < 3
        self.assertEqual(self.cmdresp('eprt ||'), msg)
        # port > 65535
        self.assertEqual(self.cmdresp('eprt |%s|%s|65536|' % (self.proto,
                                                              self.HOST)), msg)
        # port < 0
        self.assertEqual(self.cmdresp('eprt |%s|%s|-1|' % (self.proto,
                                                           self.HOST)), msg)
        # port < 1024
        resp = self.cmdresp('eprt |%s|%s|222|' % (self.proto, self.HOST))
        self.assertEqual(resp[:3], '501')
        self.assertIn('privileged port', resp)
        # proto > 2
        _cmd = 'eprt |3|%s|%s|' % (self.server.host, self.server.port)
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, _cmd)

        if self.proto == '1':
            # len(ip.octs) > 4
            self.assertEqual(self.cmdresp('eprt |1|1.2.3.4.5|2048|'), msg)
            # ip.oct > 255
            self.assertEqual(self.cmdresp('eprt |1|1.2.3.256|2048|'), msg)
            # bad proto
            resp = self.cmdresp('eprt |2|1.2.3.256|2048|')
            self.assertIn("Network protocol not supported", resp)

        # test connection
        with contextlib.closing(socket.socket(self.client.af)) as sock:
            sock.bind((self.client.sock.getsockname()[0], 0))
            sock.listen(5)
            sock.settimeout(GLOBAL_TIMEOUT)
            ip, port = sock.getsockname()[:2]
            self.client.sendcmd('eprt |%s|%s|%s|' % (self.proto, ip, port))
            try:
                s = sock.accept()
                s[0].close()
            except socket.timeout:
                self.fail("Server didn't connect to passive socket")

    def test_epsv(self):
        # test wrong proto
        try:
            self.client.sendcmd('epsv ' + self.other_proto)
        except ftplib.error_perm as err:
            self.assertEqual(str(err)[0:3], "522")
        else:
            self.fail("Exception not raised")

        # proto > 2
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'epsv 3')

        # test connection
        for cmd in ('EPSV', 'EPSV ' + self.proto):
            host, port = ftplib.parse229(self.client.sendcmd(cmd),
                                         self.client.sock.getpeername())
            with contextlib.closing(
                    socket.socket(self.client.af, socket.SOCK_STREAM)) as s:
                s.settimeout(GLOBAL_TIMEOUT)
                s.connect((host, port))
                self.client.sendcmd('abor')

    def test_epsv_all(self):
        self.client.sendcmd('epsv all')
        self.assertRaises(ftplib.error_perm, self.client.sendcmd, 'pasv')
        self.assertRaises(ftplib.error_perm, self.client.sendport, self.HOST,
                          2000)
        self.assertRaises(ftplib.error_perm, self.client.sendcmd,
                          'eprt |%s|%s|%s|' % (self.proto, self.HOST, 2000))


@unittest.skipUnless(SUPPORTS_IPV4, "IPv4 not supported")
class TestIPv4Environment(_TestNetworkProtocols, PyftpdlibTestCase):
    """Test PASV, EPSV, PORT and EPRT commands.

    Runs tests contained in _TestNetworkProtocols class by using IPv4
    plus some additional specific tests.
    """
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP
    HOST = '127.0.0.1'

    @disable_log_warning
    def test_port_v4(self):
        # test connection
        with contextlib.closing(self.client.makeport()):
            self.client.sendcmd('abor')
        # test bad arguments
        ae = self.assertEqual
        msg = "501 Invalid PORT format."
        ae(self.cmdresp('port 127,0,0,1,1.1'), msg)    # sep != ','
        ae(self.cmdresp('port X,0,0,1,1,1'), msg)      # value != int
        ae(self.cmdresp('port 127,0,0,1,1,1,1'), msg)  # len(args) > 6
        ae(self.cmdresp('port 127,0,0,1'), msg)        # len(args) < 6
        ae(self.cmdresp('port 256,0,0,1,1,1'), msg)    # oct > 255
        ae(self.cmdresp('port 127,0,0,1,256,1'), msg)  # port > 65535
        ae(self.cmdresp('port 127,0,0,1,-1,0'), msg)   # port < 0
        # port < 1024
        resp = self.cmdresp('port %s,1,1' % self.HOST.replace('.', ','))
        self.assertEqual(resp[:3], '501')
        self.assertIn('privileged port', resp)
        if "1.2.3.4" != self.HOST:
            resp = self.cmdresp('port 1,2,3,4,4,4')
            assert 'foreign address' in resp, resp

    @disable_log_warning
    def test_eprt_v4(self):
        resp = self.cmdresp('eprt |1|0.10.10.10|2222|')
        self.assertEqual(resp[:3], '501')
        self.assertIn('foreign address', resp)

    def test_pasv_v4(self):
        host, port = ftplib.parse227(self.client.sendcmd('pasv'))
        with contextlib.closing(
                socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.connect((host, port))


@unittest.skipUnless(SUPPORTS_IPV6, "IPv6 not supported")
class TestIPv6Environment(_TestNetworkProtocols, PyftpdlibTestCase):
    """Test PASV, EPSV, PORT and EPRT commands.

    Runs tests contained in _TestNetworkProtocols class by using IPv6
    plus some additional specific tests.
    """
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP
    HOST = '::1'

    def test_port_v6(self):
        # PORT is not supposed to work
        self.assertRaises(ftplib.error_perm, self.client.sendport,
                          self.server.host, self.server.port)

    def test_pasv_v6(self):
        # PASV is still supposed to work to support clients using
        # IPv4 connecting to a server supporting both IPv4 and IPv6
        self.client.makepasv()

    @disable_log_warning
    def test_eprt_v6(self):
        resp = self.cmdresp('eprt |2|::foo|2222|')
        self.assertEqual(resp[:3], '501')
        self.assertIn('foreign address', resp)


@unittest.skipUnless(SUPPORTS_HYBRID_IPV6, "IPv4/6 dual stack not supported")
class TestIPv6MixedEnvironment(PyftpdlibTestCase):
    """By running the server by specifying "::" as IP address the
    server is supposed to listen on all interfaces, supporting both
    IPv4 and IPv6 by using a single socket.

    What we are going to do here is starting the server in this
    manner and try to connect by using an IPv4 client.
    """
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP
    HOST = "::"

    def setUp(self):
        super().setUp()
        self.server = self.server_class((self.HOST, 0))
        self.server.start()
        self.client = None

    def tearDown(self):
        if self.client is not None:
            close_client(self.client)
        self.server.stop()
        super().tearDown()

    def test_port_v4(self):
        def noop(x):
            return x

        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect('127.0.0.1', self.server.port)
        self.client.set_pasv(False)
        self.client.login(USER, PASSWD)
        self.client.retrlines('list', noop)

    def test_pasv_v4(self):
        def noop(x):
            return x

        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect('127.0.0.1', self.server.port)
        self.client.set_pasv(True)
        self.client.login(USER, PASSWD)
        self.client.retrlines('list', noop)
        # make sure pasv response doesn't return an IPv4-mapped address
        ip = self.client.makepasv()[0]
        self.assertFalse(ip.startswith("::ffff:"))

    def test_eprt_v4(self):
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect('127.0.0.1', self.server.port)
        self.client.login(USER, PASSWD)
        # test connection
        with contextlib.closing(
                socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.bind((self.client.sock.getsockname()[0], 0))
            sock.listen(5)
            sock.settimeout(2)
            ip, port = sock.getsockname()[:2]
            self.client.sendcmd('eprt |1|%s|%s|' % (ip, port))
            try:
                sock2, _ = sock.accept()
                sock2.close()
            except socket.timeout:
                self.fail("Server didn't connect to passive socket")

    def test_epsv_v4(self):
        def mlstline(cmd):
            return self.client.voidcmd(cmd).split('\n')[1]

        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect('127.0.0.1', self.server.port)
        self.client.login(USER, PASSWD)
        host, port = ftplib.parse229(self.client.sendcmd('EPSV'),
                                     self.client.sock.getpeername())
        self.assertEqual('127.0.0.1', host)
        with contextlib.closing(
                socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(GLOBAL_TIMEOUT)
            s.connect((host, port))
            self.assertTrue(mlstline('mlst /').endswith('/'))


class TestCornerCases(PyftpdlibTestCase):
    """Tests for any kind of strange situation for the server to be in,
    mainly referring to bugs signaled on the bug tracker.
    """
    server_class = MProcessTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        super().tearDown()

    def test_port_race_condition(self):
        # Refers to bug #120, first sends PORT, then disconnects the
        # control channel before accept()ing the incoming data connection.
        # The original server behavior was to reply with "200 Active
        # data connection established" *after* the client had already
        # disconnected the control connection.
        with contextlib.closing(socket.socket(self.client.af)) as sock:
            sock.bind((self.client.sock.getsockname()[0], 0))
            sock.listen(5)
            sock.settimeout(GLOBAL_TIMEOUT)
            host, port = sock.getsockname()[:2]

            hbytes = host.split('.')
            pbytes = [repr(port // 256), repr(port % 256)]
            bytes = hbytes + pbytes
            cmd = 'PORT ' + ','.join(bytes) + '\r\n'
            self.client.sock.sendall(b(cmd))
            self.client.getresp()
            s, _ = sock.accept()
            s.close()

    @unittest.skipUnless(POSIX, "POSIX only")
    def test_quick_connect(self):
        # Clients that connected and disconnected quickly could cause
        # the server to crash, due to a failure to catch errors in the
        # initial part of the connection process.
        # Tracked in issues #91, #104 and #105.
        # See also https://bugs.launchpad.net/zodb/+bug/135108
        import struct

        def connect(addr):
            with contextlib.closing(socket.socket()) as s:
                # Set SO_LINGER to 1,0 causes a connection reset (RST) to
                # be sent when close() is called, instead of the standard
                # FIN shutdown sequence.
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                             struct.pack('ii', 1, 0))
                s.settimeout(GLOBAL_TIMEOUT)
                try:
                    s.connect(addr)
                except socket.error:
                    pass

        for _ in range(10):
            connect((self.server.host, self.server.port))
        for _ in range(10):
            addr = self.client.makepasv()
            connect(addr)

    def test_error_on_callback(self):
        # test that the server do not crash in case an error occurs
        # while firing a scheduled function
        self.tearDown()
        server = FTPServer((HOST, 0), FTPHandler)
        logger = logging.getLogger('pyftpdlib')
        logger.disabled = True
        try:
            len1 = len(IOLoop.instance().socket_map)
            IOLoop.instance().call_later(0, lambda: 1 // 0)
            server.serve_forever(timeout=0.001, blocking=False)
            len2 = len(IOLoop.instance().socket_map)
            self.assertEqual(len1, len2)
        finally:
            logger.disabled = False
            server.close()

    def test_active_conn_error(self):
        # we open a socket() but avoid to invoke accept() to
        # reproduce this error condition:
        # http://code.google.com/p/pyftpdlib/source/detail?r=905
        with contextlib.closing(socket.socket()) as sock:
            sock.bind((HOST, 0))
            port = sock.getsockname()[1]
            self.client.sock.settimeout(.1)
            try:
                resp = self.client.sendport(HOST, port)
            except ftplib.error_temp as err:
                self.assertEqual(str(err)[:3], '425')
            except (socket.timeout, getattr(ssl, "SSLError", object())):
                pass
            else:
                self.assertNotEqual(str(resp)[:3], '200')

    def test_repr(self):
        # make sure the FTP/DTP handler classes have a sane repr()
        with contextlib.closing(self.client.makeport()):
            for inst in IOLoop.instance().socket_map.values():
                repr(inst)
                str(inst)

    if hasattr(os, 'sendfile'):
        def test_sendfile(self):
            # make sure that on python >= 3.3 we're using os.sendfile
            # rather than third party pysendfile module
            self.assertIs(sendfile, os.sendfile)

    if SUPPORTS_SENDFILE:
        def test_sendfile_enabled(self):
            self.assertEqual(FTPHandler.use_sendfile, True)

    if hasattr(select, 'epoll') or hasattr(select, 'kqueue'):
        def test_ioloop_fileno(self):
            fd = self.server.server.ioloop.fileno()
            self.assertIsInstance(fd, int, fd)


# # TODO: disabled as on certain platforms (OSX and Windows)
# # produces failures with python3. Will have to get back to
# # this and fix it.
# @unittest.skipIf(OSX or WINDOWS, "fails on OSX or Windows")
# class TestUnicodePathNames(PyftpdlibTestCase):
#     """Test FTP commands and responses by using path names with non
#     ASCII characters.
#     """
#     server_class = MProcessTestFTPd
#     client_class = ftplib.FTP

#     def setUp(self):
#         super().setUp()
#         self.server = self.server_class()
#         self.server.start()
#         self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
#         self.client.encoding = 'utf8'  # PY3 only
#         self.client.connect(self.server.host, self.server.port)
#         self.client.login(USER, PASSWD)
#         if PY3:
#             safe_mkdir(bytes(TESTFN_UNICODE, 'utf8'))
#             touch(bytes(TESTFN_UNICODE_2, 'utf8'))
#             self.utf8fs = TESTFN_UNICODE in os.listdir('.')
#         else:
#             warnings.filterwarnings("ignore")
#             safe_mkdir(TESTFN_UNICODE)
#             touch(TESTFN_UNICODE_2)
#             self.utf8fs = \
#                 unicode(TESTFN_UNICODE, 'utf8') in os.listdir(u('.'))
#             warnings.resetwarnings()

#     def tearDown(self):
#         close_client(self.client)
#         self.server.stop()
#         super().tearDown()

#     # --- fs operations

#     def test_cwd(self):
#         if self.utf8fs:
#             resp = self.client.cwd(TESTFN_UNICODE)
#             self.assertTrue(TESTFN_UNICODE in resp)
#         else:
#             self.assertRaises(ftplib.error_perm, self.client.cwd,
#                               TESTFN_UNICODE)

#     def test_mkd(self):
#         if self.utf8fs:
#             os.rmdir(TESTFN_UNICODE)
#             dirname = self.client.mkd(TESTFN_UNICODE)
#             self.assertEqual(dirname, '/' + TESTFN_UNICODE)
#             self.assertTrue(os.path.isdir(TESTFN_UNICODE))
#         else:
#             self.assertRaises(ftplib.error_perm, self.client.mkd,
#                               TESTFN_UNICODE)

#     def test_rmdir(self):
#         if self.utf8fs:
#             self.client.rmd(TESTFN_UNICODE)
#         else:
#             self.assertRaises(ftplib.error_perm, self.client.rmd,
#                               TESTFN_UNICODE)

#     def test_rnfr_rnto(self):
#         if self.utf8fs:
#             self.client.rename(TESTFN_UNICODE, TESTFN)
#         else:
#             self.assertRaises(ftplib.error_perm, self.client.rename,
#                               TESTFN_UNICODE, TESTFN)

#     def test_size(self):
#         self.client.sendcmd('type i')
#         if self.utf8fs:
#             self.client.sendcmd('size ' + TESTFN_UNICODE_2)
#         else:
#             self.assertRaises(ftplib.error_perm, self.client.sendcmd,
#                               'size ' + TESTFN_UNICODE_2)

#     def test_mdtm(self):
#         if self.utf8fs:
#             self.client.sendcmd('mdtm ' + TESTFN_UNICODE_2)
#         else:
#             self.assertRaises(ftplib.error_perm, self.client.sendcmd,
#                               'mdtm ' + TESTFN_UNICODE_2)

#     def test_stou(self):
#         if self.utf8fs:
#             resp = self.client.sendcmd('stou ' + TESTFN_UNICODE)
#             self.assertTrue(TESTFN_UNICODE in resp)
#         else:
#             self.assertRaises(ftplib.error_perm, self.client.sendcmd,
#                               'stou ' + TESTFN_UNICODE)

#     if hasattr(os, 'chmod'):
#         def test_site_chmod(self):
#             if self.utf8fs:
#                 self.client.sendcmd('site chmod 777 ' + TESTFN_UNICODE)
#             else:
#                 self.assertRaises(ftplib.error_perm, self.client.sendcmd,
#                                   'site chmod 777 ' + TESTFN_UNICODE)

#     # --- listing cmds

#     def _test_listing_cmds(self, cmd):
#         ls = []
#         self.client.retrlines(cmd, ls.append)
#         ls = '\n'.join(ls)
#         if self.utf8fs:
#             self.assertTrue(TESTFN_UNICODE in ls)
#         else:
#             # Part of the filename which are not encodable are supposed
#             # to have been replaced. The file should be something like
#             # 'tmp-pyftpdlib-unicode-????'. In any case it is not
#             # referenceable (e.g. DELE 'tmp-pyftpdlib-unicode-????'
#             # won't work).
#             self.assertTrue('tmp-pyftpdlib-unicode' in ls)

#     def test_list(self):
#         self._test_listing_cmds('list')

#     def test_nlst(self):
#         self._test_listing_cmds('nlst')

#     def test_mlsd(self):
#         self._test_listing_cmds('mlsd')

#     def test_mlst(self):
#         # utility function for extracting the line of interest
#         def mlstline(cmd):
#             return self.client.voidcmd(cmd).split('\n')[1]

#         if self.utf8fs:
#             self.assertTrue('type=dir' in
#                             mlstline('mlst ' + TESTFN_UNICODE))
#             self.assertTrue('/' + TESTFN_UNICODE in
#                             mlstline('mlst ' + TESTFN_UNICODE))
#             self.assertTrue('type=file' in
#                             mlstline('mlst ' + TESTFN_UNICODE_2))
#             self.assertTrue('/' + TESTFN_UNICODE_2 in
#                             mlstline('mlst ' + TESTFN_UNICODE_2))
#         else:
#             self.assertRaises(ftplib.error_perm,
#                               mlstline, 'mlst ' + TESTFN_UNICODE)

#     # --- file transfer

#     def test_stor(self):
#         if self.utf8fs:
#             data = b'abcde12345' * 500
#             os.remove(TESTFN_UNICODE_2)
#             dummy = BytesIO()
#             dummy.write(data)
#             dummy.seek(0)
#             self.client.storbinary('stor ' + TESTFN_UNICODE_2, dummy)
#             dummy_recv = BytesIO()
#             self.client.retrbinary('retr ' + TESTFN_UNICODE_2,
#                                    dummy_recv.write)
#             dummy_recv.seek(0)
#             self.assertEqual(dummy_recv.read(), data)
#         else:
#             dummy = BytesIO()
#             self.assertRaises(ftplib.error_perm, self.client.storbinary,
#                               'stor ' + TESTFN_UNICODE_2, dummy)

#     def test_retr(self):
#         if self.utf8fs:
#             data = b'abcd1234' * 500
#             with open(TESTFN_UNICODE_2, 'wb') as f:
#                 f.write(data)
#             dummy = BytesIO()
#             self.client.retrbinary('retr ' + TESTFN_UNICODE_2, dummy.write)
#             dummy.seek(0)
#             self.assertEqual(dummy.read(), data)
#         else:
#             dummy = BytesIO()
#             self.assertRaises(ftplib.error_perm, self.client.retrbinary,
#                               'retr ' + TESTFN_UNICODE_2, dummy.write)


class ThreadedFTPTests(PyftpdlibTestCase):

    server_class = ThreadedTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = self.server_class()
        self.server.start()
        self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
        self.client.connect(self.server.host, self.server.port)
        self.client.login(USER, PASSWD)
        self.tempfile = self.get_testfn()
        self.tempdir = self.get_testfn()
        touch(self.tempfile)
        touch(self.tempdir)
        self.dummy_recvfile = BytesIO()
        self.dummy_sendfile = BytesIO()

    def tearDown(self):
        close_client(self.client)
        self.server.stop()
        self.dummy_recvfile.close()
        self.dummy_sendfile.close()
        super().tearDown()

    @retry_on_failure()
    def test_unforeseen_mdtm_event(self):
        # Emulate a case where the file last modification time is prior
        # to year 1900.  This most likely will never happen unless
        # someone specifically force the last modification time of a
        # file in some way.
        # To do so we temporarily override os.path.getmtime so that it
        # returns a negative value referring to a year prior to 1900.
        # It causes time.localtime/gmtime to raise a ValueError exception
        # which is supposed to be handled by server.

        # On python 3 it seems that the trick of replacing the original
        # method with the lambda doesn't work.
        if not PY3:
            _getmtime = AbstractedFS.getmtime
            try:
                AbstractedFS.getmtime = lambda x, y: -9000000000
                self.assertRaisesRegex(
                    ftplib.error_perm,
                    "550 Can't determine file's last modification time",
                    self.client.sendcmd, 'mdtm ' + self.tempfile)
                # make sure client hasn't been disconnected
                self.client.sendcmd('noop')
            finally:
                AbstractedFS.getmtime = _getmtime

    @retry_on_failure()
    def test_stou_max_tries(self):
        # Emulates case where the max number of tries to find out a
        # unique file name when processing STOU command gets hit.

        class TestFS(AbstractedFS):

            def mkstemp(self, *args, **kwargs):
                raise IOError(errno.EEXIST,
                              "No usable temporary file name found")

        with self.server.lock:
            self.server.handler.abstracted_fs = TestFS
        try:
            self.client.quit()
            self.client.connect(self.server.host, self.server.port)
            self.client.login(USER, PASSWD)
            self.assertRaises(ftplib.error_temp, self.client.sendcmd, 'stou')
        finally:
            with self.server.lock:
                self.server.handler.abstracted_fs = AbstractedFS

    @retry_on_failure()
    def test_idle_timeout(self):
        # Test control channel timeout.  The client which does not send
        # any command within the time specified in FTPHandler.timeout is
        # supposed to be kicked off.
        with self.server.lock:
            self.server.handler.timeout = 0.1

        try:
            self.client.quit()
            self.client.connect()
            self.client.login(USER, PASSWD)
            # fail if no msg is received within 1 second
            self.client.sock.settimeout(1)
            data = self.client.sock.recv(BUFSIZE)
            self.assertEqual(data, b"421 Control connection timed out.\r\n")
            # ensure client has been kicked off
            self.assertRaises((socket.error, EOFError), self.client.sendcmd,
                              'noop')
        finally:
            with self.server.lock:
                self.server.handler.timeout = 0.1

    @unittest.skipUnless(hasattr(socket, 'TCP_NODELAY'),
                         'TCP_NODELAY not available')
    @retry_on_failure()
    def test_tcp_no_delay(self):
        s = get_server_handler().socket
        self.assertTrue(s.getsockopt(socket.SOL_TCP, socket.TCP_NODELAY))
        self.client.quit()
        with self.server.lock:
            self.server.handler.tcp_no_delay = False
        self.client.connect(self.server.host, self.server.port)
        self.client.sendcmd('noop')
        s = get_server_handler().socket
        self.assertFalse(s.getsockopt(socket.SOL_TCP, socket.TCP_NODELAY))

    @retry_on_failure()
    def test_permit_foreign_address_false(self):
        handler = get_server_handler()
        with self.server.lock:
            handler.permit_foreign_addresses = False
            handler.remote_ip = '9.9.9.9'
        with self.assertRaises(ftplib.error_perm) as cm:
            self.client.makeport()
        self.assertIn('foreign address', str(cm.exception))

    @retry_on_failure()
    def test_permit_foreign_address_true(self):
        handler = get_server_handler()
        with self.server.lock:
            handler.permit_foreign_addresses = True
            handler.remote_ip = '9.9.9.9'
        s = self.client.makeport()
        s.close()

    @disable_log_warning
    @retry_on_failure()
    def test_permit_privileged_ports(self):
        # Test FTPHandler.permit_privileged_ports_active attribute

        # try to bind a socket on a privileged port
        sock = None
        for port in reversed(range(1, 1024)):
            try:
                socket.getservbyport(port)
            except socket.error:
                # not registered port; go on
                try:
                    sock = socket.socket(self.client.af, socket.SOCK_STREAM)
                    self.addCleanup(sock.close)
                    sock.settimeout(GLOBAL_TIMEOUT)
                    sock.bind((HOST, port))
                    break
                except socket.error as err:
                    if err.errno == errno.EACCES:
                        # root privileges needed
                        if sock is not None:
                            sock.close()
                        sock = None
                        break
                    sock.close()
                    continue
            else:
                # registered port found; skip to the next one
                continue
        else:
            # no usable privileged port was found
            sock = None

        with self.server.lock:
            self.server.handler.permit_privileged_ports = False
        self.assertRaises(ftplib.error_perm, self.client.sendport, HOST,
                          port)
        if sock:
            port = sock.getsockname()[1]
            with self.server.lock:
                self.server.handler.permit_privileged_ports = True
            sock.listen(5)
            sock.settimeout(GLOBAL_TIMEOUT)
            self.client.sendport(HOST, port)
            s, _ = sock.accept()
            s.close()

    @unittest.skipUnless(POSIX, "POSIX only")
    @unittest.skipIf(not PY3 and sendfile is None,
                     "pysendfile not installed")
    @retry_on_failure()
    def test_sendfile_fails(self):
        # Makes sure that if sendfile() fails and no bytes were
        # transmitted yet the server falls back on using plain
        # send()
        data = b'abcde12345' * 100000
        self.dummy_sendfile.write(data)
        self.dummy_sendfile.seek(0)
        self.client.storbinary('stor ' + self.tempfile, self.dummy_sendfile)
        with mock.patch('pyftpdlib.handlers.sendfile',
                        side_effect=OSError(errno.EINVAL)) as fun:
            self.client.retrbinary(
                'retr ' + self.tempfile, self.dummy_recvfile.write)
            assert fun.called
            self.dummy_recvfile.seek(0)
            datafile = self.dummy_recvfile.read()
            self.assertEqual(len(data), len(datafile))
            self.assertEqual(hash(data), hash(datafile))


if __name__ == '__main__':
    from pyftpdlib.test.runner import run_from_name
    run_from_name(__file__)
