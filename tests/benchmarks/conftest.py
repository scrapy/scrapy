from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.utils.reactor import install_reactor

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="session", autouse=True)
def running_reactor() -> Generator[None]:
    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

    from twisted.internet import reactor

    # Marks the reactor as running without blocking, so that crawls can be
    # driven with reactor.iterate(), see tests.benchmarks.crawl().
    reactor.startRunning(installSignalHandlers=False)

    yield

    reactor.stop()
    # Lets the shutdown event triggers run, e.g. to join the thread pool.
    reactor.iterate(0)
