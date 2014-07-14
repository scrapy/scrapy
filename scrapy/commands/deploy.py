from __future__ import print_function
import sys
import os
import glob
import tempfile
import shutil
import time
import urllib2
import netrc
import json
from six.moves.urllib.parse import urlparse, urljoin
from subprocess import Popen, PIPE, check_call

from w3lib.form import encode_multipart

from scrapy.command import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.http import basic_auth_header
from scrapy.utils.python import retry_on_eintr
from scrapy.utils.conf import get_config, closest_scrapy_cfg

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
        return "[options] [ [target] | -l | -L <target> ]"

    def short_desc(self):
        return "Deploy project in Scrapyd target"

    def long_desc(self):
        return "Deploy the current project into the given Scrapyd server " \
            "(known as target)"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-p", "--project",
            help="the project name in the target")
        parser.add_option("-v", "--version",
            help="the version to deploy. Defaults to current timestamp")
        parser.add_option("-l", "--list-targets", action="store_true", \
            help="list available targets")
        parser.add_option("-d", "--debug", action="store_true",
            help="debug mode (do not remove build dir)")
        parser.add_option("-L", "--list-projects", metavar="TARGET", \
            help="list available projects on TARGET")
        parser.add_option("--egg", metavar="FILE",
            help="use the given egg, instead of building it")
        parser.add_option("--build-egg", metavar="FILE",
            help="only build the egg, don't deploy it")

    def run(self, args, opts):
        try:
            import setuptools
        except ImportError:
            raise UsageError("setuptools not installed")

        urllib2.install_opener(urllib2.build_opener(HTTPRedirectHandler))

        if opts.list_targets:
            for name, target in _get_targets().items():
                print("%-20s %s" % (name, target['url']))
            return

        if opts.list_projects:
            target = _get_target(opts.list_projects)
            req = urllib2.Request(_url(target, 'listprojects.json'))
            _add_auth_header(req, target)
            f = urllib2.urlopen(req)
            projects = json.loads(f.read())['projects']
            print(os.linesep.join(projects))
            return

        tmpdir = None

        if opts.build_egg: # build egg only
            egg, tmpdir = _build_egg()
            _log("Writing egg to %s" % opts.build_egg)
            shutil.copyfile(egg, opts.build_egg)
        else: # buld egg and deploy
            target_name = _get_target_name(args)
            target = _get_target(target_name)
            project = _get_project(target, opts)
            version = _get_version(target, opts)
            if opts.egg:
                _log("Using egg: %s" % opts.egg)
                egg = opts.egg
            else:
                _log("Packing version %s" % version)
                egg, tmpdir = _build_egg()
            if not _upload_egg(target, egg, project, version):
                self.exitcode = 1

        if tmpdir:
            if opts.debug:
                _log("Output dir not removed: %s" % tmpdir)
            else:
                shutil.rmtree(tmpdir)

def _log(message):
    sys.stderr.write(message + os.linesep)

def _get_target_name(args):
    if len(args) > 1:
        raise UsageError("Too many arguments: %s" % ' '.join(args))
    elif args:
        return args[0]
    elif len(args) < 1:
        return 'default'

def _get_project(target, opts):
    project = opts.project or target.get('project')
    if not project:
        raise UsageError("Missing project")
    return project

def _get_option(section, option, default=None):
    cfg = get_config()
    return cfg.get(section, option) if cfg.has_option(section, option) \
        else default

def _get_targets():
    cfg = get_config()
    baset = dict(cfg.items('deploy')) if cfg.has_section('deploy') else {}
    targets = {}
    if 'url' in baset:
        targets['default'] = baset
    for x in cfg.sections():
        if x.startswith('deploy:'):
            t = baset.copy()
            t.update(cfg.items(x))
            targets[x[7:]] = t
    return targets

def _get_target(name):
    try:
        return _get_targets()[name]
    except KeyError:
        raise UsageError("Unknown target: %s" % name)

def _url(target, action):
    return urljoin(target['url'], action)

def _get_version(target, opts):
    version = opts.version or target.get('version')
    if version == 'HG':
        p = Popen(['hg', 'tip', '--template', '{rev}'], stdout=PIPE)
        d = 'r%s' % p.communicate()[0]
        p = Popen(['hg', 'branch'], stdout=PIPE)
        b = p.communicate()[0].strip('\n')
        return '%s-%s' % (d, b)
    elif version == 'GIT':
        p = Popen(['git', 'describe', '--always'], stdout=PIPE)
        d = p.communicate()[0].strip('\n')
        p = Popen(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], stdout=PIPE)
        b = p.communicate()[0].strip('\n')
        return '%s-%s' % (d, b)
    elif version:
        return version
    else:
        return str(int(time.time()))

def _upload_egg(target, eggpath, project, version):
    with open(eggpath, 'rb') as f:
        eggdata = f.read()
    data = {
        'project': project,
        'version': version,
        'egg': ('project.egg', eggdata),
    }
    body, boundary = encode_multipart(data)
    url = _url(target, 'addversion.json')
    headers = {
        'Content-Type': 'multipart/form-data; boundary=%s' % boundary,
        'Content-Length': str(len(body)),
    }
    req = urllib2.Request(url, body, headers)
    _add_auth_header(req, target)
    _log('Deploying to project "%s" in %s' % (project, url))
    return _http_post(req)

def _add_auth_header(request, target):
    if 'username' in target:
        u, p = target.get('username'), target.get('password', '')
        request.add_header('Authorization', basic_auth_header(u, p))
    else: # try netrc
        try:
            host = urlparse(target['url']).hostname
            a = netrc.netrc().authenticators(host)
            request.add_header('Authorization', basic_auth_header(a[0], a[2]))
        except (netrc.NetrcParseError, IOError, TypeError):
            pass

def _http_post(request):
    try:
        f = urllib2.urlopen(request)
        _log("Server response (%s):" % f.code)
        print(f.read())
        return True
    except urllib2.HTTPError as e:
        _log("Deploy failed (%s):" % e.code)
        print(e.read())
    except urllib2.URLError as e:
        _log("Deploy failed: %s" % e)

def _build_egg():
    closest = closest_scrapy_cfg()
    os.chdir(os.path.dirname(closest))
    if not os.path.exists('setup.py'):
        settings = get_config().get('settings', 'default')
        _create_default_setup_py(settings=settings)
    d = tempfile.mkdtemp(prefix="scrapydeploy-")
    o = open(os.path.join(d, "stdout"), "wb")
    e = open(os.path.join(d, "stderr"), "wb")
    retry_on_eintr(check_call, [sys.executable, 'setup.py', 'clean', '-a', 'bdist_egg', '-d', d], stdout=o, stderr=e)
    o.close()
    e.close()
    egg = glob.glob(os.path.join(d, '*.egg'))[0]
    return egg, d

def _create_default_setup_py(**kwargs):
    with open('setup.py', 'w') as f:
        f.write(_SETUP_PY_TEMPLATE % kwargs)


class HTTPRedirectHandler(urllib2.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = newurl.replace(' ', '%20')
        if code in (301, 307):
            return urllib2.Request(newurl,
                                   data=req.get_data(),
                                   headers=req.headers,
                                   origin_req_host=req.get_origin_req_host(),
                                   unverifiable=True)
        elif code in (302, 303):
            newheaders = dict((k, v) for k, v in req.headers.items()
                              if k.lower() not in ("content-length", "content-type"))
            return urllib2.Request(newurl,
                                   headers=newheaders,
                                   origin_req_host=req.get_origin_req_host(),
                                   unverifiable=True)
        else:
            raise urllib2.HTTPError(req.get_full_url(), code, msg, headers, fp)
