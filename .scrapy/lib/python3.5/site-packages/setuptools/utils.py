import os
import os.path


def cs_path_exists(fspath):
    if not os.path.exists(fspath): 
        return False
    # make absolute so we always have a directory
    abspath = os.path.abspath(fspath)
    directory, filename = os.path.split(abspath)
    return filename in os.listdir(directory)