# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

if __name__ == "__main__":
    import sys

    from pkg_resources import load_entry_point

    sys.exit(load_entry_point("Twisted", "console_scripts", "trial")())
