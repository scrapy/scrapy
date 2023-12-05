"""
Test win32 shortcut script
"""

import os.path
import sys
import tempfile

from twisted.trial import unittest

skipReason = None
try:
    from win32com.shell import shell  # type: ignore[import]

    from twisted.python import shortcut
except ImportError:
    skipReason = "Only runs on Windows with win32com"

if sys.version_info[0:2] >= (3, 7):
    skipReason = "Broken on Python 3.7+."


class ShortcutTests(unittest.TestCase):
    skip = skipReason

    def test_create(self):
        """
        Create a simple shortcut.
        """
        testFilename = __file__
        baseFileName = os.path.basename(testFilename)
        s1 = shortcut.Shortcut(testFilename)
        tempname = self.mktemp() + ".lnk"
        s1.save(tempname)
        self.assertTrue(os.path.exists(tempname))
        sc = shortcut.open(tempname)
        scPath = sc.GetPath(shell.SLGP_RAWPATH)[0]
        self.assertEqual(scPath[-len(baseFileName) :].lower(), baseFileName.lower())

    def test_createPythonShortcut(self):
        """
        Create a shortcut to the Python executable,
        and set some values.
        """
        testFilename = sys.executable
        baseFileName = os.path.basename(testFilename)
        tempDir = tempfile.gettempdir()
        s1 = shortcut.Shortcut(
            path=testFilename,
            arguments="-V",
            description="The Python executable",
            workingdir=tempDir,
            iconpath=tempDir,
            iconidx=1,
        )
        tempname = self.mktemp() + ".lnk"
        s1.save(tempname)
        self.assertTrue(os.path.exists(tempname))
        sc = shortcut.open(tempname)
        scPath = sc.GetPath(shell.SLGP_RAWPATH)[0]
        self.assertEqual(scPath[-len(baseFileName) :].lower(), baseFileName.lower())
        self.assertEqual(sc.GetDescription(), "The Python executable")
        self.assertEqual(sc.GetWorkingDirectory(), tempDir)
        self.assertEqual(sc.GetIconLocation(), (tempDir, 1))
