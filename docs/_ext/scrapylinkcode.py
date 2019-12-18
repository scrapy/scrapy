"""Specialization of the linkcode Sphinx extension for Scrapy.

It defines and injects the ``resolve`` function so that we can keep complex
code out of the ``conf.py`` file.
"""

import inspect
import sys
from os import environ
from os.path import relpath, dirname
from typing import Any, Dict

import sphinx
from sphinx.application import Sphinx
from sphinx.ext.linkcode import doctree_read

import scrapy


# Based on numpy’s:
# https://github.com/numpy/numpy/blob/dedc4178fc334329de9872ab42df870d2ac7a270/doc/source/conf.py#L313
def resolve(domain, info):
    if domain != 'py':
        return None

    modname = info['module']
    fullname = info['fullname']

    submod = sys.modules.get(modname)
    if submod is None:
        return None

    obj = submod
    for part in fullname.split('.'):
        try:
            obj = getattr(obj, part)
        except Exception:
            return None

    # strip decorators, which would resolve to the source of the decorator
    # possibly an upstream bug in getsourcefile, bpo-1764286
    try:
        unwrap = inspect.unwrap
    except AttributeError:
        pass
    else:
        obj = unwrap(obj)

    try:
        fn = inspect.getsourcefile(obj)
    except Exception:
        fn = None
    if not fn:
        return None

    try:
        source, lineno = inspect.getsourcelines(obj)
    except Exception:
        lineno = None

    if lineno:
        linespec = "#L%d-L%d" % (lineno, lineno + len(source) - 1)
    else:
        linespec = ""

    fn = relpath(fn, start=dirname(scrapy.__file__))

    rtd_version = environ.get('READTHEDOCS_VERSION')
    is_a_local_build = not rtd_version
    if is_a_local_build or rtd_version == 'master':
        return "https://github.com/scrapy/scrapy/blob/master/scrapy/%s%s" % (
           fn, linespec)
    return "https://github.com/scrapy/scrapy/blob/%s/scrapy/%s%s" % (
        scrapy.__version__, fn, linespec)


def setup(app: Sphinx) -> Dict[str, Any]:
    app.connect('doctree-read', doctree_read)
    app.add_config_value('linkcode_resolve', lambda v: resolve, '')
    return {'version': sphinx.__display_version__, 'parallel_read_safe': True}
