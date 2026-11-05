from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

try:
    from siosocks.io.asyncio import socks_server_handler
except ImportError:
    HAS_SIOSOCKS = False
else:
    HAS_SIOSOCKS = True

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def socks_proxy(**kwargs: Any) -> AsyncGenerator[str]:
    """Run a SOCKS4/SOCKS5 proxy and yield its ``host:port``. *kwargs* are
    passed to siosocks, e.g. ``username`` and ``password``."""
    server = await asyncio.start_server(
        lambda r, w: socks_server_handler(r, w, **kwargs), "127.0.0.1", 0
    )
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"127.0.0.1:{port}"
    finally:
        server.close()
