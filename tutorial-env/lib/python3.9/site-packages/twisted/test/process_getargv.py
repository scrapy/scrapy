# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Used by L{twisted.test.test_process}.
"""


from sys import argv, stdout

if __name__ == "__main__":

    stdout.write(chr(0).join(argv))
    stdout.flush()
