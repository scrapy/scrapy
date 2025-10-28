import contextlib
import os
import socket
from pathlib import Path

from twisted.internet.defer import Deferred


def twisted_sleep(seconds):
    from twisted.internet import reactor

    d = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d


def get_script_run_env() -> dict[str, str]:
    """Return a OS environment dict suitable to run scripts shipped with tests."""

    tests_path = Path(__file__).parent.parent
    pythonpath = str(tests_path) + os.pathsep + os.environ.get("PYTHONPATH", "")
    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath
    return env


def ipv6_loopback_available() -> bool:
    """
    Return True if the IPv6 loopback address (::1) can be bound on this host.

    Returns:
        True if binding to `::1` succeeded (IPv6 loopback is available),
        False if IPv6 is not supported or an OSError occurred while binding.

    Use as a decorator:
    pytest.mark.skipif(not _ipv6_loopback_available(), reason="IPv6 loopback is not available")
    """
    if not getattr(socket, "has_ipv6", False):
        return False
    try:
        with contextlib.closing(
            socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        ) as s:
            with contextlib.suppress(OSError, AttributeError):
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            s.bind(("::1", 0))
        return True
    except OSError:
        return False
