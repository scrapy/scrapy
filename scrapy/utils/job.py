from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy.settings import BaseSettings


def job_dir(settings: BaseSettings) -> str | None:
    """Return the job directory path from settings, creating it if needed.

    Returns the path specified in the JOBDIR setting. If the directory doesn't
    exist, it will be created (including any necessary parent directories).

    Args:
        settings: The Scrapy settings object

    Returns:
        str | None: The job directory path if JOBDIR is set and non-empty,
                    None otherwise
    """
    path: str | None = settings["JOBDIR"]
    if not path:
        return None
    if not Path(path).exists():
        Path(path).mkdir(parents=True)
    return path
