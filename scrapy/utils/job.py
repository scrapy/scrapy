from pathlib import Path


def job_dir(settings):
    path = settings['JOBDIR']
    if path:
        Path(path).mkdir(parents=True, exist_ok=True)
    return path
