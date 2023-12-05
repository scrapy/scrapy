# The MIT License
#
# Copyright (c) 2008 Bob Farrell
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

import pdb
import bpython


class BPdb(pdb.Pdb):
    """PDB with BPython support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompt = "(BPdb) "
        self.intro = 'Use "B" to enter bpython, Ctrl-d to exit it.'

    def postloop(self):
        # We only want to show the intro message once.
        self.intro = None
        super().postloop()

    # cmd.Cmd commands

    def do_Bpython(self, arg):
        locals_ = self.curframe.f_globals.copy()
        locals_.update(self.curframe.f_locals)
        bpython.embed(locals_, ["-i"])

    def help_Bpython(self):
        print("B(python)")
        print("")
        print(
            "Invoke the bpython interpreter for this stack frame. To exit "
            "bpython and return to a standard pdb press Ctrl-d"
        )

    # shortcuts
    do_B = do_Bpython
    help_B = help_Bpython
