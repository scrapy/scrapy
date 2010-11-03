from __future__ import with_statement

import sys
import os
import glob
import tempfile
import shutil
import time
import urllib2
import netrc
from urlparse import urlparse, urljoin
from subprocess import Popen, PIPE, check_call

from scrapy.command import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.py26 import json
from scrapy.utils.multipart import encode_multipart
from scrapy.utils.http import basic_auth_header
from scrapy.utils.conf import get_config, closest_scrapy_cfg

_DEFAULT_TARGETS = {
    'scrapyd': {
        'url': 'http://localhost:6800/',
    },
}

_SETUP_PY_TEMPLATE = \
"""# Automatically created by: scrapy deploy

from setuptools import setup, find_packages

setup(
    name         = 'project',
    version      = '1.0',
    packages     = find_packages(),
    entry_points = {'scrapy': ['settings = %(settings)s']},
)
"""

class Command(ScrapyCommand):

    requires_project = True

    def syntax(self):
        return "[options] [ <target:project> | -l <target> | -L ]"

    def short_desc(self):
        return "Deploy project in Scrapyd server"

    def long_desc(self):
        return "Deploy the current project into the given Scrapyd server " \
            "(aka target) and project."

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-v", "--version",
            help="the version to deploy. Defaults to current timestamp")
        parser.add_option("-L", "--list-targets", action="store_true", \
            help="list available targets")
        parser.add_option("-l", "--list-projects", metavar="TARGET", \
            help="list available projects on TARGET")
        parser.add_option("--egg", metavar="FILE",
            help="use the given egg, instead of building it")

    def run(self, args, opts):
        try:
            import setuptools
        except ImportError:
            raise UsageError("setuptools not installed")
        if opts.list_targets:
            for name, target in _get_targets().items():
                print "%-20s %s" % (name, target['url'])
            return
        if opts.list_projects:
            target = _get_target(opts.list_projects)
            req = urllib2.Request(_url(target, 'listprojects.json'))
            _add_auth_header(req, target)
            f = urllib2.urlopen(req)
            projects = json.loads(f.read())['projects']
            print os.linesep.join(projects)
            return
        target, project = _get_target_project(args)
        version = _get_version(opts)
        tmpdir = None
        if opts.egg:
            egg = open(opts.egg, 'rb')
        else:
            _log("Bulding egg of %s-%s" % (project, version))
            egg, tmpdir = _build_egg()
        _upload_egg(target, egg, project, version)
        egg.close()
        if tmpdir:
            shutil.rmtree(tmpdir)

def _log(message):
    sys.stderr.write("%s\n" % message)

def _get_target_project(args):
    if len(args) >= 1 and ':' in args[0]:
        target_name, project = args[0].split(':', 1)
    elif len(args) < 1:
        target_name = _get_option('deploy', 'target')
        project = _get_option('deploy', 'project')
        if not target_name or not project:
            raise UsageError("<target:project> not given and defaults not found")
    else:
        raise UsageError("%r is not a <target:project>" % args[0])
    target = _get_target(target_name)
    return target, project

def _get_option(section, option, default=None):
    cfg = get_config()
    return cfg.get(section, option) if cfg.has_option(section, option) \
        else default

def _get_targets():
    cfg = get_config()
    targets = _DEFAULT_TARGETS.copy()
    for x in cfg.sections():
        if x.startswith('deploy_'):
            targets[x[7:]] = dict(cfg.items(x))
    return targets

def _get_target(name):
    try:
        return _get_targets()[name]
    except KeyError:
        raise UsageError("Unknown target: %s" % name)

def _url(target, action):
    return urljoin(target['url'], action)

def _get_version(opts):
    if opts.version == 'HG':
        p = Popen(['hg', 'tip', '--template', '{rev}'], stdout=PIPE)
        return 'r%s' % p.communicate()[0]
    elif opts.version:
        return opts.version
    else:
        return str(int(time.time()))

def _upload_egg(target, eggfile, project, version):
    data = {
        'project': project,
        'version': version,
        'egg': ('project.egg', eggfile.read()),
    }
    body, boundary = encode_multipart(data)
    url = _url(target, 'addversion.json')
    headers = {
        'Content-Type': 'multipart/form-data; boundary=%s' % boundary,
        'Content-Length': str(len(body)),
    }
    req = urllib2.Request(url, body, headers)
    _add_auth_header(req, target)
    _log("Deploying %s-%s to %s" % (project, version, url))
    _http_post(req)

def _add_auth_header(request, target):
    if 'username' in target:
        u, p = target.get('username'), target.get('password', '')
        request.add_header('Authorization', basic_auth_header(u, p))
    else: # try netrc
        try:
            host = urlparse(target['url']).hostname
            a = netrc.netrc().authenticators(host)
            request.add_header('Authorization', basic_auth_header(a[0], a[2]))
        except (netrc.NetrcParseError, TypeError):
            pass

def _http_post(request):
    try:
        f = urllib2.urlopen(request)
        _log("Server response (%s):" % f.code)
        print f.read()
    except urllib2.HTTPError, e:
        _log("Deploy failed (%s):" % e.code)
        print e.read()
    except urllib2.URLError, e:
        _log("Deploy failed: %s" % e)

def _build_egg():
    closest = closest_scrapy_cfg()
    os.chdir(os.path.dirname(closest))
    if not os.path.exists('setup.py'):
        settings = get_config().get('settings', 'default')
        _create_default_setup_py(settings=settings)
    d = tempfile.mkdtemp()
    f = tempfile.TemporaryFile(dir=d)
    check_call([sys.executable, 'setup.py', 'bdist_egg', '-d', d], stdout=f)
    egg = glob.glob(os.path.join(d, '*.egg'))[0]
    return open(egg, 'rb'), d

def _create_default_setup_py(**kwargs):
    with open('setup.py', 'w') as f:
        f.write(_SETUP_PY_TEMPLATE % kwargs)
