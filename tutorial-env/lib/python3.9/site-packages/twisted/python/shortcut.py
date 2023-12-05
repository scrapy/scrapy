# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Creation of  Windows shortcuts.

Requires win32all.
"""

import os

import pythoncom  # type: ignore[import]
from win32com.shell import shell  # type: ignore[import]


def open(filename):
    """
    Open an existing shortcut for reading.

    @return: The shortcut object
    @rtype: Shortcut
    """
    sc = Shortcut()
    sc.load(filename)
    return sc


class Shortcut:
    """
    A shortcut on Win32.
    """

    def __init__(
        self,
        path=None,
        arguments=None,
        description=None,
        workingdir=None,
        iconpath=None,
        iconidx=0,
    ):
        """
        @param path: Location of the target
        @param arguments: If path points to an executable, optional arguments
                      to pass
        @param description: Human-readable description of target
        @param workingdir: Directory from which target is launched
        @param iconpath: Filename that contains an icon for the shortcut
        @param iconidx: If iconpath is set, optional index of the icon desired
        """
        self._base = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink,
        )
        if path is not None:
            self.SetPath(os.path.abspath(path))
        if arguments is not None:
            self.SetArguments(arguments)
        if description is not None:
            self.SetDescription(description)
        if workingdir is not None:
            self.SetWorkingDirectory(os.path.abspath(workingdir))
        if iconpath is not None:
            self.SetIconLocation(os.path.abspath(iconpath), iconidx)

    def load(self, filename):
        """
        Read a shortcut file from disk.
        """
        self._base.QueryInterface(pythoncom.IID_IPersistFile).Load(
            os.path.abspath(filename)
        )

    def save(self, filename):
        """
        Write the shortcut to disk.

        The file should be named something.lnk.
        """
        self._base.QueryInterface(pythoncom.IID_IPersistFile).Save(
            os.path.abspath(filename), 0
        )

    def __getattr__(self, name):
        return getattr(self._base, name)
