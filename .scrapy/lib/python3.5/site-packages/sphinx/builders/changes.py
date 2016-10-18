# -*- coding: utf-8 -*-
"""
    sphinx.builders.changes
    ~~~~~~~~~~~~~~~~~~~~~~~

    Changelog builder.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import codecs
from os import path

from six import iteritems

from sphinx import package_dir
from sphinx.util import copy_static_entry
from sphinx.locale import _
from sphinx.theming import Theme
from sphinx.builders import Builder
from sphinx.util.osutil import ensuredir, os_path
from sphinx.util.console import bold
from sphinx.util.pycompat import htmlescape


class ChangesBuilder(Builder):
    """
    Write a summary with all versionadded/changed directives.
    """
    name = 'changes'

    def init(self):
        self.create_template_bridge()
        Theme.init_themes(self.confdir, self.config.html_theme_path,
                          warn=self.warn)
        self.theme = Theme('default')
        self.templates.init(self, self.theme)

    def get_outdated_docs(self):
        return self.outdir

    typemap = {
        'versionadded': 'added',
        'versionchanged': 'changed',
        'deprecated': 'deprecated',
    }

    def write(self, *ignored):
        version = self.config.version
        libchanges = {}
        apichanges = []
        otherchanges = {}
        if version not in self.env.versionchanges:
            self.info(bold('no changes in version %s.' % version))
            return
        self.info(bold('writing summary file...'))
        for type, docname, lineno, module, descname, content in \
                self.env.versionchanges[version]:
            if isinstance(descname, tuple):
                descname = descname[0]
            ttext = self.typemap[type]
            context = content.replace('\n', ' ')
            if descname and docname.startswith('c-api'):
                if not descname:
                    continue
                if context:
                    entry = '<b>%s</b>: <i>%s:</i> %s' % (descname, ttext,
                                                          context)
                else:
                    entry = '<b>%s</b>: <i>%s</i>.' % (descname, ttext)
                apichanges.append((entry, docname, lineno))
            elif descname or module:
                if not module:
                    module = _('Builtins')
                if not descname:
                    descname = _('Module level')
                if context:
                    entry = '<b>%s</b>: <i>%s:</i> %s' % (descname, ttext,
                                                          context)
                else:
                    entry = '<b>%s</b>: <i>%s</i>.' % (descname, ttext)
                libchanges.setdefault(module, []).append((entry, docname,
                                                          lineno))
            else:
                if not context:
                    continue
                entry = '<i>%s:</i> %s' % (ttext.capitalize(), context)
                title = self.env.titles[docname].astext()
                otherchanges.setdefault((docname, title), []).append(
                    (entry, docname, lineno))

        ctx = {
            'project': self.config.project,
            'version': version,
            'docstitle': self.config.html_title,
            'shorttitle': self.config.html_short_title,
            'libchanges': sorted(iteritems(libchanges)),
            'apichanges': sorted(apichanges),
            'otherchanges': sorted(iteritems(otherchanges)),
            'show_copyright': self.config.html_show_copyright,
            'show_sphinx': self.config.html_show_sphinx,
        }
        f = codecs.open(path.join(self.outdir, 'index.html'), 'w', 'utf8')
        try:
            f.write(self.templates.render('changes/frameset.html', ctx))
        finally:
            f.close()
        f = codecs.open(path.join(self.outdir, 'changes.html'), 'w', 'utf8')
        try:
            f.write(self.templates.render('changes/versionchanges.html', ctx))
        finally:
            f.close()

        hltext = ['.. versionadded:: %s' % version,
                  '.. versionchanged:: %s' % version,
                  '.. deprecated:: %s' % version]

        def hl(no, line):
            line = '<a name="L%s"> </a>' % no + htmlescape(line)
            for x in hltext:
                if x in line:
                    line = '<span class="hl">%s</span>' % line
                    break
            return line

        self.info(bold('copying source files...'))
        for docname in self.env.all_docs:
            f = codecs.open(self.env.doc2path(docname), 'r',
                            self.env.config.source_encoding)
            try:
                lines = f.readlines()
            except UnicodeDecodeError:
                self.warn('could not read %r for changelog creation' % docname)
                continue
            finally:
                f.close()
            targetfn = path.join(self.outdir, 'rst', os_path(docname)) + '.html'
            ensuredir(path.dirname(targetfn))
            f = codecs.open(targetfn, 'w', 'utf-8')
            try:
                text = ''.join(hl(i+1, line) for (i, line) in enumerate(lines))
                ctx = {
                    'filename': self.env.doc2path(docname, None),
                    'text': text
                }
                f.write(self.templates.render('changes/rstsource.html', ctx))
            finally:
                f.close()
        themectx = dict(('theme_' + key, val) for (key, val) in
                        iteritems(self.theme.get_options({})))
        copy_static_entry(path.join(package_dir, 'themes', 'default',
                                    'static', 'default.css_t'),
                          self.outdir, self, themectx)
        copy_static_entry(path.join(package_dir, 'themes', 'basic',
                                    'static', 'basic.css'),
                          self.outdir, self)

    def hl(self, text, version):
        text = htmlescape(text)
        for directive in ['versionchanged', 'versionadded', 'deprecated']:
            text = text.replace('.. %s:: %s' % (directive, version),
                                '<b>.. %s:: %s</b>' % (directive, version))
        return text

    def finish(self):
        pass
