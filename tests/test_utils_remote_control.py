from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from scrapy.settings import Settings
from scrapy.utils._remote_control import (
    JOB_FILE_VERSION,
    job_files_dir,
    new_job_file_name,
    write_job_file,
)


def _write_job_file(path: Path) -> None:
    write_job_file(
        path,
        spider="dummy",
        project="testbot",
        scrapy_version="2.17.0",
        port=12345,
        token="secret",
    )


def test_write_job_file(tmp_path: Path) -> None:
    path = tmp_path / "jobs" / f"{os.getpid()}-abc.json"
    _write_job_file(path)
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["version"] == JOB_FILE_VERSION
    assert record["pid"] == os.getpid()
    assert record["port"] == 12345
    assert record["token"] == "secret"
    assert record["spider"] == "dummy"
    assert record["project"] == "testbot"
    assert record["scrapy_version"] == "2.17.0"
    assert isinstance(record["start_time"], float)


def test_write_job_file_leaves_no_temporary_file(tmp_path: Path) -> None:
    name = f"{os.getpid()}-abc.json"
    _write_job_file(tmp_path / name)
    assert [path.name for path in tmp_path.iterdir()] == [name]


def test_new_job_file_name() -> None:
    name = new_job_file_name()
    assert name.endswith(".json")
    pid, _, rest = name.removeprefix(".").partition("-")
    assert rest
    assert pid.isdigit()
    assert int(pid) == os.getpid()


def test_write_job_file_refuses_an_existing_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / new_job_file_name()
    planted = path.with_name(f".{path.name}.tmp")
    planted.write_text("", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _write_job_file(path)
    assert not path.exists()
    assert planted.read_text(encoding="utf-8") == ""  # left untouched


def test_write_job_file_removes_the_temporary_file_after_a_failure(
    tmp_path: Path,
) -> None:
    # A directory in the way makes the final rename fail, after the temporary
    # file has already been created.
    path = tmp_path / new_job_file_name()
    path.mkdir()
    # the specific exception differs between platforms
    with pytest.raises(OSError):  # noqa: PT011
        _write_job_file(path)
    assert list(tmp_path.iterdir()) == [path]


def test_write_job_file_ignores_a_failure_to_remove_the_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_runtime_error(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    def raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("cannot remove")

    monkeypatch.setattr(json, "dump", raise_runtime_error)
    monkeypatch.setattr(Path, "unlink", raise_os_error)
    path = tmp_path / new_job_file_name()
    # the original error wins over the cleanup one
    with pytest.raises(RuntimeError, match="boom"):
        _write_job_file(path)
    assert not path.exists()
    assert path.with_name(f".{path.name}.tmp").exists()  # could not be removed


def test_jobs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        job_files_dir(Settings({"REMOTE_CONTROL_JOBS_DIR": str(tmp_path)})) == tmp_path
    )
    # platformdirs does not determine the user state folder from environment
    # variables on every platform, hence the patching.
    monkeypatch.setattr(
        "scrapy.utils._remote_control.user_state_dir",
        lambda *args, **kwargs: str(tmp_path),
    )
    assert job_files_dir(Settings()) == tmp_path / "job_files"
