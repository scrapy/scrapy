# -*- coding: utf-8 -*-
"""
    sphinx.make_mode
    ~~~~~~~~~~~~~~~~

    sphinx-build -M command-line handling.

    This replaces the old, platform-dependent and once-generated content
    of Makefile / make.bat.

    This is in its own module so that importing it is fast.  It should not
    import the main Sphinx modules (like sphinx.applications, sphinx.builders).

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
from __future__ import print_function

import os
import sys
from os import path
from subprocess import call

import sphinx
from sphinx.util.console import bold, blue
from sphinx.util.osutil import cd, rmtree

proj_name = os.getenv('SPHINXPROJ', '<project>')


BUILDERS = [
    ("",      "html",      "to make standalone HTML files"),
    ("",      "dirhtml",   "to make HTML files named index.html in directories"),
    ("",      "singlehtml", "to make a single large HTML file"),
    ("",      "pickle",    "to make pickle files"),
    ("",      "json",      "to make JSON files"),
    ("",      "htmlhelp",  "to make HTML files and a HTML help project"),
    ("",      "qthelp",    "to make HTML files and a qthelp project"),
    ("",      "devhelp",   "to make HTML files and a Devhelp project"),
    ("",      "epub",      "to make an epub"),
    ("",      "latex",     "to make LaTeX files, you can set PAPER=a4 or PAPER=letter"),
    ("posix", "latexpdf",  "to make LaTeX files and run them through pdflatex"),
    ("posix", "latexpdfja", "to make LaTeX files and run them through platex/dvipdfmx"),
    ("",      "text",      "to make text files"),
    ("",      "man",       "to make manual pages"),
    ("",      "texinfo",   "to make Texinfo files"),
    ("posix", "info",      "to make Texinfo files and run them through makeinfo"),
    ("",      "gettext",   "to make PO message catalogs"),
    ("",      "changes",   "to make an overview of all changed/added/deprecated items"),
    ("",      "xml",       "to make Docutils-native XML files"),
    ("",      "pseudoxml", "to make pseudoxml-XML files for display purposes"),
    ("",      "linkcheck", "to check all external links for integrity"),
    ("",      "doctest",   "to run all doctests embedded in the documentation "
                           "(if enabled)"),
    ("",      "coverage",  "to run coverage check of the documentation (if enabled)"),
]


class Make(object):

    def __init__(self, srcdir, builddir, opts):
        self.srcdir = srcdir
        self.builddir = builddir
        self.opts = opts

    def builddir_join(self, *comps):
        return path.join(self.builddir, *comps)

    def build_clean(self):
        if not path.exists(self.builddir):
            return
        elif not path.isdir(self.builddir):
            print("Error: %r is not a directory!" % self.builddir)
            return 1
        print("Removing everything under %r..." % self.builddir)
        for item in os.listdir(self.builddir):
            rmtree(self.builddir_join(item))

    def build_help(self):
        print(bold("Sphinx v%s" % sphinx.__display_version__))
        print("Please use `make %s' where %s is one of" % ((blue('target'),)*2))
        for osname, bname, description in BUILDERS:
            if not osname or os.name == osname:
                print('  %s  %s' % (blue(bname.ljust(10)), description))

    def build_html(self):
        if self.run_generic_build('html') > 0:
            return 1
        print()
        print('Build finished. The HTML pages are in %s.' % self.builddir_join('html'))

    def build_dirhtml(self):
        if self.run_generic_build('dirhtml') > 0:
            return 1
        print()
        print('Build finished. The HTML pages are in %s.' %
              self.builddir_join('dirhtml'))

    def build_singlehtml(self):
        if self.run_generic_build('singlehtml') > 0:
            return 1
        print()
        print('Build finished. The HTML page is in %s.' %
              self.builddir_join('singlehtml'))

    def build_pickle(self):
        if self.run_generic_build('pickle') > 0:
            return 1
        print()
        print('Build finished; now you can process the pickle files.')

    def build_json(self):
        if self.run_generic_build('json') > 0:
            return 1
        print()
        print('Build finished; now you can process the JSON files.')

    def build_htmlhelp(self):
        if self.run_generic_build('htmlhelp') > 0:
            return 1
        print()
        print('Build finished; now you can run HTML Help Workshop with the '
              '.hhp project file in %s.' % self.builddir_join('htmlhelp'))

    def build_qthelp(self):
        if self.run_generic_build('qthelp') > 0:
            return 1
        print()
        print('Build finished; now you can run "qcollectiongenerator" with the '
              '.qhcp project file in %s, like this:' % self.builddir_join('qthelp'))
        print('$ qcollectiongenerator %s.qhcp' % self.builddir_join('qthelp', proj_name))
        print('To view the help file:')
        print('$ assistant -collectionFile %s.qhc' %
              self.builddir_join('qthelp', proj_name))

    def build_devhelp(self):
        if self.run_generic_build('devhelp') > 0:
            return 1
        print()
        print("Build finished.")
        print("To view the help file:")
        print("$ mkdir -p $HOME/.local/share/devhelp/" + proj_name)
        print("$ ln -s %s $HOME/.local/share/devhelp/%s" %
              (self.builddir_join('devhelp'), proj_name))
        print("$ devhelp")

    def build_epub(self):
        if self.run_generic_build('epub') > 0:
            return 1
        print()
        print('Build finished. The ePub file is in %s.' % self.builddir_join('epub'))

    def build_latex(self):
        if self.run_generic_build('latex') > 0:
            return 1
        print("Build finished; the LaTeX files are in %s." % self.builddir_join('latex'))
        if os.name == 'posix':
            print("Run `make' in that directory to run these through (pdf)latex")
            print("(use `make latexpdf' here to do that automatically).")

    def build_latexpdf(self):
        if self.run_generic_build('latex') > 0:
            return 1
        with cd(self.builddir_join('latex')):
            os.system('make all-pdf')

    def build_latexpdfja(self):
        if self.run_generic_build('latex') > 0:
            return 1
        with cd(self.builddir_join('latex')):
            os.system('make all-pdf-ja')

    def build_text(self):
        if self.run_generic_build('text') > 0:
            return 1
        print()
        print('Build finished. The text files are in %s.' % self.builddir_join('text'))

    def build_texinfo(self):
        if self.run_generic_build('texinfo') > 0:
            return 1
        print("Build finished; the Texinfo files are in %s." %
              self.builddir_join('texinfo'))
        if os.name == 'posix':
            print("Run `make' in that directory to run these through makeinfo")
            print("(use `make info' here to do that automatically).")

    def build_info(self):
        if self.run_generic_build('texinfo') > 0:
            return 1
        with cd(self.builddir_join('texinfo')):
            os.system('make info')

    def build_gettext(self):
        dtdir = self.builddir_join('gettext', '.doctrees')
        if self.run_generic_build('gettext', doctreedir=dtdir) > 0:
            return 1
        print()
        print('Build finished. The message catalogs are in %s.' %
              self.builddir_join('gettext'))

    def build_changes(self):
        if self.run_generic_build('changes') > 0:
            return 1
        print()
        print('Build finished. The overview file is in %s.' %
              self.builddir_join('changes'))

    def build_linkcheck(self):
        res = self.run_generic_build('linkcheck')
        print()
        print('Link check complete; look for any errors in the above output '
              'or in %s.' % self.builddir_join('linkcheck', 'output.txt'))
        return res

    def build_doctest(self):
        res = self.run_generic_build('doctest')
        print("Testing of doctests in the sources finished, look at the "
              "results in %s." % self.builddir_join('doctest', 'output.txt'))
        return res

    def build_coverage(self):
        if self.run_generic_build('coverage') > 0:
            print("Has the coverage extension been enabled?")
            return 1
        print()
        print("Testing of coverage in the sources finished, look at the "
              "results in %s." % self.builddir_join('coverage'))

    def build_xml(self):
        if self.run_generic_build('xml') > 0:
            return 1
        print()
        print('Build finished. The XML files are in %s.' % self.builddir_join('xml'))

    def build_pseudoxml(self):
        if self.run_generic_build('pseudoxml') > 0:
            return 1
        print()
        print('Build finished. The pseudo-XML files are in %s.' %
              self.builddir_join('pseudoxml'))

    def run_generic_build(self, builder, doctreedir=None):
        # compatibility with old Makefile
        papersize = os.getenv('PAPER', '')
        opts = self.opts
        if papersize in ('a4', 'letter'):
            opts.extend(['-D', 'latex_paper_size=' + papersize])
        if doctreedir is None:
            doctreedir = self.builddir_join('doctrees')

        orig_cmd = sys.argv[0]
        if sys.platform == 'win32' and orig_cmd.endswith('.exe'):
            # win32: 'sphinx-build.exe'
            cmd = [orig_cmd]
        elif sys.platform == 'win32' and os.path.splitext(orig_cmd)[1] == '':
            # win32: 'sphinx-build'  without extension
            cmd = [orig_cmd + '.exe']
        else:
            # win32: 'sphinx-build.py'
            # linux, mac: 'sphinx-build' or 'sphinx-build.py'
            cmd = [sys.executable, orig_cmd]

        return call(cmd + ['-b', builder] + opts +
                    ['-d', doctreedir, self.srcdir, self.builddir_join(builder)])


def run_make_mode(args):
    if len(args) < 3:
        print('Error: at least 3 arguments (builder, source '
              'dir, build dir) are required.', file=sys.stderr)
        return 1
    make = Make(args[1], args[2], args[3:])
    run_method = 'build_' + args[0]
    if hasattr(make, run_method):
        return getattr(make, run_method)()
    return make.run_generic_build(args[0])
