from __future__ import annotations

import ast
import asyncio
import builtins
import contextlib
import hmac
import inspect
import io
import logging
import secrets
import time
import traceback
from types import CodeType
from typing import TYPE_CHECKING, Any, Literal, cast

from aiohttp import web

import scrapy
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils._remote_control import (
    Envelope,
    job_files_dir,
    new_job_file_name,
    write_job_file,
)
from scrapy.utils.asyncio import is_asyncio_available

if TYPE_CHECKING:
    from pathlib import Path

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)

STOP_TIMEOUT = 2.0


class RemoteControl:
    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("REMOTE_CONTROL_ENABLED"):
            raise NotConfigured
        if (
            crawler.settings.getbool("TWISTED_REACTOR_ENABLED")
            and not is_asyncio_available()
        ):
            raise NotConfigured(
                f"{type(self).__name__} requires the asyncio support."
                f" You can set the REMOTE_CONTROL_ENABLED setting to False to remove this warning."
            )
        self.crawler: Crawler = crawler
        self._default_timeout: float = crawler.settings.getfloat(
            "REMOTE_CONTROL_TIMEOUT_DEFAULT"
        )
        self._max_timeout: float = crawler.settings.getfloat(
            "REMOTE_CONTROL_TIMEOUT_MAX"
        )
        self._output_max_bytes: int = crawler.settings.getint(
            "REMOTE_CONTROL_OUTPUT_MAX_BYTES"
        )
        self._traceback_max_bytes: int = crawler.settings.getint(
            "REMOTE_CONTROL_TRACEBACK_MAX_BYTES"
        )
        if self._default_timeout <= 0 or self._max_timeout <= 0:
            raise NotConfigured("REMOTE_CONTROL_TIMEOUT_* must be positive")

        self._stash: dict[str, Any] = {}
        self._auth_token: str | None = None
        self._runner: web.AppRunner | None = None
        self._job_file_path: Path | None = None

        crawler.signals.connect(self.start, signal=signals.engine_started)
        crawler.signals.connect(self.stop, signal=signals.engine_stopped)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def _make_namespace(self, buf: io.StringIO) -> dict[str, Any]:
        def _print(*args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("file", buf)
            builtins.print(*args, **kwargs)

        # Fresh each call except `stash` (same object, persists across calls)
        return {"crawler": self.crawler, "stash": self._stash, "print": _print}

    async def start(self) -> None:
        """Start the HTTP server."""
        try:
            self._auth_token = secrets.token_urlsafe(32)
            app = web.Application()
            app.router.add_post("/execute", self._handle_execute)
            self._runner = web.AppRunner(
                app, access_log=None, shutdown_timeout=STOP_TIMEOUT
            )
            await self._runner.setup()
            site = web.TCPSite(self._runner, "127.0.0.1", 0)
            await site.start()
            port = self._runner.addresses[0][1]

            job_path = job_files_dir(self.crawler.settings) / new_job_file_name()
            assert self.crawler.spider
            # we create the job file after starting the HTTP server
            write_job_file(
                job_path,
                spider=self.crawler.spider.name,
                project=self.crawler.settings.get("BOT_NAME"),
                scrapy_version=scrapy.__version__,
                port=port,
                token=self._auth_token,
            )
            self._job_file_path = job_path
            logger.info(
                f"Remote control HTTP server listening on"
                f" port {port} (job {job_path.stem})",
                extra={"crawler": self.crawler},
            )
        except Exception:
            logger.exception(
                "Remote control HTTP server failed to start",
                extra={"crawler": self.crawler},
            )
            await self.stop()

    async def stop(self) -> None:
        """Stop the HTTP server and remove the job file."""
        if self._job_file_path is not None:
            # we remove the job file before stopping the HTTP server
            with contextlib.suppress(OSError):
                self._job_file_path.unlink(missing_ok=True)
            self._job_file_path = None
        if self._runner is None:
            return
        try:
            await self._runner.cleanup()
        except Exception:
            logger.exception(
                "Error stopping the remote control HTTP server",
                extra={"crawler": self.crawler},
            )
        finally:
            self._stash.clear()
            self._runner = None
            self._auth_token = None

    async def _handle_execute(self, request: web.Request) -> web.Response:
        """An aiohttp request handler for the ``/execute`` endpoint."""
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if (
            not self._auth_token
            or not token.isascii()
            or not hmac.compare_digest(token, self._auth_token)
        ):
            return web.json_response({"error": "unauthorized"}, status=401)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON body"}, status=400)
        if not isinstance(body, dict) or not isinstance(body.get("code"), str):
            return web.json_response(
                {"error": "Missing or invalid 'code' value"}, status=400
            )
        requested_timeout = body.get("timeout_sec")
        if requested_timeout is not None and not isinstance(
            requested_timeout, (int, float)
        ):
            return web.json_response(
                {"error": "Invalid 'timeout_sec' value"}, status=400
            )
        timeout = _effective_timeout(
            requested_timeout, self._default_timeout, self._max_timeout
        )
        compiled = _compile(body["code"])
        result: Envelope
        if isinstance(compiled, CodeType):
            result = await self._run_code(compiled, timeout)
        else:
            result = {
                "status": "compile_error",
                "output": "",
                "traceback": compiled,
                "elapsed_sec": 0.0,
            }
        return web.json_response(result)

    async def _run_code(self, code_obj: CodeType, timeout: float) -> Envelope:
        """Run a compiled code object with a timeout and capture its output."""
        buf = io.StringIO()
        ns = self._make_namespace(buf)
        status: Literal["ok", "error", "timeout"] = "ok"
        tb: str | None = None
        start_time = time.perf_counter()
        try:
            # eval() returns a coroutine if and only if the source used a top-level await,
            # else it runs synchronously and returns None.
            eval_result = eval(code_obj, ns)  # noqa: S307 - arbitrary code by design
            if inspect.iscoroutine(eval_result):
                try:
                    await asyncio.wait_for(eval_result, timeout)
                except asyncio.TimeoutError:
                    # wait_for cancelled the coroutine at an await point.
                    status = "timeout"
        except Exception:
            # intentionally doesn't catch asyncio.CancelledError, which is a BaseException
            status = "error"
            tb = traceback.format_exc()
        elapsed = round(time.perf_counter() - start_time, 3)
        output, out_was_truncated = _cap(buf.getvalue(), self._output_max_bytes)
        if tb is not None:
            tb, tb_was_truncated = _cap(tb, self._traceback_max_bytes)
        else:
            tb_was_truncated = False
        result: Envelope = {
            "status": status,
            "output": output,
            "traceback": tb,
            "elapsed_sec": elapsed,
        }
        if out_was_truncated:
            result["output_truncated"] = True
        if tb_was_truncated:
            result["traceback_truncated"] = True
        return result


def _cap(s: str, limit: int) -> tuple[str, bool]:
    """Cap a string to ``limit`` bytes, appending an inline truncation marker."""
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s, False
    extra_kb = (len(b) - limit) // 1024 + 1
    head = b[:limit].decode("utf-8", "ignore")
    return f"{head}…[truncated, +{extra_kb}KB]", True


def _compile(src: str) -> CodeType | str:
    """Compile with top-level await support.

    :return: compiled code or a string with the traceback of the compile error.
    """
    try:
        return cast(
            "CodeType",
            compile(src, "<execute>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT),
        )
    except (SyntaxError, ValueError):
        return traceback.format_exc()


def _effective_timeout(
    requested: float | None, default: float, maximum: float
) -> float:
    """Clamp a client-requested timeout to ``maximum``."""
    if requested is None or not requested > 0:
        requested = default
    return min(requested, maximum)
