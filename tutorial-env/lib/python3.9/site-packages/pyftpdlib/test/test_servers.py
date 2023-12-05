# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

import contextlib
import ftplib
import inspect
import socket
import sys
import unittest

from pyftpdlib import handlers
from pyftpdlib import servers
from pyftpdlib._compat import super
from pyftpdlib.test import GLOBAL_TIMEOUT
from pyftpdlib.test import HOST
from pyftpdlib.test import PASSWD
from pyftpdlib.test import USER
from pyftpdlib.test import VERBOSITY
from pyftpdlib.test import WINDOWS
from pyftpdlib.test import PyftpdlibTestCase
from pyftpdlib.test import ThreadedTestFTPd
from pyftpdlib.test import close_client
from pyftpdlib.test.test_functional import TestCornerCases
from pyftpdlib.test.test_functional import TestFtpAbort
from pyftpdlib.test.test_functional import TestFtpAuthentication
from pyftpdlib.test.test_functional import TestFtpCmdsSemantic
from pyftpdlib.test.test_functional import TestFtpDummyCmds
from pyftpdlib.test.test_functional import TestFtpFsOperations
from pyftpdlib.test.test_functional import TestFtpListingCmds
from pyftpdlib.test.test_functional import TestFtpRetrieveData
from pyftpdlib.test.test_functional import TestFtpStoreData
from pyftpdlib.test.test_functional import TestIPv4Environment
from pyftpdlib.test.test_functional import TestIPv6Environment


MPROCESS_SUPPORT = hasattr(servers, 'MultiprocessFTPServer')


class TestFTPServer(PyftpdlibTestCase):
    """Tests for *FTPServer classes."""
    server_class = ThreadedTestFTPd
    client_class = ftplib.FTP

    def setUp(self):
        super().setUp()
        self.server = None
        self.client = None

    def tearDown(self):
        if self.client is not None:
            close_client(self.client)
        if self.server is not None:
            self.server.stop()
        super().tearDown()

    @unittest.skipIf(WINDOWS, "POSIX only")
    def test_sock_instead_of_addr(self):
        # pass a socket object instead of an address tuple to FTPServer
        # constructor
        with contextlib.closing(socket.socket()) as sock:
            sock.bind((HOST, 0))
            sock.listen(5)
            ip, port = sock.getsockname()[:2]
            self.server = self.server_class(sock)
            self.server.start()
            self.client = self.client_class(timeout=GLOBAL_TIMEOUT)
            self.client.connect(ip, port)
            self.client.login(USER, PASSWD)

    def test_ctx_mgr(self):
        with servers.FTPServer((HOST, 0), handlers.FTPHandler) as server:
            self.assertIsNotNone(server)


# =====================================================================
# --- threaded FTP server mixin tests
# =====================================================================

# What we're going to do here is repeat the original functional tests
# defined in test_functinal.py but by using different concurrency
# modules (multi thread and multi process instead of async.
# This is useful as we reuse the existent functional tests which are
# supposed to work no matter what the concurrency model is.


class _TFTPd(ThreadedTestFTPd):
    server_class = servers.ThreadedFTPServer


class ThreadFTPTestMixin:
    server_class = _TFTPd


class TestFtpAuthenticationThreadMixin(ThreadFTPTestMixin,
                                       TestFtpAuthentication):
    pass


class TestTFtpDummyCmdsThreadMixin(ThreadFTPTestMixin, TestFtpDummyCmds):
    pass


class TestFtpCmdsSemanticThreadMixin(ThreadFTPTestMixin, TestFtpCmdsSemantic):
    pass


class TestFtpFsOperationsThreadMixin(ThreadFTPTestMixin, TestFtpFsOperations):
    pass


class TestFtpStoreDataThreadMixin(ThreadFTPTestMixin, TestFtpStoreData):
    pass


class TestFtpRetrieveDataThreadMixin(ThreadFTPTestMixin, TestFtpRetrieveData):
    pass


class TestFtpListingCmdsThreadMixin(ThreadFTPTestMixin, TestFtpListingCmds):
    pass


class TestFtpAbortThreadMixin(ThreadFTPTestMixin, TestFtpAbort):
    pass


# class TestTimeoutsThreadMixin(ThreadFTPTestMixin, TestTimeouts):
#     def test_data_timeout_not_reached(self): pass
# class TestConfOptsThreadMixin(ThreadFTPTestMixin, TestConfigurableOptions):
#     pass


# class TestCallbacksThreadMixin(ThreadFTPTestMixin, TestCallbacks):
#     pass


class TestIPv4EnvironmentThreadMixin(ThreadFTPTestMixin, TestIPv4Environment):
    pass


class TestIPv6EnvironmentThreadMixin(ThreadFTPTestMixin, TestIPv6Environment):
    pass


class TestCornerCasesThreadMixin(ThreadFTPTestMixin, TestCornerCases):
    pass


# class TestFTPServerThreadMixin(ThreadFTPTestMixin, TestFTPServer):
#     pass


# =====================================================================
# --- multiprocess FTP server mixin tests
# =====================================================================

if MPROCESS_SUPPORT:
    class MultiProcFTPd(ThreadedTestFTPd):
        server_class = servers.MultiprocessFTPServer

    class MProcFTPTestMixin:
        server_class = MultiProcFTPd
else:
    @unittest.skipIf(True, "multiprocessing module not installed")
    class MProcFTPTestMixin:
        pass


class TestFtpAuthenticationMProcMixin(MProcFTPTestMixin,
                                      TestFtpAuthentication):
    pass


class TestTFtpDummyCmdsMProcMixin(MProcFTPTestMixin, TestFtpDummyCmds):
    pass


class TestFtpCmdsSemanticMProcMixin(MProcFTPTestMixin, TestFtpCmdsSemantic):
    pass


class TestFtpFsOperationsMProcMixin(MProcFTPTestMixin, TestFtpFsOperations):

    def test_unforeseen_mdtm_event(self):
        pass


class TestFtpStoreDataMProcMixin(MProcFTPTestMixin, TestFtpStoreData):
    pass


class TestFtpRetrieveDataMProcMixin(MProcFTPTestMixin, TestFtpRetrieveData):
    pass


class TestFtpListingCmdsMProcMixin(MProcFTPTestMixin, TestFtpListingCmds):
    pass


class TestFtpAbortMProcMixin(MProcFTPTestMixin, TestFtpAbort):
    pass


# class TestTimeoutsMProcMixin(MProcFTPTestMixin, TestTimeouts):
#     def test_data_timeout_not_reached(self): pass
# class TestConfiOptsMProcMixin(MProcFTPTestMixin, TestConfigurableOptions):
#     pass
# class TestCallbacksMProcMixin(MProcFTPTestMixin, TestCallbacks): pass


class TestIPv4EnvironmentMProcMixin(MProcFTPTestMixin, TestIPv4Environment):
    pass


class TestIPv6EnvironmentMProcMixin(MProcFTPTestMixin, TestIPv6Environment):
    pass


class TestCornerCasesMProcMixin(MProcFTPTestMixin, TestCornerCases):
    pass


# class TestFTPServerMProcMixin(MProcFTPTestMixin, TestFTPServer):
#     pass


def main():
    test_classes = set()
    for name, obj in inspect.getmembers(sys.modules[__name__]):
        if inspect.isclass(obj):
            if obj.__module__ == '__main__' and name.startswith('Test'):
                test_classes.add(obj)

    loader = unittest.TestLoader()
    suite = []
    for test_class in test_classes:
        suite.append(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=VERBOSITY)
    result = runner.run(unittest.TestSuite(unittest.TestSuite(suite)))
    success = result.wasSuccessful()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
