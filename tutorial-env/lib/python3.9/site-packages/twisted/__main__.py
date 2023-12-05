# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

# Make the twisted module executable with the default behaviour of
# running twist.
# This is not a docstring to avoid changing the string output of twist.


import sys

from pkg_resources import load_entry_point

if __name__ == "__main__":
    sys.exit(load_entry_point("Twisted", "console_scripts", "twist")())
