def job_dir(settings):
    path = settings['JOBDIR']
    path.mkdir(parents=True, exist_ok=True)
    return path
