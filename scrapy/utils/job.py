import os

def job_dir(settings):
    path = settings['JOBDIR']
    if path and not os.path.exists(path):
        os.makedirs(path)
    return path
