"""
tests: this package contains all Scrapy unittests

see https://docs.scrapy.org/en/latest/contributing.html#running-tests
"""

import os
import socket
from pathlib import Path

# ignore system-wide proxies for tests
# which would send requests to a totally unsuspecting server
# (e.g. because urllib does not fully understand the proxy spec)
os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""
os.environ["ftp_proxy"] = ""

# Absolutize paths to coverage config and output file because tests that
# spawn subprocesses also changes current working directory.
_sourceroot = Path(__file__).resolve().parent.parent
if "COV_CORE_CONFIG" in os.environ:
    os.environ["COVERAGE_FILE"] = str(_sourceroot / ".coverage")
    os.environ["COV_CORE_CONFIG"] = str(_sourceroot / os.environ["COV_CORE_CONFIG"])

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
