from pathlib import Path
from typing import Optional

from scrapy.settings import BaseSettings


def job_dir(settings: BaseSettings) -> Optional[str]:
    path: Optional[str] = settings["JOBDIR"]
    if not path:
        return None
    if not Path(path).exists():
        Path(path).mkdir(parents=True)
    return path
