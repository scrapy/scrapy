# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coveragepy/blob/master/NOTICE.txt

"""
Code coverage measurement for Python.

Ned Batchelder
https://coverage.readthedocs.io

"""

from __future__ import annotations

# mypy's convention is that "import as" names are public from the module.
# We import names as themselves to indicate that. Pylint sees it as pointless,
# so disable its warning.
# pylint: disable=useless-import-alias

from coverage.version import (
    __version__ as __version__,
    version_info as version_info,
)

from coverage.control import (
    Coverage as Coverage,
    process_startup as process_startup,
)
from coverage.data import CoverageData as CoverageData
from coverage.exceptions import CoverageException as CoverageException
from coverage.plugin import (
    CoveragePlugin as CoveragePlugin,
    FileReporter as FileReporter,
    FileTracer as FileTracer,
)

# Backward compatibility.
coverage = Coverage

# On Windows, we encode and decode deep enough that something goes wrong and
# the encodings.utf_8 module is loaded and then unloaded, I don't know why.
# Adding a reference here prevents it from being unloaded.  Yuk.
import encodings.utf_8      # pylint: disable=wrong-import-position, wrong-import-order
