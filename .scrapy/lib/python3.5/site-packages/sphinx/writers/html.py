# -*- coding: utf-8 -*-
"""
    sphinx.writers.html
    ~~~~~~~~~~~~~~~~~~~

    docutils writers handling Sphinx' custom nodes.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import sys
import posixpath
import os
import copy
import warnings

from six import string_types
from docutils import nodes
from docutils.writers.html4css1 import Writer, HTMLTranslator as BaseTranslator

from sphinx import addnodes
from sphinx.locale import admonitionlabels, _
from sphinx.util.images import get_image_size
from sphinx.util.smartypants import sphinx_smarty_pants

# A good overview of the purpose behind these classes can be found here:
# http://www.arnebrodowski.de/blog/write-your-own-restructuredtext-writer.html


class HTMLWriter(Writer):

    # override embed-stylesheet default value to 0.
    settings_spec = copy.deepcopy(Writer.settings_spec)
    for _setting in settings_spec[2]:
        if '--embed-stylesheet' in _setting[1]:
            _setting[2]['default'] = 0

    def __init__(self, builder):
        Writer.__init__(self)
        self.builder = builder

    def translate(self):
        # sadly, this is mostly copied from parent class
        self.visitor = visitor = self.builder.translator_class(self.builder,
                                                               self.document)
        self.document.walkabout(visitor)
        self.output = visitor.astext()
        for attr in ('head_prefix', 'stylesheet', 'head', 'body_prefix',
                     'body_pre_docinfo', 'docinfo', 'body', 'fragment',
                     'body_suffix', 'meta', 'title', 'subtitle', 'header',
                     'footer', 'html_prolog', 'html_head', 'html_title',
                     'html_subtitle', 'html_body', ):
            setattr(self, attr, getattr(visitor, attr, None))
        self.clean_meta = ''.join(visitor.meta[2:])


class HTMLTranslator(BaseTranslator):
    """
    Our custom HTML translator.
    """

    def __init__(self, builder, *args, **kwds):
        BaseTranslator.__init__(self, *args, **kwds)
        self.highlighter = builder.highlighter
        self.no_smarty = 0
        self.builder = builder
        self.highlightlang = self.highlightlang_base = \
            builder.config.highlight_language
        self.highlightopts = builder.config.highlight_options
        self.highlightlinenothreshold = sys.maxsize
        self.docnames = [builder.current_docname]  # for singlehtml builder
        self.protect_literal_text = 0
        self.permalink_text = builder.config.html_add_permalinks
        # support backwards-compatible setting to a bool
        if not isinstance(self.permalink_text, string_types):
            self.permalink_text = self.permalink_text and u'\u00B6' or ''
        self.permalink_text = self.encode(self.permalink_text)
        self.secnumber_suffix = builder.config.html_secnumber_suffix
        self.param_separator = ''
        self.optional_param_level = 0
        self._table_row_index = 0

    def visit_start_of_file(self, node):
        # only occurs in the single-file builder
        self.docnames.append(node['docname'])
        self.body.append('<span id="document-%s"></span>' % node['docname'])

    def depart_start_of_file(self, node):
        self.docnames.pop()

    def visit_desc(self, node):
        self.body.append(self.starttag(node, 'dl', CLASS=node['objtype']))

    def depart_desc(self, node):
        self.body.append('</dl>\n\n')

    def visit_desc_signature(self, node):
        # the id is set automatically
        self.body.append(self.starttag(node, 'dt'))
        # anchor for per-desc interactive data
        if node.parent['objtype'] != 'describe' \
           and node['ids'] and node['first']:
            self.body.append('<!--[%s]-->' % node['ids'][0])

    def depart_desc_signature(self, node):
        self.add_permalink_ref(node, _('Permalink to this definition'))
        self.body.append('</dt>\n')

    def visit_desc_addname(self, node):
        self.body.append(self.starttag(node, 'code', '', CLASS='descclassname'))

    def depart_desc_addname(self, node):
        self.body.append('</code>')

    def visit_desc_type(self, node):
        pass

    def depart_desc_type(self, node):
        pass

    def visit_desc_returns(self, node):
        self.body.append(' &rarr; ')

    def depart_desc_returns(self, node):
        pass

    def visit_desc_name(self, node):
        self.body.append(self.starttag(node, 'code', '', CLASS='descname'))

    def depart_desc_name(self, node):
        self.body.append('</code>')

    def visit_desc_parameterlist(self, node):
        self.body.append('<span class="sig-paren">(</span>')
        self.first_param = 1
        self.optional_param_level = 0
        # How many required parameters are left.
        self.required_params_left = sum([isinstance(c, addnodes.desc_parameter)
                                         for c in node.children])
        self.param_separator = node.child_text_separator

    def depart_desc_parameterlist(self, node):
        self.body.append('<span class="sig-paren">)</span>')

    # If required parameters are still to come, then put the comma after
    # the parameter.  Otherwise, put the comma before.  This ensures that
    # signatures like the following render correctly (see issue #1001):
    #
    #     foo([a, ]b, c[, d])
    #
    def visit_desc_parameter(self, node):
        if self.first_param:
            self.first_param = 0
        elif not self.required_params_left:
            self.body.append(self.param_separator)
        if self.optional_param_level == 0:
            self.required_params_left -= 1
        if not node.hasattr('noemph'):
            self.body.append('<em>')

    def depart_desc_parameter(self, node):
        if not node.hasattr('noemph'):
            self.body.append('</em>')
        if self.required_params_left:
            self.body.append(self.param_separator)

    def visit_desc_optional(self, node):
        self.optional_param_level += 1
        self.body.append('<span class="optional">[</span>')

    def depart_desc_optional(self, node):
        self.optional_param_level -= 1
        self.body.append('<span class="optional">]</span>')

    def visit_desc_annotation(self, node):
        self.body.append(self.starttag(node, 'em', '', CLASS='property'))

    def depart_desc_annotation(self, node):
        self.body.append('</em>')

    def visit_desc_content(self, node):
        self.body.append(self.starttag(node, 'dd', ''))

    def depart_desc_content(self, node):
        self.body.append('</dd>')

    def visit_versionmodified(self, node):
        self.body.append(self.starttag(node, 'div', CLASS=node['type']))

    def depart_versionmodified(self, node):
        self.body.append('</div>\n')

    # overwritten
    def visit_reference(self, node):
        atts = {'class': 'reference'}
        if node.get('internal') or 'refuri' not in node:
            atts['class'] += ' internal'
        else:
            atts['class'] += ' external'
        if 'refuri' in node:
            atts['href'] = node['refuri'] or '#'
            if self.settings.cloak_email_addresses and \
               atts['href'].startswith('mailto:'):
                atts['href'] = self.cloak_mailto(atts['href'])
                self.in_mailto = 1
        else:
            assert 'refid' in node, \
                   'References must have "refuri" or "refid" attribute.'
            atts['href'] = '#' + node['refid']
        if not isinstance(node.parent, nodes.TextElement):
            assert len(node) == 1 and isinstance(node[0], nodes.image)
            atts['class'] += ' image-reference'
        if 'reftitle' in node:
            atts['title'] = node['reftitle']
        self.body.append(self.starttag(node, 'a', '', **atts))

        if node.get('secnumber'):
            self.body.append(('%s' + self.secnumber_suffix) %
                             '.'.join(map(str, node['secnumber'])))

    def visit_number_reference(self, node):
        self.visit_reference(node)

    def depart_number_reference(self, node):
        self.depart_reference(node)

    # overwritten -- we don't want source comments to show up in the HTML
    def visit_comment(self, node):
        raise nodes.SkipNode

    # overwritten
    def visit_admonition(self, node, name=''):
        self.body.append(self.starttag(
            node, 'div', CLASS=('admonition ' + name)))
        if name:
            node.insert(0, nodes.title(name, admonitionlabels[name]))
        self.set_first_last(node)

    def visit_seealso(self, node):
        self.visit_admonition(node, 'seealso')

    def depart_seealso(self, node):
        self.depart_admonition(node)

    def add_secnumber(self, node):
        if node.get('secnumber'):
            self.body.append('.'.join(map(str, node['secnumber'])) +
                             self.secnumber_suffix)
        elif isinstance(node.parent, nodes.section):
            if self.builder.name == 'singlehtml':
                docname = self.docnames[-1]
                anchorname = '#' + node.parent['ids'][0]
                if (docname, anchorname) not in self.builder.secnumbers:
                    anchorname = (docname, '')  # try first heading which has no anchor
                else:
                    anchorname = (docname, anchorname)
            else:
                anchorname = '#' + node.parent['ids'][0]
                if anchorname not in self.builder.secnumbers:
                    anchorname = ''  # try first heading which has no anchor
            if self.builder.secnumbers.get(anchorname):
                numbers = self.builder.secnumbers[anchorname]
                self.body.append('.'.join(map(str, numbers)) +
                                 self.secnumber_suffix)

    def add_fignumber(self, node):
        def append_fignumber(figtype, figure_id):
            if self.builder.name == 'singlehtml':
                key = (self.docnames[-1], figtype)
            else:
                key = figtype

            if figure_id in self.builder.fignumbers.get(key, {}):
                self.body.append('<span class="caption-number">')
                prefix = self.builder.config.numfig_format.get(figtype)
                if prefix is None:
                    msg = 'numfig_format is not defined for %s' % figtype
                    self.builder.warn(msg)
                else:
                    numbers = self.builder.fignumbers[key][figure_id]
                    self.body.append(prefix % '.'.join(map(str, numbers)) + ' ')
                    self.body.append('</span>')

        figtype = self.builder.env.domains['std'].get_figtype(node)
        if figtype:
            if len(node['ids']) == 0:
                msg = 'Any IDs not assigned for %s node' % node.tagname
                self.builder.env.warn_node(msg, node)
            else:
                append_fignumber(figtype, node['ids'][0])

    def add_permalink_ref(self, node, title):
        if node['ids'] and self.permalink_text and self.builder.add_permalinks:
            format = u'<a class="headerlink" href="#%s" title="%s">%s</a>'
            self.body.append(format % (node['ids'][0], title, self.permalink_text))

    # overwritten to avoid emitting empty <ul></ul>
    def visit_bullet_list(self, node):
        if len(node) == 1 and node[0].tagname == 'toctree':
            raise nodes.SkipNode
        BaseTranslator.visit_bullet_list(self, node)

    # overwritten
    def visit_title(self, node):
        BaseTranslator.visit_title(self, node)
        self.add_secnumber(node)
        self.add_fignumber(node.parent)
        if isinstance(node.parent, nodes.table):
            self.body.append('<span class="caption-text">')

    # overwritten
    def visit_literal_block(self, node):
        if node.rawsource != node.astext():
            # most probably a parsed-literal block -- don't highlight
            return BaseTranslator.visit_literal_block(self, node)
        lang = self.highlightlang
        linenos = node.rawsource.count('\n') >= \
            self.highlightlinenothreshold - 1
        highlight_args = node.get('highlight_args', {})
        if 'language' in node:
            # code-block directives
            lang = node['language']
            highlight_args['force'] = True
        if 'linenos' in node:
            linenos = node['linenos']
        if lang is self.highlightlang_base:
            # only pass highlighter options for original language
            opts = self.highlightopts
        else:
            opts = {}

        def warner(msg):
            self.builder.warn(msg, (self.builder.current_docname, node.line))
        highlighted = self.highlighter.highlight_block(
            node.rawsource, lang, opts=opts, warn=warner, linenos=linenos,
            **highlight_args)
        starttag = self.starttag(node, 'div', suffix='',
                                 CLASS='highlight-%s' % lang)
        self.body.append(starttag + highlighted + '</div>\n')
        raise nodes.SkipNode

    def visit_caption(self, node):
        if isinstance(node.parent, nodes.container) and node.parent.get('literal_block'):
            self.body.append('<div class="code-block-caption">')
        else:
            BaseTranslator.visit_caption(self, node)
        self.add_fignumber(node.parent)
        self.body.append(self.starttag(node, 'span', '', CLASS='caption-text'))

    def depart_caption(self, node):
        self.body.append('</span>')

        # append permalink if available
        if isinstance(node.parent, nodes.container) and node.parent.get('literal_block'):
            self.add_permalink_ref(node.parent, _('Permalink to this code'))
        elif isinstance(node.parent, nodes.figure):
            image_nodes = node.parent.traverse(nodes.image)
            target_node = image_nodes and image_nodes[0] or node.parent
            self.add_permalink_ref(target_node, _('Permalink to this image'))
        elif node.parent.get('toctree'):
            self.add_permalink_ref(node.parent.parent, _('Permalink to this toctree'))

        if isinstance(node.parent, nodes.container) and node.parent.get('literal_block'):
            self.body.append('</div>\n')
        else:
            BaseTranslator.depart_caption(self, node)

    def visit_doctest_block(self, node):
        self.visit_literal_block(node)

    # overwritten to add the <div> (for XHTML compliance)
    def visit_block_quote(self, node):
        self.body.append(self.starttag(node, 'blockquote') + '<div>')

    def depart_block_quote(self, node):
        self.body.append('</div></blockquote>\n')

    # overwritten
    def visit_literal(self, node):
        self.body.append(self.starttag(node, 'code', '',
                                       CLASS='docutils literal'))
        self.protect_literal_text += 1

    def depart_literal(self, node):
        self.protect_literal_text -= 1
        self.body.append('</code>')

    def visit_productionlist(self, node):
        self.body.append(self.starttag(node, 'pre'))
        names = []
        for production in node:
            names.append(production['tokenname'])
        maxlen = max(len(name) for name in names)
        lastname = None
        for production in node:
            if production['tokenname']:
                lastname = production['tokenname'].ljust(maxlen)
                self.body.append(self.starttag(production, 'strong', ''))
                self.body.append(lastname + '</strong> ::= ')
            elif lastname is not None:
                self.body.append('%s     ' % (' '*len(lastname)))
            production.walkabout(self)
            self.body.append('\n')
        self.body.append('</pre>\n')
        raise nodes.SkipNode

    def depart_productionlist(self, node):
        pass

    def visit_production(self, node):
        pass

    def depart_production(self, node):
        pass

    def visit_centered(self, node):
        self.body.append(self.starttag(node, 'p', CLASS="centered") +
                         '<strong>')

    def depart_centered(self, node):
        self.body.append('</strong></p>')

    # overwritten
    def should_be_compact_paragraph(self, node):
        """Determine if the <p> tags around paragraph can be omitted."""
        if isinstance(node.parent, addnodes.desc_content):
            # Never compact desc_content items.
            return False
        if isinstance(node.parent, addnodes.versionmodified):
            # Never compact versionmodified nodes.
            return False
        return BaseTranslator.should_be_compact_paragraph(self, node)

    def visit_compact_paragraph(self, node):
        pass

    def depart_compact_paragraph(self, node):
        pass

    def visit_highlightlang(self, node):
        self.highlightlang = node['lang']
        self.highlightlinenothreshold = node['linenothreshold']

    def depart_highlightlang(self, node):
        pass

    def visit_download_reference(self, node):
        if node.hasattr('filename'):
            self.body.append(
                '<a class="reference download internal" href="%s" download="">' %
                posixpath.join(self.builder.dlpath, node['filename']))
            self.context.append('</a>')
        else:
            self.context.append('')

    def depart_download_reference(self, node):
        self.body.append(self.context.pop())

    # overwritten
    def visit_image(self, node):
        olduri = node['uri']
        # rewrite the URI if the environment knows about it
        if olduri in self.builder.images:
            node['uri'] = posixpath.join(self.builder.imgpath,
                                         self.builder.images[olduri])

        uri = node['uri']
        if uri.lower().endswith('svg') or uri.lower().endswith('svgz'):
            atts = {'src': uri}
            if 'width' in node:
                atts['width'] = node['width']
            if 'height' in node:
                atts['height'] = node['height']
            atts['alt'] = node.get('alt', uri)
            if 'align' in node:
                self.body.append('<div align="%s" class="align-%s">' %
                                 (node['align'], node['align']))
                self.context.append('</div>\n')
            else:
                self.context.append('')
            self.body.append(self.emptytag(node, 'img', '', **atts))
            return

        if 'scale' in node:
            # Try to figure out image height and width.  Docutils does that too,
            # but it tries the final file name, which does not necessarily exist
            # yet at the time the HTML file is written.
            if not ('width' in node and 'height' in node):
                size = get_image_size(os.path.join(self.builder.srcdir, olduri))
                if size is None:
                    self.builder.env.warn_node('Could not obtain image size. '
                                               ':scale: option is ignored.', node)
                else:
                    if 'width' not in node:
                        node['width'] = str(size[0])
                    if 'height' not in node:
                        node['height'] = str(size[1])
        BaseTranslator.visit_image(self, node)

    def visit_toctree(self, node):
        # this only happens when formatting a toc from env.tocs -- in this
        # case we don't want to include the subtree
        raise nodes.SkipNode

    def visit_index(self, node):
        raise nodes.SkipNode

    def visit_tabular_col_spec(self, node):
        raise nodes.SkipNode

    def visit_glossary(self, node):
        pass

    def depart_glossary(self, node):
        pass

    def visit_acks(self, node):
        pass

    def depart_acks(self, node):
        pass

    def visit_hlist(self, node):
        self.body.append('<table class="hlist"><tr>')

    def depart_hlist(self, node):
        self.body.append('</tr></table>\n')

    def visit_hlistcol(self, node):
        self.body.append('<td>')

    def depart_hlistcol(self, node):
        self.body.append('</td>')

    def bulk_text_processor(self, text):
        return text

    # overwritten
    def visit_Text(self, node):
        text = node.astext()
        encoded = self.encode(text)
        if self.protect_literal_text:
            # moved here from base class's visit_literal to support
            # more formatting in literal nodes
            for token in self.words_and_spaces.findall(encoded):
                if token.strip():
                    # protect literal text from line wrapping
                    self.body.append('<span class="pre">%s</span>' % token)
                elif token in ' \n':
                    # allow breaks at whitespace
                    self.body.append(token)
                else:
                    # protect runs of multiple spaces; the last one can wrap
                    self.body.append('&#160;' * (len(token)-1) + ' ')
        else:
            if self.in_mailto and self.settings.cloak_email_addresses:
                encoded = self.cloak_email(encoded)
            else:
                encoded = self.bulk_text_processor(encoded)
            self.body.append(encoded)

    def visit_note(self, node):
        self.visit_admonition(node, 'note')

    def depart_note(self, node):
        self.depart_admonition(node)

    def visit_warning(self, node):
        self.visit_admonition(node, 'warning')

    def depart_warning(self, node):
        self.depart_admonition(node)

    def visit_attention(self, node):
        self.visit_admonition(node, 'attention')

    def depart_attention(self, node):
        self.depart_admonition()

    def visit_caution(self, node):
        self.visit_admonition(node, 'caution')

    def depart_caution(self, node):
        self.depart_admonition()

    def visit_danger(self, node):
        self.visit_admonition(node, 'danger')

    def depart_danger(self, node):
        self.depart_admonition()

    def visit_error(self, node):
        self.visit_admonition(node, 'error')

    def depart_error(self, node):
        self.depart_admonition()

    def visit_hint(self, node):
        self.visit_admonition(node, 'hint')

    def depart_hint(self, node):
        self.depart_admonition()

    def visit_important(self, node):
        self.visit_admonition(node, 'important')

    def depart_important(self, node):
        self.depart_admonition()

    def visit_tip(self, node):
        self.visit_admonition(node, 'tip')

    def depart_tip(self, node):
        self.depart_admonition()

    # these are only handled specially in the SmartyPantsHTMLTranslator
    def visit_literal_emphasis(self, node):
        return self.visit_emphasis(node)

    def depart_literal_emphasis(self, node):
        return self.depart_emphasis(node)

    def visit_literal_strong(self, node):
        return self.visit_strong(node)

    def depart_literal_strong(self, node):
        return self.depart_strong(node)

    def visit_abbreviation(self, node):
        attrs = {}
        if node.hasattr('explanation'):
            attrs['title'] = node['explanation']
        self.body.append(self.starttag(node, 'abbr', '', **attrs))

    def depart_abbreviation(self, node):
        self.body.append('</abbr>')

    # overwritten (but not changed) to keep pair of visit/depart_term
    def visit_term(self, node):
        self.body.append(self.starttag(node, 'dt', ''))

    # overwritten to add '</dt>' in 'depart_term' state.
    def depart_term(self, node):
        self.body.append('</dt>\n')

    # overwritten to do not add '</dt>' in 'visit_definition' state.
    def visit_definition(self, node):
        self.body.append(self.starttag(node, 'dd', ''))
        self.set_first_last(node)

    # overwritten (but not changed) to keep pair of visit/depart_definition
    def depart_definition(self, node):
        self.body.append('</dd>\n')

    def visit_termsep(self, node):
        warnings.warn('sphinx.addnodes.termsep will be removed at Sphinx-1.5',
                      DeprecationWarning)
        self.body.append('<br />')
        raise nodes.SkipNode

    def visit_manpage(self, node):
        return self.visit_literal_emphasis(node)

    def depart_manpage(self, node):
        return self.depart_literal_emphasis(node)

    def depart_title(self, node):
        close_tag = self.context[-1]
        if (self.permalink_text and self.builder.add_permalinks and
           node.parent.hasattr('ids') and node.parent['ids']):
            # add permalink anchor
            if close_tag.startswith('</h'):
                self.add_permalink_ref(node.parent, _('Permalink to this headline'))
            elif close_tag.startswith('</a></h'):
                self.body.append(u'</a><a class="headerlink" href="#%s" ' %
                                 node.parent['ids'][0] +
                                 u'title="%s">%s' % (
                                     _('Permalink to this headline'),
                                     self.permalink_text))
            elif isinstance(node.parent, nodes.table):
                self.body.append('</span>')
                self.add_permalink_ref(node.parent, _('Permalink to this table'))

        BaseTranslator.depart_title(self, node)

    # overwritten to add even/odd classes

    def visit_table(self, node):
        self._table_row_index = 0
        return BaseTranslator.visit_table(self, node)

    def visit_row(self, node):
        self._table_row_index += 1
        if self._table_row_index % 2 == 0:
            node['classes'].append('row-even')
        else:
            node['classes'].append('row-odd')
        self.body.append(self.starttag(node, 'tr', ''))
        node.column = 0

    def visit_field_list(self, node):
        self._fieldlist_row_index = 0
        return BaseTranslator.visit_field_list(self, node)

    def visit_field(self, node):
        self._fieldlist_row_index += 1
        if self._fieldlist_row_index % 2 == 0:
            node['classes'].append('field-even')
        else:
            node['classes'].append('field-odd')
        self.body.append(self.starttag(node, 'tr', '', CLASS='field'))

    def visit_math(self, node, math_env=''):
        self.builder.warn('using "math" markup without a Sphinx math extension '
                          'active, please use one of the math extensions '
                          'described at http://sphinx-doc.org/ext/math.html',
                          (self.builder.current_docname, node.line))
        raise nodes.SkipNode

    def unknown_visit(self, node):
        raise NotImplementedError('Unknown node: ' + node.__class__.__name__)


class SmartyPantsHTMLTranslator(HTMLTranslator):
    """
    Handle ordinary text via smartypants, converting quotes and dashes
    to the correct entities.
    """

    def __init__(self, *args, **kwds):
        self.no_smarty = 0
        HTMLTranslator.__init__(self, *args, **kwds)

    def visit_literal(self, node):
        self.no_smarty += 1
        try:
            # this raises SkipNode
            HTMLTranslator.visit_literal(self, node)
        finally:
            self.no_smarty -= 1

    def visit_literal_block(self, node):
        self.no_smarty += 1
        try:
            HTMLTranslator.visit_literal_block(self, node)
        except nodes.SkipNode:
            # HTMLTranslator raises SkipNode for simple literal blocks,
            # but not for parsed literal blocks
            self.no_smarty -= 1
            raise

    def depart_literal_block(self, node):
        HTMLTranslator.depart_literal_block(self, node)
        self.no_smarty -= 1

    def visit_literal_emphasis(self, node):
        self.no_smarty += 1
        self.visit_emphasis(node)

    def depart_literal_emphasis(self, node):
        self.depart_emphasis(node)
        self.no_smarty -= 1

    def visit_literal_strong(self, node):
        self.no_smarty += 1
        self.visit_strong(node)

    def depart_literal_strong(self, node):
        self.depart_strong(node)
        self.no_smarty -= 1

    def visit_desc_signature(self, node):
        self.no_smarty += 1
        HTMLTranslator.visit_desc_signature(self, node)

    def depart_desc_signature(self, node):
        self.no_smarty -= 1
        HTMLTranslator.depart_desc_signature(self, node)

    def visit_productionlist(self, node):
        self.no_smarty += 1
        try:
            HTMLTranslator.visit_productionlist(self, node)
        finally:
            self.no_smarty -= 1

    def visit_option(self, node):
        self.no_smarty += 1
        HTMLTranslator.visit_option(self, node)

    def depart_option(self, node):
        self.no_smarty -= 1
        HTMLTranslator.depart_option(self, node)

    def bulk_text_processor(self, text):
        if self.no_smarty <= 0:
            return sphinx_smarty_pants(text)
        return text
