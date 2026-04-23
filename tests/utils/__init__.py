import asyncio
import os
from pathlib import Path

from twisted.internet.defer import Deferred

from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.defer import maybe_deferred_to_future


def twisted_sleep(seconds: float):
    from twisted.internet import reactor

    d: Deferred[None] = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d


async def async_sleep(seconds: float) -> None:
    if is_asyncio_available():
        await asyncio.sleep(seconds)
    else:
        await maybe_deferred_to_future(twisted_sleep(seconds))


def get_script_run_env() -> dict[str, str]:
    """Return a OS environment dict suitable to run scripts shipped with tests."""

    tests_path = Path(__file__).parent.parent
    pythonpath = str(tests_path) + os.pathsep + os.environ.get("PYTHONPATH", "")
    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath
    return env
