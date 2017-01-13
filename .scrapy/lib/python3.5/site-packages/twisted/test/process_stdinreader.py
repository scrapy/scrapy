# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""Script used by twisted.test.test_process on win32."""

import sys, os, msvcrt
msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
msvcrt.setmode(sys.stderr.fileno(), os.O_BINARY)


sys.stdout.write("out\n")
sys.stdout.flush()
sys.stderr.write("err\n")
sys.stderr.flush()

data = sys.stdin.read()

sys.stdout.write(data)
sys.stdout.write("\nout\n")
sys.stderr.write("err\n")

sys.stdout.flush()
sys.stderr.flush()
