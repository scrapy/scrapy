import os
from typing import Optional

from scrapy.settings import BaseSettings


def job_dir(settings: BaseSettings) -> Optional[str]:
    path = settings['JOBDIR']
    if path and not os.path.exists(path):
        os.makedirs(path)
    return path
