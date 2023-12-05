"""The Sphinx documentation toolchain."""

import sys

from sphinx.cmd.build import main

sys.exit(main(sys.argv[1:]))
