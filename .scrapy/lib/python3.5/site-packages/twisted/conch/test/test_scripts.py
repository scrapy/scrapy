# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the command-line interfaces to conch.
"""
from twisted.python.reflect import requireModule

if requireModule('pyasn1'):
    pyasn1Skip = None
else:
    pyasn1Skip =  "Cannot run without PyASN1"

if requireModule('cryptography'):
    cryptoSkip = None
else:
    cryptoSkip = "can't run w/o cryptography"

if requireModule('tty'):
    ttySkip = None
else:
    ttySkip = "can't run w/o tty"

try:
    import Tkinter
except ImportError:
    tkskip = "can't run w/o Tkinter"
else:
    try:
        Tkinter.Tk().destroy()
    except Tkinter.TclError as e:
        tkskip = "Can't test Tkinter: " + str(e)
    else:
        tkskip = None

from twisted.trial.unittest import TestCase
from twisted.scripts.test.test_scripts import ScriptTestsMixin
from twisted.python.test.test_shellcomp import ZshScriptTestMixin



class ScriptTests(TestCase, ScriptTestsMixin):
    """
    Tests for the Conch scripts.
    """
    skip = pyasn1Skip or cryptoSkip


    def test_conch(self):
        self.scriptTest("conch/conch")
    test_conch.skip = ttySkip or skip


    def test_cftp(self):
        self.scriptTest("conch/cftp")
    test_cftp.skip = ttySkip or skip


    def test_ckeygen(self):
        self.scriptTest("conch/ckeygen")


    def test_tkconch(self):
        self.scriptTest("conch/tkconch")
    test_tkconch.skip = tkskip or skip



class ZshIntegrationTests(TestCase, ZshScriptTestMixin):
    """
    Test that zsh completion functions are generated without error
    """
    generateFor = [('conch', 'twisted.conch.scripts.conch.ClientOptions'),
                   ('cftp', 'twisted.conch.scripts.cftp.ClientOptions'),
                   ('ckeygen', 'twisted.conch.scripts.ckeygen.GeneralOptions'),
                   ('tkconch', 'twisted.conch.scripts.tkconch.GeneralOptions'),
                   ]
