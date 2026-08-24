from __future__ import annotations

import contextlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict

from platformdirs import user_state_dir

if TYPE_CHECKING:
    # typing.NotRequired requires Python 3.11
    from typing_extensions import NotRequired

    from scrapy.settings import BaseSettings

logger = logging.getLogger(__name__)

# On-disk format of the job files
JOB_FILE_VERSION = 1


class StatusResult(TypedDict):
    """The result of a ``/status`` call."""

    pid: int
    spider: str
    project: str | None
    scrapy_version: str
    start_time: float | None


class ExecuteResult(TypedDict):
    """The result of an ``/execute`` call."""

    status: Literal["ok", "compile_error", "error", "timeout"]
    output: str
    traceback: str | None
    elapsed_sec: float
    output_truncated: NotRequired[bool]
    traceback_truncated: NotRequired[bool]


def job_files_dir(settings: BaseSettings) -> Path:
    """Return the directory used for job files."""
    setting = settings.get("REMOTE_CONTROL_JOBS_DIR")
    if setting:
        return Path(setting)
    return Path(user_state_dir("scrapy", appauthor=False), "job_files")


def new_job_file_name() -> str:
    """Return the name of a new job file."""
    return f"{os.getpid()}-{uuid.uuid4().hex}.json"


def write_job_file(
    path: Path,
    *,
    spider: str,
    project: str | None,
    scrapy_version: str,
    port: int,
    token: str,
) -> None:
    """Write the job file that makes a crawl discoverable.

    The file content is sensitive information as it includes the auth token.
    """
    data = {
        "version": JOB_FILE_VERSION,
        "pid": os.getpid(),
        "port": port,
        "token": token,
        "spider": spider,
        "project": project,
        "scrapy_version": scrapy_version,
        "start_time": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    # Atomic write so the file is never world-readable mid-write.
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        tmp.chmod(0o600)
        tmp.replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
