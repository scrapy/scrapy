# Copyright 2021-2022 Sebastian Ramacher <sebastian@ramacher.at>
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
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Bindings for wcwidth(3) and wcswidth(3)

This module computes the number of cells a unicode string is expected to occupy
on the screen. On systems conforming to POSIX.1-2001 to POSIX.1-2008, this
module calls wcwidth(3) and wcswidth(3) provided by C library. On systems where
these functions are not available, a compatible implementation is included in
the module.

This module provides the same interface as the wcwidth module.
"""

from ._impl import wcwidth, wcswidth

__version__ = "0.1.9"
__author__ = "Sebastian Ramacher"
__license__ = "Expat"
__copyright__ = f"(C) 2021-2022 {__author__}"
__all__ = ("wcwidth", "wcswidth")
