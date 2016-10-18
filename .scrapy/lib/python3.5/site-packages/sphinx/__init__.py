# -*- coding: utf-8 -*-
"""
    Sphinx
    ~~~~~~

    The Sphinx documentation toolchain.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

# Keep this file executable as-is in Python 3!
# (Otherwise getting the version out of it from setup.py is impossible.)

import sys
from os import path

__version__  = '1.4.8'
__released__ = '1.4.8'  # used when Sphinx builds its own docs

# version info for better programmatic use
# possible values for 3rd element: 'alpha', 'beta', 'rc', 'final'
# 'final' has 0 as the last element
version_info = (1, 4, 8, 'final', 0)

package_dir = path.abspath(path.dirname(__file__))

__display_version__ = __version__  # used for command line version
if __version__.endswith('+'):
    # try to find out the changeset hash if checked out from hg, and append
    # it to __version__ (since we use this value from setup.py, it gets
    # automatically propagated to an installed copy as well)
    __display_version__ = __version__
    __version__ = __version__[:-1]  # remove '+' for PEP-440 version spec.
    try:
        import subprocess
        p = subprocess.Popen(['git', 'show', '-s', '--pretty=format:%h',
                              path.join(package_dir, '..')],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        if out:
            __display_version__ += '/' + out.decode().strip()
    except Exception:
        pass


def main(argv=sys.argv):
    if sys.argv[1:2] == ['-M']:
        sys.exit(make_main(argv))
    else:
        sys.exit(build_main(argv))


def build_main(argv=sys.argv):
    """Sphinx build "main" command-line entry."""
    if (sys.version_info[:3] < (2, 6, 0) or
       (3, 0, 0) <= sys.version_info[:3] < (3, 3, 0)):
        sys.stderr.write('Error: Sphinx requires at least Python 2.6 or 3.3 to run.\n')
        return 1
    try:
        from sphinx import cmdline
    except ImportError:
        err = sys.exc_info()[1]
        errstr = str(err)
        if errstr.lower().startswith('no module named'):
            whichmod = errstr[16:]
            hint = ''
            if whichmod.startswith('docutils'):
                whichmod = 'Docutils library'
            elif whichmod.startswith('jinja'):
                whichmod = 'Jinja2 library'
            elif whichmod == 'roman':
                whichmod = 'roman module (which is distributed with Docutils)'
                hint = ('This can happen if you upgraded docutils using\n'
                        'easy_install without uninstalling the old version'
                        'first.\n')
            else:
                whichmod += ' module'
            sys.stderr.write('Error: The %s cannot be found. '
                             'Did you install Sphinx and its dependencies '
                             'correctly?\n' % whichmod)
            if hint:
                sys.stderr.write(hint)
            return 1
        raise

    from sphinx.util.compat import docutils_version
    if docutils_version < (0, 10):
        sys.stderr.write('Error: Sphinx requires at least Docutils 0.10 to '
                         'run.\n')
        return 1
    return cmdline.main(argv)


def make_main(argv=sys.argv):
    """Sphinx build "make mode" entry."""
    from sphinx import make_mode
    return make_mode.run_make_mode(argv[2:])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
