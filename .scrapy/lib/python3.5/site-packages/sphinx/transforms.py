# -*- coding: utf-8 -*-
"""
    sphinx.transforms
    ~~~~~~~~~~~~~~~~~

    Docutils transforms used by Sphinx when reading documents.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from os import path

from docutils import nodes
from docutils.io import StringInput
from docutils.utils import relative_path
from docutils.transforms import Transform
from docutils.transforms.parts import ContentsFilter

from sphinx import addnodes
from sphinx.locale import _, init as init_locale
from sphinx.util import split_index_msg
from sphinx.util.nodes import (
    traverse_translatable_index, extract_messages, LITERAL_TYPE_NODES, IMAGE_TYPE_NODES,
    apply_source_workaround,
)
from sphinx.util.i18n import find_catalog, format_date
from sphinx.util.pycompat import indent
from sphinx.domains.std import make_glossary_term, split_term_classifiers


default_substitutions = set([
    'version',
    'release',
    'today',
])


class DefaultSubstitutions(Transform):
    """
    Replace some substitutions if they aren't defined in the document.
    """
    # run before the default Substitutions
    default_priority = 210

    def apply(self):
        env = self.document.settings.env
        config = self.document.settings.env.config
        # only handle those not otherwise defined in the document
        to_handle = default_substitutions - set(self.document.substitution_defs)
        for ref in self.document.traverse(nodes.substitution_reference):
            refname = ref['refname']
            if refname in to_handle:
                text = config[refname]
                if refname == 'today' and not text:
                    # special handling: can also specify a strftime format
                    text = format_date(config.today_fmt or _('%b %d, %Y'),
                                       language=config.language, warn=env.warn)
                ref.replace_self(nodes.Text(text, text))


class MoveModuleTargets(Transform):
    """
    Move module targets that are the first thing in a section to the section
    title.

    XXX Python specific
    """
    default_priority = 210

    def apply(self):
        for node in self.document.traverse(nodes.target):
            if not node['ids']:
                continue
            if ('ismod' in node and
                    node.parent.__class__ is nodes.section and
                    # index 0 is the section title node
                    node.parent.index(node) == 1):
                node.parent['ids'][0:0] = node['ids']
                node.parent.remove(node)


class HandleCodeBlocks(Transform):
    """
    Several code block related transformations.
    """
    default_priority = 210

    def apply(self):
        # move doctest blocks out of blockquotes
        for node in self.document.traverse(nodes.block_quote):
            if all(isinstance(child, nodes.doctest_block) for child
                   in node.children):
                node.replace_self(node.children)
        # combine successive doctest blocks
        # for node in self.document.traverse(nodes.doctest_block):
        #    if node not in node.parent.children:
        #        continue
        #    parindex = node.parent.index(node)
        #    while len(node.parent) > parindex+1 and \
        #            isinstance(node.parent[parindex+1], nodes.doctest_block):
        #        node[0] = nodes.Text(node[0] + '\n\n' +
        #                             node.parent[parindex+1][0])
        #        del node.parent[parindex+1]


class AutoNumbering(Transform):
    """
    Register IDs of tables, figures and literal_blocks to assign numbers.
    """
    default_priority = 210

    def apply(self):
        domain = self.document.settings.env.domains['std']

        for node in self.document.traverse(nodes.Element):
            if domain.is_enumerable_node(node) and domain.get_numfig_title(node) is not None:
                self.document.note_implicit_target(node)


class SortIds(Transform):
    """
    Sort secion IDs so that the "id[0-9]+" one comes last.
    """
    default_priority = 261

    def apply(self):
        for node in self.document.traverse(nodes.section):
            if len(node['ids']) > 1 and node['ids'][0].startswith('id'):
                node['ids'] = node['ids'][1:] + [node['ids'][0]]


class CitationReferences(Transform):
    """
    Replace citation references by pending_xref nodes before the default
    docutils transform tries to resolve them.
    """
    default_priority = 619

    def apply(self):
        for citnode in self.document.traverse(nodes.citation_reference):
            cittext = citnode.astext()
            refnode = addnodes.pending_xref(cittext, reftype='citation',
                                            reftarget=cittext, refwarn=True,
                                            ids=citnode["ids"])
            refnode.source = citnode.source or citnode.parent.source
            refnode.line = citnode.line or citnode.parent.line
            refnode += nodes.Text('[' + cittext + ']')
            citnode.parent.replace(citnode, refnode)


TRANSLATABLE_NODES = {
    'literal-block': nodes.literal_block,
    'doctest-block': nodes.doctest_block,
    'raw': nodes.raw,
    'index': addnodes.index,
    'image': nodes.image,
}


class ApplySourceWorkaround(Transform):
    """
    update source and rawsource attributes
    """
    default_priority = 10

    def apply(self):
        for n in self.document.traverse():
            if isinstance(n, nodes.TextElement):
                apply_source_workaround(n)


class AutoIndexUpgrader(Transform):
    """
    Detect old style; 4 column based indices and automatically upgrade to new style.
    """
    default_priority = 210

    def apply(self):
        env = self.document.settings.env
        for node in self.document.traverse(addnodes.index):
            if 'entries' in node and any(len(entry) == 4 for entry in node['entries']):
                msg = ('4 column based index found. '
                       'It might be a bug of extensions you use: %r' % node['entries'])
                env.warn_node(msg, node)
                for i, entry in enumerate(node['entries']):
                    if len(entry) == 4:
                        node['entries'][i] = entry + (None,)


class ExtraTranslatableNodes(Transform):
    """
    make nodes translatable
    """
    default_priority = 10

    def apply(self):
        targets = self.document.settings.env.config.gettext_additional_targets
        target_nodes = [v for k, v in TRANSLATABLE_NODES.items() if k in targets]
        if not target_nodes:
            return

        def is_translatable_node(node):
            return isinstance(node, tuple(target_nodes))

        for node in self.document.traverse(is_translatable_node):
            node['translatable'] = True


def publish_msgstr(app, source, source_path, source_line, config, settings):
    """Publish msgstr (single line) into docutils document

    :param sphinx.application.Sphinx app: sphinx application
    :param unicode source: source text
    :param unicode source_path: source path for warning indication
    :param source_line: source line for warning indication
    :param sphinx.config.Config config: sphinx config
    :param docutils.frontend.Values settings: docutils settings
    :return: document
    :rtype: docutils.nodes.document
    """
    from sphinx.io import SphinxI18nReader
    reader = SphinxI18nReader(
        app=app,
        parsers=config.source_parsers,
        parser_name='restructuredtext',  # default parser
    )
    reader.set_lineno_for_reporter(source_line)
    doc = reader.read(
        source=StringInput(source=source, source_path=source_path),
        parser=reader.parser,
        settings=settings,
    )
    try:
        doc = doc[0]
    except IndexError:  # empty node
        pass
    return doc


class Locale(Transform):
    """
    Replace translatable nodes with their translated doctree.
    """
    default_priority = 20

    def apply(self):
        env = self.document.settings.env
        settings, source = self.document.settings, self.document['source']
        # XXX check if this is reliable
        assert source.startswith(env.srcdir)
        docname = path.splitext(relative_path(path.join(env.srcdir, 'dummy'),
                                              source))[0]
        textdomain = find_catalog(docname,
                                  self.document.settings.gettext_compact)

        # fetch translations
        dirs = [path.join(env.srcdir, directory)
                for directory in env.config.locale_dirs]
        catalog, has_catalog = init_locale(dirs, env.config.language, textdomain)
        if not has_catalog:
            return

        # phase1: replace reference ids with translated names
        for node, msg in extract_messages(self.document):
            msgstr = catalog.gettext(msg)
            # XXX add marker to untranslated parts
            if not msgstr or msgstr == msg or not msgstr.strip():
                # as-of-yet untranslated
                continue

            # Avoid "Literal block expected; none found." warnings.
            # If msgstr ends with '::' then it cause warning message at
            # parser.parse() processing.
            # literal-block-warning is only appear in avobe case.
            if msgstr.strip().endswith('::'):
                msgstr += '\n\n   dummy literal'
                # dummy literal node will discard by 'patch = patch[0]'

            # literalblock need literal block notation to avoid it become
            # paragraph.
            if isinstance(node, LITERAL_TYPE_NODES):
                msgstr = '::\n\n' + indent(msgstr, ' '*3)

            patch = publish_msgstr(
                env.app, msgstr, source, node.line, env.config, settings)
            # XXX doctest and other block markup
            if not isinstance(patch, nodes.paragraph):
                continue  # skip for now

            processed = False  # skip flag

            # update title(section) target name-id mapping
            if isinstance(node, nodes.title):
                section_node = node.parent
                new_name = nodes.fully_normalize_name(patch.astext())
                old_name = nodes.fully_normalize_name(node.astext())

                if old_name != new_name:
                    # if name would be changed, replace node names and
                    # document nameids mapping with new name.
                    names = section_node.setdefault('names', [])
                    names.append(new_name)
                    # Original section name (reference target name) should be kept to refer
                    # from other nodes which is still not translated or uses explicit target
                    # name like "`text to display <explicit target name_>`_"..
                    # So, `old_name` is still exist in `names`.

                    _id = self.document.nameids.get(old_name, None)
                    explicit = self.document.nametypes.get(old_name, None)

                    # * if explicit: _id is label. title node need another id.
                    # * if not explicit:
                    #
                    #   * if _id is None:
                    #
                    #     _id is None means:
                    #
                    #     1. _id was not provided yet.
                    #
                    #     2. _id was duplicated.
                    #
                    #        old_name entry still exists in nameids and
                    #        nametypes for another duplicated entry.
                    #
                    #   * if _id is provided: bellow process
                    if _id:
                        if not explicit:
                            # _id was not duplicated.
                            # remove old_name entry from document ids database
                            # to reuse original _id.
                            self.document.nameids.pop(old_name, None)
                            self.document.nametypes.pop(old_name, None)
                            self.document.ids.pop(_id, None)

                        # re-entry with new named section node.
                        #
                        # Note: msgnode that is a second parameter of the
                        # `note_implicit_target` is not necessary here because
                        # section_node has been noted previously on rst parsing by
                        # `docutils.parsers.rst.states.RSTState.new_subsection()`
                        # and already has `system_message` if needed.
                        self.document.note_implicit_target(section_node)

                    # replace target's refname to new target name
                    def is_named_target(node):
                        return isinstance(node, nodes.target) and  \
                            node.get('refname') == old_name
                    for old_target in self.document.traverse(is_named_target):
                        old_target['refname'] = new_name

                    processed = True

            # glossary terms update refid
            if isinstance(node, nodes.term):
                gloss_entries = env.temp_data.setdefault('gloss_entries', set())
                for _id in node['names']:
                    if _id in gloss_entries:
                        gloss_entries.remove(_id)

                    parts = split_term_classifiers(msgstr)
                    patch = publish_msgstr(
                        env.app, parts[0], source, node.line, env.config, settings)
                    patch = make_glossary_term(
                        env, patch, parts[1], source, node.line, _id)
                    node['ids'] = patch['ids']
                    node['names'] = patch['names']
                    processed = True

            # update leaves with processed nodes
            if processed:
                for child in patch.children:
                    child.parent = node
                node.children = patch.children
                node['translated'] = True

        # phase2: translation
        for node, msg in extract_messages(self.document):
            if node.get('translated', False):
                continue

            msgstr = catalog.gettext(msg)
            # XXX add marker to untranslated parts
            if not msgstr or msgstr == msg:  # as-of-yet untranslated
                continue

            # Avoid "Literal block expected; none found." warnings.
            # If msgstr ends with '::' then it cause warning message at
            # parser.parse() processing.
            # literal-block-warning is only appear in avobe case.
            if msgstr.strip().endswith('::'):
                msgstr += '\n\n   dummy literal'
                # dummy literal node will discard by 'patch = patch[0]'

            # literalblock need literal block notation to avoid it become
            # paragraph.
            if isinstance(node, LITERAL_TYPE_NODES):
                msgstr = '::\n\n' + indent(msgstr, ' '*3)

            patch = publish_msgstr(
                env.app, msgstr, source, node.line, env.config, settings)
            # XXX doctest and other block markup
            if not isinstance(
                    patch,
                    (nodes.paragraph,) + LITERAL_TYPE_NODES + IMAGE_TYPE_NODES):
                continue  # skip for now

            # auto-numbered foot note reference should use original 'ids'.
            def is_autonumber_footnote_ref(node):
                return isinstance(node, nodes.footnote_reference) and \
                    node.get('auto') == 1

            def list_replace_or_append(lst, old, new):
                if old in lst:
                    lst[lst.index(old)] = new
                else:
                    lst.append(new)
            old_foot_refs = node.traverse(is_autonumber_footnote_ref)
            new_foot_refs = patch.traverse(is_autonumber_footnote_ref)
            if len(old_foot_refs) != len(new_foot_refs):
                env.warn_node('inconsistent footnote references in '
                              'translated message', node)
            old_foot_namerefs = {}
            for r in old_foot_refs:
                old_foot_namerefs.setdefault(r.get('refname'), []).append(r)
            for new in new_foot_refs:
                refname = new.get('refname')
                refs = old_foot_namerefs.get(refname, [])
                if not refs:
                    continue

                old = refs.pop(0)
                new['ids'] = old['ids']
                for id in new['ids']:
                    self.document.ids[id] = new
                list_replace_or_append(
                    self.document.autofootnote_refs, old, new)
                if refname:
                    list_replace_or_append(
                        self.document.footnote_refs.setdefault(refname, []),
                        old, new)
                    list_replace_or_append(
                        self.document.refnames.setdefault(refname, []),
                        old, new)

            # reference should use new (translated) 'refname'.
            # * reference target ".. _Python: ..." is not translatable.
            # * use translated refname for section refname.
            # * inline reference "`Python <...>`_" has no 'refname'.
            def is_refnamed_ref(node):
                return isinstance(node, nodes.reference) and  \
                    'refname' in node
            old_refs = node.traverse(is_refnamed_ref)
            new_refs = patch.traverse(is_refnamed_ref)
            if len(old_refs) != len(new_refs):
                env.warn_node('inconsistent references in '
                              'translated message', node)
            old_ref_names = [r['refname'] for r in old_refs]
            new_ref_names = [r['refname'] for r in new_refs]
            orphans = list(set(old_ref_names) - set(new_ref_names))
            for new in new_refs:
                if not self.document.has_name(new['refname']):
                    # Maybe refname is translated but target is not translated.
                    # Note: multiple translated refnames break link ordering.
                    if orphans:
                        new['refname'] = orphans.pop(0)
                    else:
                        # orphan refnames is already empty!
                        # reference number is same in new_refs and old_refs.
                        pass

                self.document.note_refname(new)

            # refnamed footnote and citation should use original 'ids'.
            def is_refnamed_footnote_ref(node):
                footnote_ref_classes = (nodes.footnote_reference,
                                        nodes.citation_reference)
                return isinstance(node, footnote_ref_classes) and \
                    'refname' in node
            old_refs = node.traverse(is_refnamed_footnote_ref)
            new_refs = patch.traverse(is_refnamed_footnote_ref)
            refname_ids_map = {}
            if len(old_refs) != len(new_refs):
                env.warn_node('inconsistent references in '
                              'translated message', node)
            for old in old_refs:
                refname_ids_map[old["refname"]] = old["ids"]
            for new in new_refs:
                refname = new["refname"]
                if refname in refname_ids_map:
                    new["ids"] = refname_ids_map[refname]

            # Original pending_xref['reftarget'] contain not-translated
            # target name, new pending_xref must use original one.
            # This code restricts to change ref-targets in the translation.
            old_refs = node.traverse(addnodes.pending_xref)
            new_refs = patch.traverse(addnodes.pending_xref)
            xref_reftarget_map = {}
            if len(old_refs) != len(new_refs):
                env.warn_node('inconsistent term references in '
                              'translated message', node)

            def get_ref_key(node):
                case = node["refdomain"], node["reftype"]
                if case == ('std', 'term'):
                    return None
                else:
                    return (
                        node["refdomain"],
                        node["reftype"],
                        node['reftarget'],)

            for old in old_refs:
                key = get_ref_key(old)
                if key:
                    xref_reftarget_map[key] = old.attributes
            for new in new_refs:
                key = get_ref_key(new)
                # Copy attributes to keep original node behavior. Especially
                # copying 'reftarget', 'py:module', 'py:class' are needed.
                for k, v in xref_reftarget_map.get(key, {}).items():
                    # Note: This implementation overwrite all attributes.
                    # if some attributes `k` should not be overwritten,
                    # you should provide exclude list as:
                    # `if k not in EXCLUDE_LIST: new[k] = v`
                    new[k] = v

            # update leaves
            for child in patch.children:
                child.parent = node
            node.children = patch.children

            # for highlighting that expects .rawsource and .astext() are same.
            if isinstance(node, LITERAL_TYPE_NODES):
                node.rawsource = node.astext()

            if isinstance(node, IMAGE_TYPE_NODES):
                node.update_all_atts(patch)

            node['translated'] = True

        if 'index' in env.config.gettext_additional_targets:
            # Extract and translate messages for index entries.
            for node, entries in traverse_translatable_index(self.document):
                new_entries = []
                for type, msg, tid, main, key_ in entries:
                    msg_parts = split_index_msg(type, msg)
                    msgstr_parts = []
                    for part in msg_parts:
                        msgstr = catalog.gettext(part)
                        if not msgstr:
                            msgstr = part
                        msgstr_parts.append(msgstr)

                    new_entries.append((type, ';'.join(msgstr_parts), tid, main, None))

                node['raw_entries'] = entries
                node['entries'] = new_entries


class RemoveTranslatableInline(Transform):
    """
    Remove inline nodes used for translation as placeholders.
    """
    default_priority = 999

    def apply(self):
        from sphinx.builders.gettext import MessageCatalogBuilder
        env = self.document.settings.env
        builder = env.app.builder
        if isinstance(builder, MessageCatalogBuilder):
            return
        for inline in self.document.traverse(nodes.inline):
            if 'translatable' in inline:
                inline.parent.remove(inline)
                inline.parent += inline.children


class SphinxContentsFilter(ContentsFilter):
    """
    Used with BuildEnvironment.add_toc_from() to discard cross-file links
    within table-of-contents link nodes.
    """
    def visit_pending_xref(self, node):
        text = node.astext()
        self.parent.append(nodes.literal(text, text))
        raise nodes.SkipNode

    def visit_image(self, node):
        raise nodes.SkipNode
