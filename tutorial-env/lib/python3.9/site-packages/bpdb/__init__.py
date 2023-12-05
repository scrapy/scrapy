# The MIT License
#
# Copyright (c) 2008 Bob Farrell
# Copyright (c) 2013-2020 Sebastian Ramacher
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import os
import sys
import traceback

import bpython
from bpython.args import version_banner, copyright_banner
from .debugger import BPdb
from optparse import OptionParser
from pdb import Restart

__author__ = bpython.__author__
__copyright__ = bpython.__copyright__
__license__ = bpython.__license__
__version__ = bpython.__version__


def set_trace():
    """Just like pdb.set_trace(), a helper function that creates
    a debugger instance and sets the trace."""
    debugger = BPdb()
    debugger.set_trace(sys._getframe().f_back)


# Adopted verbatim from pdb for completeness:


def post_mortem(t=None):
    # handling the default
    if t is None:
        # sys.exc_info() returns (type, value, traceback) if an exception is
        # being handled, otherwise it returns None
        t = sys.exc_info()[2]
        if t is None:
            raise ValueError(
                "A valid traceback must be passed if no exception is being handled."
            )

    p = BPdb()
    p.reset()
    p.interaction(None, t)


def pm():
    post_mortem(getattr(sys, "last_traceback", None))


def main():
    parser = OptionParser(usage="Usage: %prog [options] [file [args]]")
    parser.add_option(
        "--version", "-V", action="store_true", help="Print version and exit."
    )
    options, args = parser.parse_args(sys.argv)
    if options.version:
        print(version_banner(base="bpdb"))
        print(copyright_banner())
        return 0

    if len(args) < 2:
        print("usage: bpdb scriptfile [arg] ...")
        return 2

    # The following code is based on Python's pdb.py.
    mainpyfile = args[1]
    if not os.path.exists(mainpyfile):
        print(f"Error: {mainpyfile} does not exist.")
        return 1

    # Hide bpdb from argument list.
    del sys.argv[0]

    # Replace bpdb's dir with script's dir in front of module search path.
    sys.path[0] = os.path.dirname(mainpyfile)

    pdb = BPdb()
    while True:
        try:
            pdb._runscript(mainpyfile)
            if pdb._user_requested_quit:
                break
            print("The program finished and will be restarted.")
        except Restart:
            print(f"Restarting {mainpyfile} with arguments:")
            print("\t" + " ".join(sys.argv[1:]))
        except SystemExit:
            # In most cases SystemExit does not warrant a post-mortem session.
            print(
                "The program exited via sys.exit(). Exit status: ",
            )
            print(sys.exc_info()[1])
        except:
            traceback.print_exc()
            print("Uncaught exception. Entering post mortem debugging.")
            print("Running 'cont' or 'step' will restart the program.")
            t = sys.exc_info()[2]
            pdb.interaction(None, t)
            print(
                f"Post mortem debugger finished. The {mainpyfile} will be restarted."
            )
