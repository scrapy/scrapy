"""
tests: this package contains all Scrapy unittests

see https://docs.scrapy.org/en/latest/contributing.html#running-tests
"""

import os
import socket
from pathlib import Path

from twisted import version as TWISTED_VERSION
from twisted.python.versions import Version

# ignore system-wide proxies for tests
# which would send requests to a totally unsuspecting server
# (e.g. because urllib does not fully understand the proxy spec)
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""
os.environ["ftp_proxy"] = ""

tests_datadir = str(Path(__file__).parent.resolve() / "sample_data")


# In some environments accessing a non-existing host doesn't raise an
# error. In such cases we're going to skip tests which rely on it.
try:
    socket.getaddrinfo("non-existing-host", 80)
    NON_EXISTING_RESOLVABLE = True
except socket.gaierror:
    NON_EXISTING_RESOLVABLE = False


def get_testdata(*paths: str) -> bytes:
    """Return test data"""
    return Path(tests_datadir, *paths).read_bytes()


TWISTED_KEEPS_TRACEBACKS = TWISTED_VERSION >= Version("twisted", 24, 10, 0)
