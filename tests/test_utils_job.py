from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.settings import Settings
from scrapy.utils.job import job_dir

if TYPE_CHECKING:
    from pathlib import Path


def test_no_jobdir() -> None:
    assert job_dir(Settings()) is None
    assert job_dir(Settings({"JOBDIR": ""})) is None


def test_existing_jobdir(tmp_path: Path) -> None:
    assert job_dir(Settings({"JOBDIR": str(tmp_path)})) == str(tmp_path)


def test_missing_jobdir(tmp_path: Path) -> None:
    jobdir = tmp_path / "missing" / "jobdir"
    assert job_dir(Settings({"JOBDIR": str(jobdir)})) == str(jobdir)
    assert jobdir.is_dir()
