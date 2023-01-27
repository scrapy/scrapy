from pathlib import Path
from typing import Optional

from scrapy.settings import BaseSettings


def job_dir(settings: BaseSettings) -> Optional[str]:
    path = settings["JOBDIR"]
    if path and not Path(path).exists():
        Path(path).mkdir(parents=True)
    return path
