# -*- coding: utf-8 -*-
"""
    sphinx.builders.gettext
    ~~~~~~~~~~~~~~~~~~~~~~~

    The MessageCatalogBuilder class.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from __future__ import unicode_literals

from os import path, walk, getenv
from codecs import open
from time import time
from datetime import datetime, tzinfo, timedelta
from collections import defaultdict
from uuid import uuid4

from six import iteritems

from sphinx.builders import Builder
from sphinx.util import split_index_msg
from sphinx.util.nodes import extract_messages, traverse_translatable_index
from sphinx.util.osutil import safe_relpath, ensuredir, canon_path
from sphinx.util.i18n import find_catalog
from sphinx.util.console import darkgreen, purple, bold
from sphinx.locale import pairindextypes

POHEADER = r"""
# SOME DESCRIPTIVE TITLE.
# Copyright (C) %(copyright)s
# This file is distributed under the same license as the %(project)s package.
# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
#
#, fuzzy
msgid ""
msgstr ""
"Project-Id-Version: %(project)s %(version)s\n"
"Report-Msgid-Bugs-To: \n"
"POT-Creation-Date: %(ctime)s\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\n"
"Language-Team: LANGUAGE <LL@li.org>\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"

"""[1:]


class Catalog(object):
    """Catalog of translatable messages."""

    def __init__(self):
        self.messages = []  # retain insertion order, a la OrderedDict
        self.metadata = {}  # msgid -> file, line, uid

    def add(self, msg, origin):
        if not hasattr(origin, 'uid'):
            # Nodes that are replicated like todo don't have a uid,
            # however i18n is also unnecessary.
            return
        if msg not in self.metadata:  # faster lookup in hash
            self.messages.append(msg)
            self.metadata[msg] = []
        self.metadata[msg].append((origin.source, origin.line, origin.uid))


class MsgOrigin(object):
    """
    Origin holder for Catalog message origin.
    """

    def __init__(self, source, line):
        self.source = source
        self.line = line
        self.uid = uuid4().hex


class I18nBuilder(Builder):
    """
    General i18n builder.
    """
    name = 'i18n'
    versioning_method = 'text'
    versioning_compare = None  # be set by `gettext_uuid`

    def __init__(self, app):
        self.versioning_compare = app.env.config.gettext_uuid
        super(I18nBuilder, self).__init__(app)

    def init(self):
        Builder.init(self)
        self.catalogs = defaultdict(Catalog)

    def get_target_uri(self, docname, typ=None):
        return ''

    def get_outdated_docs(self):
        return self.env.found_docs

    def prepare_writing(self, docnames):
        return

    def compile_catalogs(self, catalogs, message):
        return

    def write_doc(self, docname, doctree):
        catalog = self.catalogs[find_catalog(docname,
                                             self.config.gettext_compact)]

        for node, msg in extract_messages(doctree):
            catalog.add(msg, node)

        if 'index' in self.env.config.gettext_additional_targets:
            # Extract translatable messages from index entries.
            for node, entries in traverse_translatable_index(doctree):
                for typ, msg, tid, main, key_ in entries:
                    for m in split_index_msg(typ, msg):
                        if typ == 'pair' and m in pairindextypes.values():
                            # avoid built-in translated message was incorporated
                            # in 'sphinx.util.nodes.process_index_entry'
                            continue
                        catalog.add(m, node)


# determine tzoffset once to remain unaffected by DST change during build
timestamp = time()
tzdelta = datetime.fromtimestamp(timestamp) - \
    datetime.utcfromtimestamp(timestamp)
# set timestamp from SOURCE_DATE_EPOCH if set
# see https://reproducible-builds.org/specs/source-date-epoch/
source_date_epoch = getenv('SOURCE_DATE_EPOCH')
if source_date_epoch is not None:
    timestamp = float(source_date_epoch)
    tzdelta = timedelta(0)


class LocalTimeZone(tzinfo):

    def __init__(self, *args, **kw):
        super(LocalTimeZone, self).__init__(*args, **kw)
        self.tzdelta = tzdelta

    def utcoffset(self, dt):
        return self.tzdelta

    def dst(self, dt):
        return timedelta(0)

ltz = LocalTimeZone()


class MessageCatalogBuilder(I18nBuilder):
    """
    Builds gettext-style message catalogs (.pot files).
    """
    name = 'gettext'

    def init(self):
        I18nBuilder.init(self)
        self.create_template_bridge()
        self.templates.init(self)

    def _collect_templates(self):
        template_files = set()
        for template_path in self.config.templates_path:
            tmpl_abs_path = path.join(self.app.srcdir, template_path)
            for dirpath, dirs, files in walk(tmpl_abs_path):
                for fn in files:
                    if fn.endswith('.html'):
                        filename = canon_path(path.join(dirpath, fn))
                        template_files.add(filename)
        return template_files

    def _extract_from_template(self):
        files = self._collect_templates()
        self.info(bold('building [%s]: ' % self.name), nonl=1)
        self.info('targets for %d template files' % len(files))

        extract_translations = self.templates.environment.extract_translations

        for template in self.app.status_iterator(
                files, 'reading templates... ', purple, len(files)):
            with open(template, 'r', encoding='utf-8') as f:
                context = f.read()
            for line, meth, msg in extract_translations(context):
                origin = MsgOrigin(template, line)
                self.catalogs['sphinx'].add(msg, origin)

    def build(self, docnames, summary=None, method='update'):
        self._extract_from_template()
        I18nBuilder.build(self, docnames, summary, method)

    def finish(self):
        I18nBuilder.finish(self)
        data = dict(
            version = self.config.version,
            copyright = self.config.copyright,
            project = self.config.project,
            ctime = datetime.fromtimestamp(
                timestamp, ltz).strftime('%Y-%m-%d %H:%M%z'),
        )
        for textdomain, catalog in self.app.status_iterator(
                iteritems(self.catalogs), "writing message catalogs... ",
                darkgreen, len(self.catalogs),
                lambda textdomain__: textdomain__[0]):
            # noop if config.gettext_compact is set
            ensuredir(path.join(self.outdir, path.dirname(textdomain)))

            pofn = path.join(self.outdir, textdomain + '.pot')
            pofile = open(pofn, 'w', encoding='utf-8')
            try:
                pofile.write(POHEADER % data)

                for message in catalog.messages:
                    positions = catalog.metadata[message]

                    if self.config.gettext_location:
                        # generate "#: file1:line1\n#: file2:line2 ..."
                        pofile.write("#: %s\n" % "\n#: ".join(
                            "%s:%s" % (canon_path(
                                safe_relpath(source, self.outdir)), line)
                            for source, line, _ in positions))
                    if self.config.gettext_uuid:
                        # generate "# uuid1\n# uuid2\n ..."
                        pofile.write("# %s\n" % "\n# ".join(
                            uid for _, _, uid in positions))

                    # message contains *one* line of text ready for translation
                    message = message.replace('\\', r'\\'). \
                        replace('"', r'\"'). \
                        replace('\n', '\\n"\n"')
                    pofile.write('msgid "%s"\nmsgstr ""\n\n' % message)

            finally:
                pofile.close()
