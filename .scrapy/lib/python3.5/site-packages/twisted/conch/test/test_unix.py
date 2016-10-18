# -*- test-case-name: twisted.conch.test.test_unix -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import

from zope.interface import implementer

from twisted.internet.interfaces import IReactorProcess
from twisted.python.reflect import requireModule
from twisted.trial import unittest

from .test_session import StubConnection, StubClient

unix = requireModule('twisted.conch.unix')



@implementer(IReactorProcess)
class MockProcessSpawner(object):
    """
    An L{IReactorProcess} that logs calls to C{spawnProcess}.
    """

    def __init__(self):
        self._spawnProcessCalls = []


    def spawnProcess(self, processProtocol, executable, args=(), env={},
                     path=None, uid=None, gid=None, usePTY=0, childFDs=None):
        """
        Log a call to C{spawnProcess}. Do not actually spawn a process.
        """
        self._spawnProcessCalls.append(
            {'processProtocol': processProtocol,
             'executable': executable,
             'args': args,
             'env': env,
             'path': path,
             'uid': uid,
             'gid': gid,
             'usePTY': usePTY,
             'childFDs': childFDs})



class StubUnixConchUser(object):
    """
    Enough of UnixConchUser to exercise SSHSessionForUnixConchUser in the
    tests below.
    """

    def __init__(self, homeDirectory):
        self._homeDirectory = homeDirectory
        self.conn = StubConnection(transport=StubClient())


    def getUserGroupId(self):
        return (None, None)


    def getHomeDir(self):
        return self._homeDirectory


    def getShell(self):
        pass



class TestSSHSessionForUnixConchUser(unittest.TestCase):

    if unix is None:
        skip = "Unix system required"


    def testExecCommandEnvironment(self):
        """
        C{execCommand} sets the C{HOME} environment variable to the avatar's home
        directory.
        """
        mockReactor = MockProcessSpawner()
        homeDirectory = "/made/up/path/"
        avatar = StubUnixConchUser(homeDirectory)
        session = unix.SSHSessionForUnixConchUser(avatar, reactor=mockReactor)
        protocol = None
        command = ["not-actually-executed"]
        session.execCommand(protocol, command)
        [call] = mockReactor._spawnProcessCalls
        self.assertEqual(homeDirectory, call['env']['HOME'])
