# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.runtime}.
"""

from __future__ import division, absolute_import

import sys

from twisted.python.reflect import namedModule
from twisted.trial.util import suppress as SUPRESS
from twisted.trial.unittest import SynchronousTestCase

from twisted.python.runtime import Platform, shortPythonVersion


class PythonVersionTests(SynchronousTestCase):
    """
    Tests the shortPythonVersion method.
    """

    def test_shortPythonVersion(self):
        """
        Verify if the Python version is returned correctly.
        """
        ver = shortPythonVersion().split('.')
        for i in range(3):
            self.assertEqual(int(ver[i]), sys.version_info[i])



class PlatformTests(SynchronousTestCase):
    """
    Tests for the default L{Platform} initializer.
    """

    isWinNTDeprecationMessage = ('twisted.python.runtime.Platform.isWinNT was '
        'deprecated in Twisted 13.0. Use Platform.isWindows instead.')


    def test_isKnown(self):
        """
        L{Platform.isKnown} returns a boolean indicating whether this is one of
        the L{runtime.knownPlatforms}.
        """
        platform = Platform()
        self.assertTrue(platform.isKnown())


    def test_isVistaConsistency(self):
        """
        Verify consistency of L{Platform.isVista}: it can only be C{True} if
        L{Platform.isWinNT} and L{Platform.isWindows} are C{True}.
        """
        platform = Platform()
        if platform.isVista():
            self.assertTrue(platform.isWinNT())
            self.assertTrue(platform.isWindows())
            self.assertFalse(platform.isMacOSX())


    def test_isMacOSXConsistency(self):
        """
        L{Platform.isMacOSX} can only return C{True} if L{Platform.getType}
        returns C{'posix'}.
        """
        platform = Platform()
        if platform.isMacOSX():
            self.assertEqual(platform.getType(), 'posix')


    def test_isLinuxConsistency(self):
        """
        L{Platform.isLinux} can only return C{True} if L{Platform.getType}
        returns C{'posix'} and L{sys.platform} starts with C{"linux"}.
        """
        platform = Platform()
        if platform.isLinux():
            self.assertTrue(sys.platform.startswith("linux"))


    def test_isWinNT(self):
        """
        L{Platform.isWinNT} can return only C{False} or C{True} and can not
        return C{True} if L{Platform.getType} is not C{"win32"}.
        """
        platform = Platform()
        isWinNT = platform.isWinNT()
        self.assertIn(isWinNT, (False, True))
        if platform.getType() != "win32":
            self.assertFalse(isWinNT)

    test_isWinNT.suppress = [SUPRESS(category=DeprecationWarning,
         message=isWinNTDeprecationMessage)]


    def test_isWinNTDeprecated(self):
        """
        L{Platform.isWinNT} is deprecated in favor of L{platform.isWindows}.
        """
        platform = Platform()
        platform.isWinNT()
        warnings = self.flushWarnings([self.test_isWinNTDeprecated])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0]['message'], self.isWinNTDeprecationMessage)


    def test_supportsThreads(self):
        """
        L{Platform.supportsThreads} returns C{True} if threads can be created in
        this runtime, C{False} otherwise.
        """
        # It's difficult to test both cases of this without faking the threading
        # module.  Perhaps an adequate test is to just test the behavior with
        # the current runtime, whatever that happens to be.
        try:
            namedModule('threading')
        except ImportError:
            self.assertFalse(Platform().supportsThreads())
        else:
            self.assertTrue(Platform().supportsThreads())



class ForeignPlatformTests(SynchronousTestCase):
    """
    Tests for L{Platform} based overridden initializer values.
    """

    def test_getType(self):
        """
        If an operating system name is supplied to L{Platform}'s initializer,
        L{Platform.getType} returns the platform type which corresponds to that
        name.
        """
        self.assertEqual(Platform('nt').getType(), 'win32')
        self.assertEqual(Platform('ce').getType(), 'win32')
        self.assertEqual(Platform('posix').getType(), 'posix')
        self.assertEqual(Platform('java').getType(), 'java')


    def test_isMacOSX(self):
        """
        If a system platform name is supplied to L{Platform}'s initializer, it
        is used to determine the result of L{Platform.isMacOSX}, which returns
        C{True} for C{"darwin"}, C{False} otherwise.
        """
        self.assertTrue(Platform(None, 'darwin').isMacOSX())
        self.assertFalse(Platform(None, 'linux2').isMacOSX())
        self.assertFalse(Platform(None, 'win32').isMacOSX())


    def test_isLinux(self):
        """
        If a system platform name is supplied to L{Platform}'s initializer, it
        is used to determine the result of L{Platform.isLinux}, which returns
        C{True} for values beginning with C{"linux"}, C{False} otherwise.
        """
        self.assertFalse(Platform(None, 'darwin').isLinux())
        self.assertTrue(Platform(None, 'linux').isLinux())
        self.assertTrue(Platform(None, 'linux2').isLinux())
        self.assertTrue(Platform(None, 'linux3').isLinux())
        self.assertFalse(Platform(None, 'win32').isLinux())



class DockerPlatformTests(SynchronousTestCase):
    """
    Tests for L{twisted.python.runtime.Platform.isDocker}.
    """

    def test_noChecksOnLinux(self):
        """
        If the platform is not Linux, C{isDocker()} always returns L{False}.
        """
        platform = Platform(None, 'win32')
        self.assertFalse(platform.isDocker())


    def test_noCGroups(self):
        """
        If the platform is Linux, and the cgroups file in C{/proc} does not
        exist, C{isDocker()} returns L{False}
        """
        platform = Platform(None, 'linux')
        self.assertFalse(platform.isDocker(_initCGroupLocation="fakepath"))


    def test_cgroupsSuggestsDocker(self):
        """
        If the platform is Linux, and the cgroups file (faked out here) exists,
        and one of the paths starts with C{/docker/}, C{isDocker()} returns
        C{True}.
        """
        cgroupsFile = self.mktemp()
        with open(cgroupsFile, 'wb') as f:
            # real cgroups file from inside a Debian 7 docker container
            f.write(b"""10:debug:/
9:net_prio:/
8:perf_event:/docker/104155a6453cb67590027e397dc90fc25a06a7508403c797bc89ea43adf8d35f
7:net_cls:/
6:freezer:/docker/104155a6453cb67590027e397dc90fc25a06a7508403c797bc89ea43adf8d35f
5:devices:/docker/104155a6453cb67590027e397dc90fc25a06a7508403c797bc89ea43adf8d35f
4:blkio:/docker/104155a6453cb67590027e397dc90fc25a06a7508403c797bc89ea43adf8d35f
3:cpuacct:/docker/104155a6453cb67590027e397dc90fc25a06a7508403c797bc89ea43adf8d35f
2:cpu:/docker/104155a6453cb67590027e397dc90fc25a06a7508403c797bc89ea43adf8d35f
1:cpuset:/docker/104155a6453cb67590027e397dc90fc25a06a7508403c797bc89ea43adf8d35f""")

        platform = Platform(None, 'linux')
        self.assertTrue(platform.isDocker(_initCGroupLocation=cgroupsFile))


    def test_cgroupsSuggestsRealSystem(self):
        """
        If the platform is Linux, and the cgroups file (faked out here) exists,
        and none of the paths starts with C{/docker/}, C{isDocker()} returns
        C{False}.
        """
        cgroupsFile = self.mktemp()
        with open(cgroupsFile, 'wb') as f:
            # real cgroups file from a Fedora 17 system
            f.write(b"""9:perf_event:/
8:blkio:/
7:net_cls:/
6:freezer:/
5:devices:/
4:memory:/
3:cpuacct,cpu:/
2:cpuset:/
1:name=systemd:/system""")

        platform = Platform(None, 'linux')
        self.assertFalse(platform.isDocker(_initCGroupLocation=cgroupsFile))
