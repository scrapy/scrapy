# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Script used by twisted.test.test_process on win32.
"""


import msvcrt
import os
import sys

msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)  # type:ignore[attr-defined]
msvcrt.setmode(sys.stderr.fileno(), os.O_BINARY)  # type:ignore[attr-defined]

# We want to write bytes directly to the output, not text, because otherwise
# newlines get mangled. Get the underlying buffer.
stdout = sys.stdout.buffer
stderr = sys.stderr.buffer
stdin = sys.stdin.buffer

stdout.write(b"out\n")
stdout.flush()
stderr.write(b"err\n")
stderr.flush()

data = stdin.read()

stdout.write(data)
stdout.write(b"\nout\n")
stderr.write(b"err\n")

sys.stdout.flush()
sys.stderr.flush()
