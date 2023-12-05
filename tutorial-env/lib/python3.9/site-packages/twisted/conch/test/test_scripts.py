# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the command-line interfaces to conch.
"""
from unittest import skipIf

from twisted.python.reflect import requireModule
from twisted.python.test.test_shellcomp import ZshScriptTestMixin
from twisted.scripts.test.test_scripts import ScriptTestsMixin
from twisted.trial.unittest import TestCase

doSkip = False
skipReason = ""

if not requireModule("pyasn1"):
    doSkip = True
    skipReason = "Cannot run without PyASN1"

if not requireModule("cryptography"):
    doSkip = True
    cryptoSkip = "can't run w/o cryptography"

if not requireModule("tty"):
    doSkip = True
    ttySkip = "can't run w/o tty"

try:
    import tkinter
except ImportError:
    doSkip = True
    skipReason = "can't run w/o tkinter"
else:
    try:
        tkinter.Tk().destroy()
    except tkinter.TclError as e:
        doSkip = True
        skipReason = "Can't test Tkinter: " + str(e)


@skipIf(doSkip, skipReason)
class ScriptTests(TestCase, ScriptTestsMixin):
    """
    Tests for the Conch scripts.
    """

    def test_conch(self):
        self.scriptTest("conch/conch")

    def test_cftp(self):
        self.scriptTest("conch/cftp")

    def test_ckeygen(self):
        self.scriptTest("conch/ckeygen")

    def test_tkconch(self):
        self.scriptTest("conch/tkconch")


class ZshIntegrationTests(TestCase, ZshScriptTestMixin):
    """
    Test that zsh completion functions are generated without error
    """

    generateFor = [
        ("conch", "twisted.conch.scripts.conch.ClientOptions"),
        ("cftp", "twisted.conch.scripts.cftp.ClientOptions"),
        ("ckeygen", "twisted.conch.scripts.ckeygen.GeneralOptions"),
        ("tkconch", "twisted.conch.scripts.tkconch.GeneralOptions"),
    ]
