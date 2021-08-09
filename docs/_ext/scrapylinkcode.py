"""Specialization of the linkcode Sphinx extension for Scrapy.

It defines and injects the ``resolve`` function so that we can keep complex
code out of the ``conf.py`` file.
"""

import sys
from inspect import getsourcefile, getsourcelines, unwrap
from os import environ
from os.path import relpath, dirname
from typing import Any, Dict

import sphinx
from sphinx.application import Sphinx
from sphinx.ext.linkcode import doctree_read

import scrapy


def _github_branch():
    rtd_version = environ.get('READTHEDOCS_VERSION')
    is_a_local_build = not rtd_version

    if is_a_local_build or rtd_version == 'master':
        return 'master'

    return scrapy.__version__


# Based on numpy’s:
# https://github.com/numpy/numpy/blob/dedc4178fc334329de9872ab42df870d2ac7a270/doc/source/conf.py#L313
def resolve(domain, info):
    modname = info['module']
    fullname = info['fullname']

    obj = sys.modules.get(modname)
    for part in fullname.split('.'):
        try:
            obj = getattr(obj, part)
        except AttributeError:
            return None

    try:
        file_path = getsourcefile(obj)
    except TypeError:
        return None

    file_path = relpath(file_path,
                        start=dirname(scrapy.__file__))
    source, lineno = getsourcelines(obj)
    linespec = "#L%d-L%d" % (lineno, lineno + len(source) - 1)
    branch = _github_branch()

    file_path = file_path.replace('\\', '/')
    return "https://github.com/scrapy/scrapy/blob/%s/scrapy/%s%s" % (
        branch, file_path, linespec)


def setup(app: Sphinx) -> Dict[str, Any]:
    app.connect('doctree-read', doctree_read)
    app.add_config_value('linkcode_resolve', lambda v: resolve, '')
    return {'version': sphinx.__display_version__, 'parallel_read_safe': True}
