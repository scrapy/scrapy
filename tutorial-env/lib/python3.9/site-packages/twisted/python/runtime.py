# -*- test-case-name: twisted.python.test.test_runtime -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

__all__ = [
    "seconds",
    "shortPythonVersion",
    "Platform",
    "platform",
    "platformType",
]
import os
import sys
import warnings
from time import time as seconds
from typing import Optional


def shortPythonVersion() -> str:
    """
    Returns the Python version as a dot-separated string.
    """
    return "%s.%s.%s" % sys.version_info[:3]


knownPlatforms = {
    "nt": "win32",
    "ce": "win32",
    "posix": "posix",
    "java": "java",
    "org.python.modules.os": "java",
}


class Platform:
    """
    Gives us information about the platform we're running on.
    """

    type: Optional[str] = knownPlatforms.get(os.name)
    seconds = staticmethod(seconds)
    _platform = sys.platform

    def __init__(
        self, name: Optional[str] = None, platform: Optional[str] = None
    ) -> None:
        if name is not None:
            self.type = knownPlatforms.get(name)
        if platform is not None:
            self._platform = platform

    def isKnown(self) -> bool:
        """
        Do we know about this platform?

        @return: Boolean indicating whether this is a known platform or not.
        """
        return self.type != None

    def getType(self) -> Optional[str]:
        """
        Get platform type.

        @return: Either 'posix', 'win32' or 'java'
        """
        return self.type

    def isMacOSX(self) -> bool:
        """
        Check if current platform is macOS.

        @return: C{True} if the current platform has been detected as macOS.
        """
        return self._platform == "darwin"

    def isWinNT(self) -> bool:
        """
        Are we running in Windows NT?

        This is deprecated and always returns C{True} on win32 because
        Twisted only supports Windows NT-derived platforms at this point.

        @return: C{True} if the current platform has been detected as
            Windows NT.
        """
        warnings.warn(
            "twisted.python.runtime.Platform.isWinNT was deprecated in "
            "Twisted 13.0. Use Platform.isWindows instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.isWindows()

    def isWindows(self) -> bool:
        """
        Are we running in Windows?

        @return: C{True} if the current platform has been detected as
            Windows.
        """
        return self.getType() == "win32"

    def isVista(self) -> bool:
        """
        Check if current platform is Windows Vista or Windows Server 2008.

        @return: C{True} if the current platform has been detected as Vista
        """
        return sys.platform == "win32" and sys.getwindowsversion().major == 6

    def isLinux(self) -> bool:
        """
        Check if current platform is Linux.

        @return: C{True} if the current platform has been detected as Linux.
        """
        return self._platform.startswith("linux")

    def isDocker(self, _initCGroupLocation: str = "/proc/1/cgroup") -> bool:
        """
        Check if the current platform is Linux in a Docker container.

        @return: C{True} if the current platform has been detected as Linux
            inside a Docker container.
        """
        if not self.isLinux():
            return False

        from twisted.python.filepath import FilePath

        # Ask for the cgroups of init (pid 1)
        initCGroups = FilePath(_initCGroupLocation)
        if initCGroups.exists():
            # The cgroups file looks like "2:cpu:/". The third element will
            # begin with /docker if it is inside a Docker container.
            controlGroups = [
                x.split(b":") for x in initCGroups.getContent().split(b"\n")
            ]

            for group in controlGroups:
                if len(group) == 3 and group[2].startswith(b"/docker/"):
                    # If it starts with /docker/, we're in a docker container
                    return True

        return False

    def _supportsSymlinks(self) -> bool:
        """
        Check for symlink support usable for Twisted's purposes.

        @return: C{True} if symlinks are supported on the current platform,
                 otherwise C{False}.
        """
        if self.isWindows():
            # We do the isWindows() check as newer Pythons support the symlink
            # support in Vista+, but only if you have some obscure permission
            # (SeCreateSymbolicLinkPrivilege), which can only be given on
            # platforms with msc.exe (so, Business/Enterprise editions).
            # This uncommon requirement makes the Twisted test suite test fail
            # in 99.99% of cases as general users don't have permission to do
            # it, even if there is "symlink support".
            return False
        else:
            # If we're not on Windows, check for existence of os.symlink.
            try:
                os.symlink
            except AttributeError:
                return False
            else:
                return True

    def supportsThreads(self) -> bool:
        """
        Can threads be created?

        @return: C{True} if the threads are supported on the current platform.
        """
        try:
            import threading

            return threading is not None  # shh pyflakes
        except ImportError:
            return False

    def supportsINotify(self) -> bool:
        """
        Return C{True} if we can use the inotify API on this platform.

        @since: 10.1
        """
        try:
            from twisted.python._inotify import INotifyError, init
        except ImportError:
            return False

        try:
            os.close(init())
        except INotifyError:
            return False
        return True


platform = Platform()
platformType = platform.getType()
