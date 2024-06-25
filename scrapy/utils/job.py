from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from scrapy.settings import BaseSettings


def job_dir(settings: BaseSettings) -> Optional[str]:
    path: Optional[str] = settings["JOBDIR"]
    if not path:
        return None
    if not Path(path).exists():
        Path(path).mkdir(parents=True)
    return path
