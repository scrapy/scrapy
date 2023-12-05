# The MIT License
#
# Copyright (c) 2009-2011 Andreas Stuehrk
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

# mypy: disallow_untyped_defs=True
# mypy: disallow_untyped_calls=True

import curses
import errno
import os
import pydoc
import subprocess
import sys
import shlex
from typing import List


def get_pager_command(default: str = "less -rf") -> List[str]:
    command = shlex.split(os.environ.get("PAGER", default))
    return command


def page_internal(data: str) -> None:
    """A more than dumb pager function."""
    if hasattr(pydoc, "ttypager"):
        pydoc.ttypager(data)
    else:
        sys.stdout.write(data)


def page(data: str, use_internal: bool = False) -> None:
    command = get_pager_command()
    if not command or use_internal:
        page_internal(data)
    else:
        curses.endwin()
        try:
            popen = subprocess.Popen(command, stdin=subprocess.PIPE)
            assert popen.stdin is not None
            data_bytes = data.encode(sys.__stdout__.encoding, "replace")
            popen.stdin.write(data_bytes)
            popen.stdin.close()
        except OSError as e:
            if e.errno == errno.ENOENT:
                # pager command not found, fall back to internal pager
                page_internal(data)
                return
            if e.errno != errno.EPIPE:
                raise
        while True:
            try:
                popen.wait()
            except OSError as e:
                if e.errno != errno.EINTR:
                    raise
            else:
                break
        curses.doupdate()


# vim: sw=4 ts=4 sts=4 ai et
