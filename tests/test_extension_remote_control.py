from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
import pytest
from aiohttp import web

from scrapy.exceptions import NotConfigured
from scrapy.extensions import remote_control
from scrapy.extensions.remote_control import (
    RemoteControl,
    _cap,
    _compile,
    _effective_timeout,
)
from scrapy.settings import default_settings
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import CodeType

pytestmark = pytest.mark.only_asyncio


def _get_extension(settings: dict[str, Any] | None = None) -> RemoteControl:
    crawler = get_crawler(
        settings_dict={"REMOTE_CONTROL_ENABLED": True, **(settings or {})}
    )
    crawler.spider = crawler._create_spider()
    return RemoteControl(crawler)


def compile_or_fail(source: str) -> CodeType:
    compiled = _compile(source)
    assert not isinstance(compiled, str)
    return compiled


@asynccontextmanager
async def _started_extension(
    jobs_dir: Path, settings: dict[str, Any] | None = None
) -> AsyncGenerator[RemoteControl]:
    extension = _get_extension(
        {"REMOTE_CONTROL_JOBS_DIR": str(jobs_dir), **(settings or {})}
    )
    await extension.start()
    assert extension._runner is not None, "the server did not start"
    try:
        yield extension
    finally:
        await extension.stop()


async def _post(extension: RemoteControl, **kwargs: Any) -> tuple[int, Any]:
    assert extension._runner
    host, port = extension._runner.addresses[0]
    url = f"http://{host}:{port}/execute"
    async with (
        aiohttp.ClientSession() as session,
        session.post(url, **kwargs) as response,
    ):
        return response.status, await response.json(content_type=None)


def _auth(extension: RemoteControl) -> dict[str, str]:
    return {"Authorization": f"Bearer {extension._auth_token}"}


@coroutine_test
async def test_ok_output() -> None:
    extension = _get_extension()
    result = await extension._run_code(compile_or_fail("print('hello')"), 5)
    assert result["status"] == "ok"
    assert result["output"] == "hello\n"
    assert result["traceback"] is None
    assert "output_truncated" not in result
    assert "traceback_truncated" not in result


@coroutine_test
async def test_top_level_await() -> None:
    extension = _get_extension()
    result = await extension._run_code(
        compile_or_fail("import asyncio\nawait asyncio.sleep(0)\nprint('done')"), 5
    )
    assert result["status"] == "ok"
    assert result["output"] == "done\n"


@coroutine_test
async def test_sync_code_runs() -> None:
    extension = _get_extension()
    result = await extension._run_code(
        compile_or_fail("x = sum(range(10))\nprint(x)"), 5
    )
    assert result["status"] == "ok"
    assert result["output"] == "45\n"


@coroutine_test
async def test_crawler_is_in_the_namespace() -> None:
    extension = _get_extension()
    result = await extension._run_code(
        compile_or_fail("print(crawler.spidercls.name)"), 5
    )
    assert result["output"] == f"{extension.crawler.spidercls.name}\n"


@coroutine_test
async def test_runtime_error_keeps_partial_output() -> None:
    extension = _get_extension()
    result = await extension._run_code(
        compile_or_fail("print('before')\nraise ValueError('boom')"), 5
    )
    assert result["status"] == "error"
    assert result["traceback"] is not None
    assert "ValueError: boom" in result["traceback"]
    assert "before" in result["output"]


@coroutine_test
async def test_timeout() -> None:
    extension = _get_extension()
    result = await extension._run_code(
        compile_or_fail("import asyncio\nawait asyncio.sleep(10)"), 0.05
    )
    assert result["status"] == "timeout"
    assert result["traceback"] is None


@coroutine_test
async def test_stash_persists_across_calls() -> None:
    extension = _get_extension()
    await extension._run_code(compile_or_fail("stash['x'] = 42"), 5)
    result = await extension._run_code(compile_or_fail("print(stash['x'])"), 5)
    assert result["output"] == "42\n"
    assert extension._stash == {"x": 42}


@coroutine_test
async def test_namespace_is_fresh_each_call() -> None:
    extension = _get_extension()
    await extension._run_code(compile_or_fail("y = 99"), 5)
    result = await extension._run_code(compile_or_fail("print('y' in dir())"), 5)
    assert result["status"] == "ok"
    assert result["output"] == "False\n"


@coroutine_test
async def test_concurrent_calls_are_not_serialized() -> None:
    # A slow, awaiting call must not block a quick one: the quick call finishes
    # first even though it was started second, and both share `stash`.
    extension = _get_extension()
    extension._stash["order"] = []
    slow = extension._run_code(
        compile_or_fail(
            "import asyncio\nawait asyncio.sleep(0.3)\nstash['order'].append('slow')"
        ),
        5,
    )
    quick = extension._run_code(compile_or_fail("stash['order'].append('quick')"), 5)
    await asyncio.gather(slow, quick)
    assert extension._stash["order"] == ["quick", "slow"]


@coroutine_test
async def test_output_truncation() -> None:
    extension = _get_extension({"REMOTE_CONTROL_OUTPUT_MAX_BYTES": 10})
    result = await extension._run_code(compile_or_fail("print('x' * 100)"), 5)
    assert result["output_truncated"] is True
    assert "truncated" in result["output"]


@coroutine_test
async def test_traceback_truncation() -> None:
    extension = _get_extension({"REMOTE_CONTROL_TRACEBACK_MAX_BYTES": 10})
    result = await extension._run_code(
        compile_or_fail("raise ValueError('boom' * 100)"), 5
    )
    assert result["traceback_truncated"] is True
    assert result["traceback"] is not None
    assert "truncated" in result["traceback"]


@pytest.mark.parametrize("source", ["def (:", "print('a')\x00"])
def test_compile_error(source: str) -> None:
    rendered = _compile(source)
    assert isinstance(rendered, str)
    # The docs only say "This function raises SyntaxError or ValueError if the
    # compiled source is invalid." and it depends on the Python version.
    assert "SyntaxError" in rendered or "ValueError" in rendered


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (None, 30.0),
        (50, 50.0),
        (1000, 600.0),
        (0, 30.0),
        (-1, 30.0),
        (float("nan"), 30.0),
        (float("inf"), 600.0),
    ],
)
def test_effective_timeout(requested: float | None, expected: float) -> None:
    assert _effective_timeout(requested, 30.0, 600.0) == expected


def test_effective_timeout_caps_the_default_too() -> None:
    assert _effective_timeout(None, 1000.0, 600.0) == 600.0


def test_cap() -> None:
    assert _cap("hello", 10) == ("hello", False)
    capped, truncated = _cap("x" * 2048, 10)
    assert truncated is True
    assert capped.startswith("x" * 10)
    assert capped.endswith("…[truncated, +2KB]")  # 2038 bytes dropped


def test_cap_does_not_split_a_character() -> None:
    # "ä" takes two bytes, so a 5 byte cap must drop the third one entirely.
    capped, truncated = _cap("ä" * 10, 5)
    assert truncated is True
    assert capped.startswith("ää")
    assert "truncated" in capped


def test_disabled_by_setting() -> None:
    with pytest.raises(NotConfigured):
        _get_extension({"REMOTE_CONTROL_ENABLED": False})


@pytest.mark.parametrize(
    "settings",
    [
        {"REMOTE_CONTROL_TIMEOUT_DEFAULT": 0},
        {"REMOTE_CONTROL_TIMEOUT_DEFAULT": -1},
        {"REMOTE_CONTROL_TIMEOUT_MAX": 0},
        {"REMOTE_CONTROL_TIMEOUT_MAX": -1},
    ],
)
def test_non_positive_timeouts_rejected(settings: dict[str, Any]) -> None:
    with pytest.raises(NotConfigured):
        _get_extension(settings)


def test_default_timeouts() -> None:
    extension = _get_extension()
    assert extension._default_timeout == default_settings.REMOTE_CONTROL_TIMEOUT_DEFAULT
    assert extension._max_timeout == default_settings.REMOTE_CONTROL_TIMEOUT_MAX


def test_settings_are_applied() -> None:
    extension = _get_extension(
        {
            "REMOTE_CONTROL_TIMEOUT_DEFAULT": 5.0,
            "REMOTE_CONTROL_TIMEOUT_MAX": 999.0,
            "REMOTE_CONTROL_OUTPUT_MAX_BYTES": 11,
            "REMOTE_CONTROL_TRACEBACK_MAX_BYTES": 22,
        }
    )
    assert extension._default_timeout == 5.0
    assert extension._max_timeout == 999.0
    assert extension._output_max_bytes == 11
    assert extension._traceback_max_bytes == 22


@coroutine_test
async def test_ok_envelope(tmp_path: Path) -> None:
    async with _started_extension(tmp_path) as extension:
        status, envelope = await _post(
            extension, json={"code": "print(6 * 7)"}, headers=_auth(extension)
        )
    assert status == 200
    assert envelope["status"] == "ok"
    assert envelope["output"] == "42\n"


@coroutine_test
async def test_compile_error_envelope(tmp_path: Path) -> None:
    async with _started_extension(tmp_path) as extension:
        status, envelope = await _post(
            extension, json={"code": "def (:"}, headers=_auth(extension)
        )
    assert status == 200
    assert envelope["status"] == "compile_error"
    assert "SyntaxError" in envelope["traceback"]


@coroutine_test
async def test_runtime_error_envelope(tmp_path: Path) -> None:
    async with _started_extension(tmp_path) as extension:
        status, envelope = await _post(
            extension,
            json={"code": "raise ValueError('boom')"},
            headers=_auth(extension),
        )
    assert status == 200
    assert envelope["status"] == "error"
    assert "boom" in envelope["traceback"]


@coroutine_test
async def test_live_crawler_is_reachable(tmp_path: Path) -> None:
    # Using the real token covers the auth path end to end as well.
    async with _started_extension(tmp_path) as extension:
        status, envelope = await _post(
            extension,
            json={"code": "print(type(crawler).__name__)"},
            headers=_auth(extension),
        )
    assert status == 200
    assert envelope["status"] == "ok"
    assert "Crawler" in envelope["output"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer nope"},
        {"Authorization": "Bearer ünicode"},
        {"Authorization": "Basic nope"},
    ],
)
@coroutine_test
async def test_unauthorized(tmp_path: Path, headers: dict[str, str]) -> None:
    async with _started_extension(tmp_path) as extension:
        status, body = await _post(
            extension, json={"code": "print(1)"}, headers=headers
        )
    assert status == 401
    assert body == {"error": "unauthorized"}


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"data": "not json"}, "invalid JSON body"),
        ({"json": {"nope": 1}}, "Missing or invalid 'code' value"),
        ({"json": {"code": 1}}, "Missing or invalid 'code' value"),
        ({"json": [1, 2]}, "Missing or invalid 'code' value"),
    ],
)
@coroutine_test
async def test_bad_requests(tmp_path: Path, kwargs: dict[str, Any], error: str) -> None:
    async with _started_extension(tmp_path) as extension:
        status, body = await _post(extension, headers=_auth(extension), **kwargs)
    assert status == 400
    assert body == {"error": error}


@pytest.mark.parametrize("timeout_sec", ["abc", [1]])
@coroutine_test
async def test_bad_timeout_type(tmp_path: Path, timeout_sec: Any) -> None:
    async with _started_extension(tmp_path) as extension:
        status, body = await _post(
            extension,
            json={"code": "print(1)", "timeout_sec": timeout_sec},
            headers=_auth(extension),
        )
    assert status == 400
    assert body == {"error": "Invalid 'timeout_sec' value"}


@pytest.mark.parametrize("timeout_sec", [None, 0, -1])
@coroutine_test
async def test_unset_timeout_is_accepted(tmp_path: Path, timeout_sec: Any) -> None:
    async with _started_extension(tmp_path) as extension:
        status, envelope = await _post(
            extension,
            json={"code": "print(1)", "timeout_sec": timeout_sec},
            headers=_auth(extension),
        )
    assert status == 200
    assert envelope["status"] == "ok"


@coroutine_test
async def test_job_file_written_and_removed(tmp_path: Path) -> None:
    async with _started_extension(tmp_path) as extension:
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["token"] == extension._auth_token
        assert record["spider"] == extension.crawler.spidercls.name
    assert list(tmp_path.glob("*.json")) == []


@coroutine_test
async def test_token_is_never_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        async with _started_extension(tmp_path) as extension:
            token = extension._auth_token
    assert token
    assert token not in caplog.text


@coroutine_test
async def test_stop_without_start() -> None:
    extension = _get_extension()
    await extension.stop()
    assert extension._runner is None


@coroutine_test
async def test_stop_is_idempotent(tmp_path: Path) -> None:
    async with _started_extension(tmp_path) as extension:
        pass
    await extension.stop()
    assert extension._runner is None
    assert list(tmp_path.glob("*.json")) == []


@coroutine_test
async def test_start_failure_disables_the_extension(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A file where the job file directory is expected makes writing the job
    # file fail, after the HTTP server has already started.
    jobs_dir = tmp_path / "jobs"
    jobs_dir.write_text("", encoding="utf-8")
    extension = _get_extension({"REMOTE_CONTROL_JOBS_DIR": str(jobs_dir)})
    await extension.start()
    assert "Remote control HTTP server failed to start" in caplog.text
    assert "FileExistsError" in caplog.text
    assert extension._runner is None
    assert extension._auth_token is None
    assert extension._job_file_path is None


@coroutine_test
async def test_stop_logs_a_cleanup_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension = _get_extension({"REMOTE_CONTROL_JOBS_DIR": str(tmp_path)})
    await extension.start()
    runner = extension._runner
    assert runner is not None
    extension._stash["x"] = 42
    real_cleanup = web.AppRunner.cleanup

    async def raise_runtime_error(self: web.AppRunner) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(web.AppRunner, "cleanup", raise_runtime_error)
    await extension.stop()
    assert "Error stopping the remote control HTTP server" in caplog.text
    assert "RuntimeError: boom" in caplog.text
    assert extension._runner is None
    assert extension._auth_token is None
    assert extension._stash == {}
    assert list(tmp_path.glob("*.json")) == []
    await real_cleanup(runner)


@coroutine_test
async def test_stop_ignores_a_failure_to_remove_the_job_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("cannot remove")

    extension = _get_extension({"REMOTE_CONTROL_JOBS_DIR": str(tmp_path)})
    await extension.start()
    monkeypatch.setattr(Path, "unlink", raise_os_error)
    await extension.stop()
    assert extension._runner is None
    assert extension._job_file_path is None
    assert len(list(tmp_path.glob("*.json"))) == 1  # could not be removed


@coroutine_test
async def test_stop_does_not_wait_for_a_running_snippet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(remote_control, "STOP_TIMEOUT", 0.1)
    extension = _get_extension({"REMOTE_CONTROL_JOBS_DIR": str(tmp_path)})
    extension.crawler.spider = extension.crawler.spidercls()
    await extension.start()
    request = asyncio.ensure_future(
        _post(
            extension,
            json={"code": "import asyncio\nawait asyncio.sleep(30)"},
            headers=_auth(extension),
        )
    )
    await asyncio.sleep(0.1)  # let the request reach the handler
    await asyncio.wait_for(extension.stop(), 10)
    assert extension._runner is None
    request.cancel()
    with contextlib.suppress(asyncio.CancelledError, aiohttp.ClientError):
        await request
