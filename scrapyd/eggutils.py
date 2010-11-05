from __future__ import with_statement

import os, sys, shutil, pkg_resources
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile

def get_spider_list_from_eggfile(eggfile, project, eggrunner='scrapyd.eggrunner'):
    with NamedTemporaryFile(suffix='.egg') as f:
        shutil.copyfileobj(eggfile, f)
        f.flush()
        eggfile.seek(0)
        pargs = [sys.executable, '-m', eggrunner, 'list']
        env = os.environ.copy()
        env['SCRAPY_PROJECT'] = project
        env['SCRAPY_EGGFILE'] = f.name
        proc = Popen(pargs, stdout=PIPE, stderr=PIPE, env=env)
        out, err = proc.communicate()
        if proc.returncode:
            msg = err or out or 'unknown error'
            raise RuntimeError(msg.splitlines()[-1])
        return out.splitlines()

def activate_egg(eggpath):
    """Activate a Scrapy egg file. This is meant to be used from egg runners
    to activate a Scrapy egg file. Don't use it from other code as it may
    leave unwanted side effects.
    """
    try:
        d = pkg_resources.find_distributions(eggpath).next()
    except StopIteration:
        raise ValueError("Unknown or corrupt egg")
    d.activate()
    settings_module = d.get_entry_info('scrapy', 'settings').module_name
    os.environ['SCRAPY_SETTINGS_MODULE'] = settings_module
