from __future__ import with_statement

import os, sys, shutil, pkg_resources
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile, mkdtemp

def get_spider_list_from_eggfile(eggfile, project):
    # FIXME: we use a temporary directory here to avoid permissions problems
    # when running as system service, as "scrapy list" command tries to write
    # the scrapy.db sqlite database in current directory
    tmpdir = mkdtemp()
    try:
        with NamedTemporaryFile(suffix='.egg', dir=tmpdir) as f:
            shutil.copyfileobj(eggfile, f)
            f.flush()
            eggfile.seek(0)
            pargs = [sys.executable, '-m', 'scrapyd.eggrunner', 'list']
            env = os.environ.copy()
            env['SCRAPY_PROJECT'] = project
            env['SCRAPY_EGGFILE'] = f.name
            env.pop('SCRAPY_SETTINGS_DISABLED', None)
            proc = Popen(pargs, stdout=PIPE, cwd=tmpdir, env=env)
            out = proc.communicate()[0]
            return out.splitlines()
    finally:
        shutil.rmtree(tmpdir)

def activate_egg(eggpath):
    """Activate a Scrapy egg file. This is meant to be used from egg runners
    to activate a Scrapy egg file. Don't use it from other code as it may
    leave unwanted side effects.
    """
    d = pkg_resources.find_distributions(eggpath).next()
    d.activate()
    settings_module = d.get_entry_info('scrapy', 'settings').module_name
    os.environ['SCRAPY_SETTINGS_MODULE'] = settings_module
