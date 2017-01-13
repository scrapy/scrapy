# $Id: __init__.py 7753 2014-06-24 14:52:59Z milde $
# Author: David Goodger
# Maintainer: docutils-develop@lists.sourceforge.net
# Copyright: This module has been placed in the public domain.

"""
Simple HyperText Markup Language document tree Writer.

The output conforms to the XHTML version 1.0 Transitional DTD
(*almost* strict).  The output contains a minimum of formatting
information.  The cascading style sheet "html4css1.css" is required
for proper viewing with a modern graphical browser.
"""

__docformat__ = 'reStructuredText'


import sys
import os
import os.path
import time
import re
import urllib.request, urllib.parse, urllib.error
try: # check for the Python Imaging Library
    import PIL.Image
except ImportError:
    try:  # sometimes PIL modules are put in PYTHONPATH's root
        import Image
        class PIL(object): pass  # dummy wrapper
        PIL.Image = Image
    except ImportError:
        PIL = None
import docutils
from docutils import frontend, nodes, utils, writers, languages, io
from docutils.utils.error_reporting import SafeString
from docutils.transforms import writer_aux
from docutils.utils.math import unichar2tex, pick_math_environment, math2html
from docutils.utils.math.latex2mathml import parse_latex_math

class Writer(writers.Writer):

    supported = ('html', 'html4css1', 'xhtml')
    """Formats this writer supports."""

    default_stylesheet = 'html4css1.css'
    default_stylesheet_dirs = ['.', utils.relative_path(
        os.path.join(os.getcwd(), 'dummy'), os.path.dirname(__file__))]

    default_template = 'template.txt'

    default_template_path = utils.relative_path(
        os.path.join(os.getcwd(), 'dummy'),
        os.path.join(os.path.dirname(__file__), default_template))

    settings_spec = (
        'HTML-Specific Options',
        None,
        (('Specify the template file (UTF-8 encoded).  Default is "%s".'
          % default_template_path,
          ['--template'],
          {'default': default_template_path, 'metavar': '<file>'}),
         ('Comma separated list of stylesheet URLs. '
          'Overrides previous --stylesheet and --stylesheet-path settings.',
          ['--stylesheet'],
          {'metavar': '<URL[,URL,...]>', 'overrides': 'stylesheet_path',
           'validator': frontend.validate_comma_separated_list}),
         ('Comma separated list of stylesheet paths. '
          'Relative paths are expanded if a matching file is found in '
          'the --stylesheet-dirs. With --link-stylesheet, '
          'the path is rewritten relative to the output HTML file. '
          'Default: "%s"' % default_stylesheet,
          ['--stylesheet-path'],
          {'metavar': '<file[,file,...]>', 'overrides': 'stylesheet',
           'validator': frontend.validate_comma_separated_list,
           'default': [default_stylesheet]}),
         ('Embed the stylesheet(s) in the output HTML file.  The stylesheet '
          'files must be accessible during processing. This is the default.',
          ['--embed-stylesheet'],
          {'default': 1, 'action': 'store_true',
           'validator': frontend.validate_boolean}),
         ('Link to the stylesheet(s) in the output HTML file. '
          'Default: embed stylesheets.',
          ['--link-stylesheet'],
          {'dest': 'embed_stylesheet', 'action': 'store_false'}),
         ('Comma-separated list of directories where stylesheets are found. '
          'Used by --stylesheet-path when expanding relative path arguments. '
          'Default: "%s"' % default_stylesheet_dirs,
          ['--stylesheet-dirs'],
          {'metavar': '<dir[,dir,...]>',
           'validator': frontend.validate_comma_separated_list,
           'default': default_stylesheet_dirs}),
         ('Specify the initial header level.  Default is 1 for "<h1>".  '
          'Does not affect document title & subtitle (see --no-doc-title).',
          ['--initial-header-level'],
          {'choices': '1 2 3 4 5 6'.split(), 'default': '1',
           'metavar': '<level>'}),
         ('Specify the maximum width (in characters) for one-column field '
          'names.  Longer field names will span an entire row of the table '
          'used to render the field list.  Default is 14 characters.  '
          'Use 0 for "no limit".',
          ['--field-name-limit'],
          {'default': 14, 'metavar': '<level>',
           'validator': frontend.validate_nonnegative_int}),
         ('Specify the maximum width (in characters) for options in option '
          'lists.  Longer options will span an entire row of the table used '
          'to render the option list.  Default is 14 characters.  '
          'Use 0 for "no limit".',
          ['--option-limit'],
          {'default': 14, 'metavar': '<level>',
           'validator': frontend.validate_nonnegative_int}),
         ('Format for footnote references: one of "superscript" or '
          '"brackets".  Default is "brackets".',
          ['--footnote-references'],
          {'choices': ['superscript', 'brackets'], 'default': 'brackets',
           'metavar': '<format>',
           'overrides': 'trim_footnote_reference_space'}),
         ('Format for block quote attributions: one of "dash" (em-dash '
          'prefix), "parentheses"/"parens", or "none".  Default is "dash".',
          ['--attribution'],
          {'choices': ['dash', 'parentheses', 'parens', 'none'],
           'default': 'dash', 'metavar': '<format>'}),
         ('Remove extra vertical whitespace between items of "simple" bullet '
          'lists and enumerated lists.  Default: enabled.',
          ['--compact-lists'],
          {'default': 1, 'action': 'store_true',
           'validator': frontend.validate_boolean}),
         ('Disable compact simple bullet and enumerated lists.',
          ['--no-compact-lists'],
          {'dest': 'compact_lists', 'action': 'store_false'}),
         ('Remove extra vertical whitespace between items of simple field '
          'lists.  Default: enabled.',
          ['--compact-field-lists'],
          {'default': 1, 'action': 'store_true',
           'validator': frontend.validate_boolean}),
         ('Disable compact simple field lists.',
          ['--no-compact-field-lists'],
          {'dest': 'compact_field_lists', 'action': 'store_false'}),
         ('Added to standard table classes. '
          'Defined styles: "borderless". Default: ""',
          ['--table-style'],
          {'default': ''}),
         ('Math output format, one of "MathML", "HTML", "MathJax" '
          'or "LaTeX". Default: "HTML math.css"',
          ['--math-output'],
          {'default': 'HTML math.css'}),
         ('Omit the XML declaration.  Use with caution.',
          ['--no-xml-declaration'],
          {'dest': 'xml_declaration', 'default': 1, 'action': 'store_false',
           'validator': frontend.validate_boolean}),
         ('Obfuscate email addresses to confuse harvesters while still '
          'keeping email links usable with standards-compliant browsers.',
          ['--cloak-email-addresses'],
          {'action': 'store_true', 'validator': frontend.validate_boolean}),))

    settings_defaults = {'output_encoding_error_handler': 'xmlcharrefreplace'}

    config_section = 'html4css1 writer'
    config_section_dependencies = ('writers',)

    visitor_attributes = (
        'head_prefix', 'head', 'stylesheet', 'body_prefix',
        'body_pre_docinfo', 'docinfo', 'body', 'body_suffix',
        'title', 'subtitle', 'header', 'footer', 'meta', 'fragment',
        'html_prolog', 'html_head', 'html_title', 'html_subtitle',
        'html_body')

    def get_transforms(self):
        return writers.Writer.get_transforms(self) + [writer_aux.Admonitions]

    def __init__(self):
        writers.Writer.__init__(self)
        self.translator_class = HTMLTranslator

    def translate(self):
        self.visitor = visitor = self.translator_class(self.document)
        self.document.walkabout(visitor)
        for attr in self.visitor_attributes:
            setattr(self, attr, getattr(visitor, attr))
        self.output = self.apply_template()

    def apply_template(self):
        template_file = open(self.document.settings.template, 'rb')
        template = str(template_file.read(), 'utf-8')
        template_file.close()
        subs = self.interpolation_dict()
        return template % subs

    def interpolation_dict(self):
        subs = {}
        settings = self.document.settings
        for attr in self.visitor_attributes:
            subs[attr] = ''.join(getattr(self, attr)).rstrip('\n')
        subs['encoding'] = settings.output_encoding
        subs['version'] = docutils.__version__
        return subs

    def assemble_parts(self):
        writers.Writer.assemble_parts(self)
        for part in self.visitor_attributes:
            self.parts[part] = ''.join(getattr(self, part))


class HTMLTranslator(nodes.NodeVisitor):

    """
    This HTML writer has been optimized to produce visually compact
    lists (less vertical whitespace).  HTML's mixed content models
    allow list items to contain "<li><p>body elements</p></li>" or
    "<li>just text</li>" or even "<li>text<p>and body
    elements</p>combined</li>", each with different effects.  It would
    be best to stick with strict body elements in list items, but they
    affect vertical spacing in browsers (although they really
    shouldn't).

    Here is an outline of the optimization:

    - Check for and omit <p> tags in "simple" lists: list items
      contain either a single paragraph, a nested simple list, or a
      paragraph followed by a nested simple list.  This means that
      this list can be compact:

          - Item 1.
          - Item 2.

      But this list cannot be compact:

          - Item 1.

            This second paragraph forces space between list items.

          - Item 2.

    - In non-list contexts, omit <p> tags on a paragraph if that
      paragraph is the only child of its parent (footnotes & citations
      are allowed a label first).

    - Regardless of the above, in definitions, table cells, field bodies,
      option descriptions, and list items, mark the first child with
      'class="first"' and the last child with 'class="last"'.  The stylesheet
      sets the margins (top & bottom respectively) to 0 for these elements.

    The ``no_compact_lists`` setting (``--no-compact-lists`` command-line
    option) disables list whitespace optimization.
    """

    xml_declaration = '<?xml version="1.0" encoding="%s" ?>\n'
    doctype = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"'
        ' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n')
    doctype_mathml = doctype

    head_prefix_template = ('<html xmlns="http://www.w3.org/1999/xhtml"'
                            ' xml:lang="%(lang)s" lang="%(lang)s">\n<head>\n')
    content_type = ('<meta http-equiv="Content-Type"'
                    ' content="text/html; charset=%s" />\n')
    content_type_mathml = ('<meta http-equiv="Content-Type"'
                           ' content="application/xhtml+xml; charset=%s" />\n')

    generator = ('<meta name="generator" content="Docutils %s: '
                 'http://docutils.sourceforge.net/" />\n')

    # Template for the MathJax script in the header:
    mathjax_script = '<script type="text/javascript" src="%s"></script>\n'
    # The latest version of MathJax from the distributed server:
    # avaliable to the public under the `MathJax CDN Terms of Service`__
    # __http://www.mathjax.org/download/mathjax-cdn-terms-of-service/
    mathjax_url = ('http://cdn.mathjax.org/mathjax/latest/MathJax.js?'
                   'config=TeX-AMS-MML_HTMLorMML')
    # may be overwritten by custom URL appended to "mathjax"

    stylesheet_link = '<link rel="stylesheet" href="%s" type="text/css" />\n'
    embedded_stylesheet = '<style type="text/css">\n\n%s\n</style>\n'
    words_and_spaces = re.compile(r'\S+| +|\n')
    sollbruchstelle = re.compile(r'.+\W\W.+|[-?].+', re.U) # wrap point inside word
    lang_attribute = 'lang' # name changes to 'xml:lang' in XHTML 1.1

    def __init__(self, document):
        nodes.NodeVisitor.__init__(self, document)
        self.settings = settings = document.settings
        lcode = settings.language_code
        self.language = languages.get_language(lcode, document.reporter)
        self.meta = [self.generator % docutils.__version__]
        self.head_prefix = []
        self.html_prolog = []
        if settings.xml_declaration:
            self.head_prefix.append(self.xml_declaration
                                    % settings.output_encoding)
            # encoding not interpolated:
            self.html_prolog.append(self.xml_declaration)
        self.head = self.meta[:]
        self.stylesheet = [self.stylesheet_call(path)
                           for path in utils.get_stylesheet_list(settings)]
        self.body_prefix = ['</head>\n<body>\n']
        # document title, subtitle display
        self.body_pre_docinfo = []
        # author, date, etc.
        self.docinfo = []
        self.body = []
        self.fragment = []
        self.body_suffix = ['</body>\n</html>\n']
        self.section_level = 0
        self.initial_header_level = int(settings.initial_header_level)

        self.math_output = settings.math_output.split()
        self.math_output_options = self.math_output[1:]
        self.math_output = self.math_output[0].lower()

        # A heterogenous stack used in conjunction with the tree traversal.
        # Make sure that the pops correspond to the pushes:
        self.context = []
        self.topic_classes = []
        self.colspecs = []
        self.compact_p = True
        self.compact_simple = False
        self.compact_field_list = False
        self.in_docinfo = False
        self.in_sidebar = False
        self.title = []
        self.subtitle = []
        self.header = []
        self.footer = []
        self.html_head = [self.content_type] # charset not interpolated
        self.html_title = []
        self.html_subtitle = []
        self.html_body = []
        self.in_document_title = 0   # len(self.body) or 0
        self.in_mailto = False
        self.author_in_authors = False
        self.math_header = []

    def astext(self):
        return ''.join(self.head_prefix + self.head
                       + self.stylesheet + self.body_prefix
                       + self.body_pre_docinfo + self.docinfo
                       + self.body + self.body_suffix)

    def encode(self, text):
        """Encode special characters in `text` & return."""
        # @@@ A codec to do these and all other HTML entities would be nice.
        text = str(text)
        return text.translate({
            ord('&'): '&amp;',
            ord('<'): '&lt;',
            ord('"'): '&quot;',
            ord('>'): '&gt;',
            ord('@'): '&#64;', # may thwart some address harvesters
            # TODO: convert non-breaking space only if needed?
            0xa0: '&nbsp;'}) # non-breaking space

    def cloak_mailto(self, uri):
        """Try to hide a mailto: URL from harvesters."""
        # Encode "@" using a URL octet reference (see RFC 1738).
        # Further cloaking with HTML entities will be done in the
        # `attval` function.
        return uri.replace('@', '%40')

    def cloak_email(self, addr):
        """Try to hide the link text of a email link from harversters."""
        # Surround at-signs and periods with <span> tags.  ("@" has
        # already been encoded to "&#64;" by the `encode` method.)
        addr = addr.replace('&#64;', '<span>&#64;</span>')
        addr = addr.replace('.', '<span>&#46;</span>')
        return addr

    def attval(self, text,
               whitespace=re.compile('[\n\r\t\v\f]')):
        """Cleanse, HTML encode, and return attribute value text."""
        encoded = self.encode(whitespace.sub(' ', text))
        if self.in_mailto and self.settings.cloak_email_addresses:
            # Cloak at-signs ("%40") and periods with HTML entities.
            encoded = encoded.replace('%40', '&#37;&#52;&#48;')
            encoded = encoded.replace('.', '&#46;')
        return encoded

    def stylesheet_call(self, path):
        """Return code to reference or embed stylesheet file `path`"""
        if self.settings.embed_stylesheet:
            try:
                content = io.FileInput(source_path=path,
                                       encoding='utf-8').read()
                self.settings.record_dependencies.add(path)
            except IOError as err:
                msg = "Cannot embed stylesheet '%s': %s." % (
                                path, SafeString(err.strerror))
                self.document.reporter.error(msg)
                return '<--- %s --->\n' % msg
            return self.embedded_stylesheet % content
        # else link to style file:
        if self.settings.stylesheet_path:
            # adapt path relative to output (cf. config.html#stylesheet-path)
            path = utils.relative_path(self.settings._destination, path)
        return self.stylesheet_link % self.encode(path)

    def starttag(self, node, tagname, suffix='\n', empty=False, **attributes):
        """
        Construct and return a start tag given a node (id & class attributes
        are extracted), tag name, and optional attributes.
        """
        tagname = tagname.lower()
        prefix = []
        atts = {}
        ids = []
        for (name, value) in list(attributes.items()):
            atts[name.lower()] = value
        classes = []
        languages = []
        # unify class arguments and move language specification
        for cls in node.get('classes', []) + atts.pop('class', '').split() :
            if cls.startswith('language-'):
                languages.append(cls[9:])
            elif cls.strip() and cls not in classes:
                classes.append(cls)
        if languages:
            # attribute name is 'lang' in XHTML 1.0 but 'xml:lang' in 1.1
            atts[self.lang_attribute] = languages[0]
        if classes:
            atts['class'] = ' '.join(classes)
        assert 'id' not in atts
        ids.extend(node.get('ids', []))
        if 'ids' in atts:
            ids.extend(atts['ids'])
            del atts['ids']
        if ids:
            atts['id'] = ids[0]
            for id in ids[1:]:
                # Add empty "span" elements for additional IDs.  Note
                # that we cannot use empty "a" elements because there
                # may be targets inside of references, but nested "a"
                # elements aren't allowed in XHTML (even if they do
                # not all have a "href" attribute).
                if empty:
                    # Empty tag.  Insert target right in front of element.
                    prefix.append('<span id="%s"></span>' % id)
                else:
                    # Non-empty tag.  Place the auxiliary <span> tag
                    # *inside* the element, as the first child.
                    suffix += '<span id="%s"></span>' % id
        attlist = list(atts.items())
        attlist.sort()
        parts = [tagname]
        for name, value in attlist:
            # value=None was used for boolean attributes without
            # value, but this isn't supported by XHTML.
            assert value is not None
            if isinstance(value, list):
                values = [str(v) for v in value]
                parts.append('%s="%s"' % (name.lower(),
                                          self.attval(' '.join(values))))
            else:
                parts.append('%s="%s"' % (name.lower(),
                                          self.attval(str(value))))
        if empty:
            infix = ' /'
        else:
            infix = ''
        return ''.join(prefix) + '<%s%s>' % (' '.join(parts), infix) + suffix

    def emptytag(self, node, tagname, suffix='\n', **attributes):
        """Construct and return an XML-compatible empty tag."""
        return self.starttag(node, tagname, suffix, empty=True, **attributes)

    def set_class_on_child(self, node, class_, index=0):
        """
        Set class `class_` on the visible child no. index of `node`.
        Do nothing if node has fewer children than `index`.
        """
        children = [n for n in node if not isinstance(n, nodes.Invisible)]
        try:
            child = children[index]
        except IndexError:
            return
        child['classes'].append(class_)

    def set_first_last(self, node):
        self.set_class_on_child(node, 'first', 0)
        self.set_class_on_child(node, 'last', -1)

    def visit_Text(self, node):
        text = node.astext()
        encoded = self.encode(text)
        if self.in_mailto and self.settings.cloak_email_addresses:
            encoded = self.cloak_email(encoded)
        self.body.append(encoded)

    def depart_Text(self, node):
        pass

    def visit_abbreviation(self, node):
        # @@@ implementation incomplete ("title" attribute)
        self.body.append(self.starttag(node, 'abbr', ''))

    def depart_abbreviation(self, node):
        self.body.append('</abbr>')

    def visit_acronym(self, node):
        # @@@ implementation incomplete ("title" attribute)
        self.body.append(self.starttag(node, 'acronym', ''))

    def depart_acronym(self, node):
        self.body.append('</acronym>')

    def visit_address(self, node):
        self.visit_docinfo_item(node, 'address', meta=False)
        self.body.append(self.starttag(node, 'pre', CLASS='address'))

    def depart_address(self, node):
        self.body.append('\n</pre>\n')
        self.depart_docinfo_item()

    def visit_admonition(self, node):
        self.body.append(self.starttag(node, 'div'))
        self.set_first_last(node)

    def depart_admonition(self, node=None):
        self.body.append('</div>\n')

    attribution_formats = {'dash': ('&mdash;', ''),
                           'parentheses': ('(', ')'),
                           'parens': ('(', ')'),
                           'none': ('', '')}

    def visit_attribution(self, node):
        prefix, suffix = self.attribution_formats[self.settings.attribution]
        self.context.append(suffix)
        self.body.append(
            self.starttag(node, 'p', prefix, CLASS='attribution'))

    def depart_attribution(self, node):
        self.body.append(self.context.pop() + '</p>\n')

    def visit_author(self, node):
        if isinstance(node.parent, nodes.authors):
            if self.author_in_authors:
                self.body.append('\n<br />')
        else:
            self.visit_docinfo_item(node, 'author')

    def depart_author(self, node):
        if isinstance(node.parent, nodes.authors):
            self.author_in_authors = True
        else:
            self.depart_docinfo_item()

    def visit_authors(self, node):
        self.visit_docinfo_item(node, 'authors')
        self.author_in_authors = False  # initialize

    def depart_authors(self, node):
        self.depart_docinfo_item()

    def visit_block_quote(self, node):
        self.body.append(self.starttag(node, 'blockquote'))

    def depart_block_quote(self, node):
        self.body.append('</blockquote>\n')

    def check_simple_list(self, node):
        """Check for a simple list that can be rendered compactly."""
        visitor = SimpleListChecker(self.document)
        try:
            node.walk(visitor)
        except nodes.NodeFound:
            return None
        else:
            return 1

    def is_compactable(self, node):
        return ('compact' in node['classes']
                or (self.settings.compact_lists
                    and 'open' not in node['classes']
                    and (self.compact_simple
                         or self.topic_classes == ['contents']
                         or self.check_simple_list(node))))

    def visit_bullet_list(self, node):
        atts = {}
        old_compact_simple = self.compact_simple
        self.context.append((self.compact_simple, self.compact_p))
        self.compact_p = None
        self.compact_simple = self.is_compactable(node)
        if self.compact_simple and not old_compact_simple:
            atts['class'] = 'simple'
        self.body.append(self.starttag(node, 'ul', **atts))

    def depart_bullet_list(self, node):
        self.compact_simple, self.compact_p = self.context.pop()
        self.body.append('</ul>\n')

    def visit_caption(self, node):
        self.body.append(self.starttag(node, 'p', '', CLASS='caption'))

    def depart_caption(self, node):
        self.body.append('</p>\n')

    def visit_citation(self, node):
        self.body.append(self.starttag(node, 'table',
                                       CLASS='docutils citation',
                                       frame="void", rules="none"))
        self.body.append('<colgroup><col class="label" /><col /></colgroup>\n'
                         '<tbody valign="top">\n'
                         '<tr>')
        self.footnote_backrefs(node)

    def depart_citation(self, node):
        self.body.append('</td></tr>\n'
                         '</tbody>\n</table>\n')

    def visit_citation_reference(self, node):
        href = '#'
        if 'refid' in node:
            href += node['refid']
        elif 'refname' in node:
            href += self.document.nameids[node['refname']]
        # else: # TODO system message (or already in the transform)?
        # 'Citation reference missing.'
        self.body.append(self.starttag(
            node, 'a', '[', CLASS='citation-reference', href=href))

    def depart_citation_reference(self, node):
        self.body.append(']</a>')

    def visit_classifier(self, node):
        self.body.append(' <span class="classifier-delimiter">:</span> ')
        self.body.append(self.starttag(node, 'span', '', CLASS='classifier'))

    def depart_classifier(self, node):
        self.body.append('</span>')

    def visit_colspec(self, node):
        self.colspecs.append(node)
        # "stubs" list is an attribute of the tgroup element:
        node.parent.stubs.append(node.attributes.get('stub'))

    def depart_colspec(self, node):
        pass

    def write_colspecs(self):
        width = 0
        for node in self.colspecs:
            width += node['colwidth']
        for node in self.colspecs:
            colwidth = int(node['colwidth'] * 100.0 / width + 0.5)
            self.body.append(self.emptytag(node, 'col',
                                           width='%i%%' % colwidth))
        self.colspecs = []

    def visit_comment(self, node,
                      sub=re.compile('-(?=-)').sub):
        """Escape double-dashes in comment text."""
        self.body.append('<!-- %s -->\n' % sub('- ', node.astext()))
        # Content already processed:
        raise nodes.SkipNode

    def visit_compound(self, node):
        self.body.append(self.starttag(node, 'div', CLASS='compound'))
        if len(node) > 1:
            node[0]['classes'].append('compound-first')
            node[-1]['classes'].append('compound-last')
            for child in node[1:-1]:
                child['classes'].append('compound-middle')

    def depart_compound(self, node):
        self.body.append('</div>\n')

    def visit_container(self, node):
        self.body.append(self.starttag(node, 'div', CLASS='container'))

    def depart_container(self, node):
        self.body.append('</div>\n')

    def visit_contact(self, node):
        self.visit_docinfo_item(node, 'contact', meta=False)

    def depart_contact(self, node):
        self.depart_docinfo_item()

    def visit_copyright(self, node):
        self.visit_docinfo_item(node, 'copyright')

    def depart_copyright(self, node):
        self.depart_docinfo_item()

    def visit_date(self, node):
        self.visit_docinfo_item(node, 'date')

    def depart_date(self, node):
        self.depart_docinfo_item()

    def visit_decoration(self, node):
        pass

    def depart_decoration(self, node):
        pass

    def visit_definition(self, node):
        self.body.append('</dt>\n')
        self.body.append(self.starttag(node, 'dd', ''))
        self.set_first_last(node)

    def depart_definition(self, node):
        self.body.append('</dd>\n')

    def visit_definition_list(self, node):
        self.body.append(self.starttag(node, 'dl', CLASS='docutils'))

    def depart_definition_list(self, node):
        self.body.append('</dl>\n')

    def visit_definition_list_item(self, node):
        pass

    def depart_definition_list_item(self, node):
        pass

    def visit_description(self, node):
        self.body.append(self.starttag(node, 'td', ''))
        self.set_first_last(node)

    def depart_description(self, node):
        self.body.append('</td>')

    def visit_docinfo(self, node):
        self.context.append(len(self.body))
        self.body.append(self.starttag(node, 'table',
                                       CLASS='docinfo',
                                       frame="void", rules="none"))
        self.body.append('<col class="docinfo-name" />\n'
                         '<col class="docinfo-content" />\n'
                         '<tbody valign="top">\n')
        self.in_docinfo = True

    def depart_docinfo(self, node):
        self.body.append('</tbody>\n</table>\n')
        self.in_docinfo = False
        start = self.context.pop()
        self.docinfo = self.body[start:]
        self.body = []

    def visit_docinfo_item(self, node, name, meta=True):
        if meta:
            meta_tag = '<meta name="%s" content="%s" />\n' \
                       % (name, self.attval(node.astext()))
            self.add_meta(meta_tag)
        self.body.append(self.starttag(node, 'tr', ''))
        self.body.append('<th class="docinfo-name">%s:</th>\n<td>'
                         % self.language.labels[name])
        if len(node):
            if isinstance(node[0], nodes.Element):
                node[0]['classes'].append('first')
            if isinstance(node[-1], nodes.Element):
                node[-1]['classes'].append('last')

    def depart_docinfo_item(self):
        self.body.append('</td></tr>\n')

    def visit_doctest_block(self, node):
        self.body.append(self.starttag(node, 'pre', CLASS='doctest-block'))

    def depart_doctest_block(self, node):
        self.body.append('\n</pre>\n')

    def visit_document(self, node):
        self.head.append('<title>%s</title>\n'
                         % self.encode(node.get('title', '')))

    def depart_document(self, node):
        self.head_prefix.extend([self.doctype,
                                 self.head_prefix_template %
                                 {'lang': self.settings.language_code}])
        self.html_prolog.append(self.doctype)
        self.meta.insert(0, self.content_type % self.settings.output_encoding)
        self.head.insert(0, self.content_type % self.settings.output_encoding)
        if self.math_header:
            if self.math_output == 'mathjax':
                self.head.extend(self.math_header)
            else:
                self.stylesheet.extend(self.math_header)
        # skip content-type meta tag with interpolated charset value:
        self.html_head.extend(self.head[1:])
        self.body_prefix.append(self.starttag(node, 'div', CLASS='document'))
        self.body_suffix.insert(0, '</div>\n')
        self.fragment.extend(self.body) # self.fragment is the "naked" body
        self.html_body.extend(self.body_prefix[1:] + self.body_pre_docinfo
                              + self.docinfo + self.body
                              + self.body_suffix[:-1])
        assert not self.context, 'len(context) = %s' % len(self.context)

    def visit_emphasis(self, node):
        self.body.append(self.starttag(node, 'em', ''))

    def depart_emphasis(self, node):
        self.body.append('</em>')

    def visit_entry(self, node):
        atts = {'class': []}
        if isinstance(node.parent.parent, nodes.thead):
            atts['class'].append('head')
        if node.parent.parent.parent.stubs[node.parent.column]:
            # "stubs" list is an attribute of the tgroup element
            atts['class'].append('stub')
        if atts['class']:
            tagname = 'th'
            atts['class'] = ' '.join(atts['class'])
        else:
            tagname = 'td'
            del atts['class']
        node.parent.column += 1
        if 'morerows' in node:
            atts['rowspan'] = node['morerows'] + 1
        if 'morecols' in node:
            atts['colspan'] = node['morecols'] + 1
            node.parent.column += node['morecols']
        self.body.append(self.starttag(node, tagname, '', **atts))
        self.context.append('</%s>\n' % tagname.lower())
        if len(node) == 0:              # empty cell
            self.body.append('&nbsp;')
        self.set_first_last(node)

    def depart_entry(self, node):
        self.body.append(self.context.pop())

    def visit_enumerated_list(self, node):
        """
        The 'start' attribute does not conform to HTML 4.01's strict.dtd, but
        CSS1 doesn't help. CSS2 isn't widely enough supported yet to be
        usable.
        """
        atts = {}
        if 'start' in node:
            atts['start'] = node['start']
        if 'enumtype' in node:
            atts['class'] = node['enumtype']
        # @@@ To do: prefix, suffix. How? Change prefix/suffix to a
        # single "format" attribute? Use CSS2?
        old_compact_simple = self.compact_simple
        self.context.append((self.compact_simple, self.compact_p))
        self.compact_p = None
        self.compact_simple = self.is_compactable(node)
        if self.compact_simple and not old_compact_simple:
            atts['class'] = (atts.get('class', '') + ' simple').strip()
        self.body.append(self.starttag(node, 'ol', **atts))

    def depart_enumerated_list(self, node):
        self.compact_simple, self.compact_p = self.context.pop()
        self.body.append('</ol>\n')

    def visit_field(self, node):
        self.body.append(self.starttag(node, 'tr', '', CLASS='field'))

    def depart_field(self, node):
        self.body.append('</tr>\n')

    def visit_field_body(self, node):
        self.body.append(self.starttag(node, 'td', '', CLASS='field-body'))
        self.set_class_on_child(node, 'first', 0)
        field = node.parent
        if (self.compact_field_list or
            isinstance(field.parent, nodes.docinfo) or
            field.parent.index(field) == len(field.parent) - 1):
            # If we are in a compact list, the docinfo, or if this is
            # the last field of the field list, do not add vertical
            # space after last element.
            self.set_class_on_child(node, 'last', -1)

    def depart_field_body(self, node):
        self.body.append('</td>\n')

    def visit_field_list(self, node):
        self.context.append((self.compact_field_list, self.compact_p))
        self.compact_p = None
        if 'compact' in node['classes']:
            self.compact_field_list = True
        elif (self.settings.compact_field_lists
              and 'open' not in node['classes']):
            self.compact_field_list = True
        if self.compact_field_list:
            for field in node:
                field_body = field[-1]
                assert isinstance(field_body, nodes.field_body)
                children = [n for n in field_body
                            if not isinstance(n, nodes.Invisible)]
                if not (len(children) == 0 or
                        len(children) == 1 and
                        isinstance(children[0],
                                   (nodes.paragraph, nodes.line_block))):
                    self.compact_field_list = False
                    break
        self.body.append(self.starttag(node, 'table', frame='void',
                                       rules='none',
                                       CLASS='docutils field-list'))
        self.body.append('<col class="field-name" />\n'
                         '<col class="field-body" />\n'
                         '<tbody valign="top">\n')

    def depart_field_list(self, node):
        self.body.append('</tbody>\n</table>\n')
        self.compact_field_list, self.compact_p = self.context.pop()

    def visit_field_name(self, node):
        atts = {}
        if self.in_docinfo:
            atts['class'] = 'docinfo-name'
        else:
            atts['class'] = 'field-name'
        if ( self.settings.field_name_limit
             and len(node.astext()) > self.settings.field_name_limit):
            atts['colspan'] = 2
            self.context.append('</tr>\n'
                                + self.starttag(node.parent, 'tr', '', 
                                                CLASS='field')
                                + '<td>&nbsp;</td>')
        else:
            self.context.append('')
        self.body.append(self.starttag(node, 'th', '', **atts))

    def depart_field_name(self, node):
        self.body.append(':</th>')
        self.body.append(self.context.pop())

    def visit_figure(self, node):
        atts = {'class': 'figure'}
        if node.get('width'):
            atts['style'] = 'width: %s' % node['width']
        if node.get('align'):
            atts['class'] += " align-" + node['align']
        self.body.append(self.starttag(node, 'div', **atts))

    def depart_figure(self, node):
        self.body.append('</div>\n')

    def visit_footer(self, node):
        self.context.append(len(self.body))

    def depart_footer(self, node):
        start = self.context.pop()
        footer = [self.starttag(node, 'div', CLASS='footer'),
                  '<hr class="footer" />\n']
        footer.extend(self.body[start:])
        footer.append('\n</div>\n')
        self.footer.extend(footer)
        self.body_suffix[:0] = footer
        del self.body[start:]

    def visit_footnote(self, node):
        self.body.append(self.starttag(node, 'table',
                                       CLASS='docutils footnote',
                                       frame="void", rules="none"))
        self.body.append('<colgroup><col class="label" /><col /></colgroup>\n'
                         '<tbody valign="top">\n'
                         '<tr>')
        self.footnote_backrefs(node)

    def footnote_backrefs(self, node):
        backlinks = []
        backrefs = node['backrefs']
        if self.settings.footnote_backlinks and backrefs:
            if len(backrefs) == 1:
                self.context.append('')
                self.context.append('</a>')
                self.context.append('<a class="fn-backref" href="#%s">'
                                    % backrefs[0])
            else:
                i = 1
                for backref in backrefs:
                    backlinks.append('<a class="fn-backref" href="#%s">%s</a>'
                                     % (backref, i))
                    i += 1
                self.context.append('<em>(%s)</em> ' % ', '.join(backlinks))
                self.context += ['', '']
        else:
            self.context.append('')
            self.context += ['', '']
        # If the node does not only consist of a label.
        if len(node) > 1:
            # If there are preceding backlinks, we do not set class
            # 'first', because we need to retain the top-margin.
            if not backlinks:
                node[1]['classes'].append('first')
            node[-1]['classes'].append('last')

    def depart_footnote(self, node):
        self.body.append('</td></tr>\n'
                         '</tbody>\n</table>\n')

    def visit_footnote_reference(self, node):
        href = '#' + node['refid']
        format = self.settings.footnote_references
        if format == 'brackets':
            suffix = '['
            self.context.append(']')
        else:
            assert format == 'superscript'
            suffix = '<sup>'
            self.context.append('</sup>')
        self.body.append(self.starttag(node, 'a', suffix,
                                       CLASS='footnote-reference', href=href))

    def depart_footnote_reference(self, node):
        self.body.append(self.context.pop() + '</a>')

    def visit_generated(self, node):
        pass

    def depart_generated(self, node):
        pass

    def visit_header(self, node):
        self.context.append(len(self.body))

    def depart_header(self, node):
        start = self.context.pop()
        header = [self.starttag(node, 'div', CLASS='header')]
        header.extend(self.body[start:])
        header.append('\n<hr class="header"/>\n</div>\n')
        self.body_prefix.extend(header)
        self.header.extend(header)
        del self.body[start:]

    def visit_image(self, node):
        atts = {}
        uri = node['uri']
        # place SVG and SWF images in an <object> element
        types = {'.svg': 'image/svg+xml',
                 '.swf': 'application/x-shockwave-flash'}
        ext = os.path.splitext(uri)[1].lower()
        if ext in ('.svg', '.swf'):
            atts['data'] = uri
            atts['type'] = types[ext]
        else:
            atts['src'] = uri
            atts['alt'] = node.get('alt', uri)
        # image size
        if 'width' in node:
            atts['width'] = node['width']
        if 'height' in node:
            atts['height'] = node['height']
        if 'scale' in node:
            if (PIL and not ('width' in node and 'height' in node)
                and self.settings.file_insertion_enabled):
                imagepath = urllib.request.url2pathname(uri)
                try:
                    img = PIL.Image.open(
                            imagepath.encode(sys.getfilesystemencoding()))
                except (IOError, UnicodeEncodeError):
                    pass # TODO: warn?
                else:
                    self.settings.record_dependencies.add(
                        imagepath.replace('\\', '/'))
                    if 'width' not in atts:
                        atts['width'] = '%dpx' % img.size[0]
                    if 'height' not in atts:
                        atts['height'] = '%dpx' % img.size[1]
                    del img
            for att_name in 'width', 'height':
                if att_name in atts:
                    match = re.match(r'([0-9.]+)(\S*)$', atts[att_name])
                    assert match
                    atts[att_name] = '%s%s' % (
                        float(match.group(1)) * (float(node['scale']) / 100),
                        match.group(2))
        style = []
        for att_name in 'width', 'height':
            if att_name in atts:
                if re.match(r'^[0-9.]+$', atts[att_name]):
                    # Interpret unitless values as pixels.
                    atts[att_name] += 'px'
                style.append('%s: %s;' % (att_name, atts[att_name]))
                del atts[att_name]
        if style:
            atts['style'] = ' '.join(style)
        if (isinstance(node.parent, nodes.TextElement) or
            (isinstance(node.parent, nodes.reference) and
             not isinstance(node.parent.parent, nodes.TextElement))):
            # Inline context or surrounded by <a>...</a>.
            suffix = ''
        else:
            suffix = '\n'
        if 'align' in node:
            atts['class'] = 'align-%s' % node['align']
        self.context.append('')
        if ext in ('.svg', '.swf'): # place in an object element,
            # do NOT use an empty tag: incorrect rendering in browsers
            self.body.append(self.starttag(node, 'object', suffix, **atts) +
                             node.get('alt', uri) + '</object>' + suffix)
        else:
            self.body.append(self.emptytag(node, 'img', suffix, **atts))

    def depart_image(self, node):
        self.body.append(self.context.pop())

    def visit_inline(self, node):
        self.body.append(self.starttag(node, 'span', ''))

    def depart_inline(self, node):
        self.body.append('</span>')

    def visit_label(self, node):
        # Context added in footnote_backrefs.
        self.body.append(self.starttag(node, 'td', '%s[' % self.context.pop(),
                                       CLASS='label'))

    def depart_label(self, node):
        # Context added in footnote_backrefs.
        self.body.append(']%s</td><td>%s' % (self.context.pop(), self.context.pop()))

    def visit_legend(self, node):
        self.body.append(self.starttag(node, 'div', CLASS='legend'))

    def depart_legend(self, node):
        self.body.append('</div>\n')

    def visit_line(self, node):
        self.body.append(self.starttag(node, 'div', suffix='', CLASS='line'))
        if not len(node):
            self.body.append('<br />')

    def depart_line(self, node):
        self.body.append('</div>\n')

    def visit_line_block(self, node):
        self.body.append(self.starttag(node, 'div', CLASS='line-block'))

    def depart_line_block(self, node):
        self.body.append('</div>\n')

    def visit_list_item(self, node):
        self.body.append(self.starttag(node, 'li', ''))
        if len(node):
            node[0]['classes'].append('first')

    def depart_list_item(self, node):
        self.body.append('</li>\n')

    def visit_literal(self, node):
        # special case: "code" role
        classes = node.get('classes', [])
        if 'code' in classes:
            # filter 'code' from class arguments
            node['classes'] = [cls for cls in classes if cls != 'code']
            self.body.append(self.starttag(node, 'code', ''))
            return
        self.body.append(
            self.starttag(node, 'tt', '', CLASS='docutils literal'))
        text = node.astext()
        for token in self.words_and_spaces.findall(text):
            if token.strip():
                # Protect text like "--an-option" and the regular expression
                # ``[+]?(\d+(\.\d*)?|\.\d+)`` from bad line wrapping
                if self.sollbruchstelle.search(token):
                    self.body.append('<span class="pre">%s</span>'
                                     % self.encode(token))
                else:
                    self.body.append(self.encode(token))
            elif token in ('\n', ' '):
                # Allow breaks at whitespace:
                self.body.append(token)
            else:
                # Protect runs of multiple spaces; the last space can wrap:
                self.body.append('&nbsp;' * (len(token) - 1) + ' ')
        self.body.append('</tt>')
        # Content already processed:
        raise nodes.SkipNode

    def depart_literal(self, node):
        # skipped unless literal element is from "code" role:
        self.body.append('</code>')

    def visit_literal_block(self, node):
        self.body.append(self.starttag(node, 'pre', CLASS='literal-block'))

    def depart_literal_block(self, node):
        self.body.append('\n</pre>\n')

    def visit_math(self, node, math_env=''):
        # If the method is called from visit_math_block(), math_env != ''.

        # As there is no native HTML math support, we provide alternatives:
        # LaTeX and MathJax math_output modes simply wrap the content,
        # HTML and MathML math_output modes also convert the math_code.
        if self.math_output not in ('mathml', 'html', 'mathjax', 'latex'):
            self.document.reporter.error(
                'math-output format "%s" not supported '
                'falling back to "latex"'% self.math_output)
            self.math_output = 'latex'
        #
        # HTML container
        tags = {# math_output: (block, inline, class-arguments)
                'mathml':      ('div', '', ''),
                'html':        ('div', 'span', 'formula'),
                'mathjax':     ('div', 'span', 'math'),
                'latex':       ('pre', 'tt',   'math'),
               }
        tag = tags[self.math_output][math_env == '']
        clsarg = tags[self.math_output][2]
        # LaTeX container
        wrappers = {# math_mode: (inline, block)
                    'mathml':  (None,     None),
                    'html':    ('$%s$',   '\\begin{%s}\n%s\n\\end{%s}'),
                    'mathjax': ('\(%s\)', '\\begin{%s}\n%s\n\\end{%s}'),
                    'latex':   (None,     None),
                   }
        wrapper = wrappers[self.math_output][math_env != '']
        # get and wrap content
        math_code = node.astext().translate(unichar2tex.uni2tex_table)
        if wrapper and math_env:
            math_code = wrapper % (math_env, math_code, math_env)
        elif wrapper:
            math_code = wrapper % math_code
        # settings and conversion
        if self.math_output in ('latex', 'mathjax'):
            math_code = self.encode(math_code)
        if self.math_output == 'mathjax' and not self.math_header:
            if self.math_output_options:
                self.mathjax_url = self.math_output_options[0]
            self.math_header = [self.mathjax_script % self.mathjax_url]
        elif self.math_output == 'html':
            if self.math_output_options and not self.math_header:
                self.math_header = [self.stylesheet_call(
                    utils.find_file_in_dirs(s, self.settings.stylesheet_dirs))
                    for s in self.math_output_options[0].split(',')]
            # TODO: fix display mode in matrices and fractions
            math2html.DocumentParameters.displaymode = (math_env != '')
            math_code = math2html.math2html(math_code)
        elif self.math_output == 'mathml':
            self.doctype = self.doctype_mathml
            self.content_type = self.content_type_mathml
            try:
                mathml_tree = parse_latex_math(math_code, inline=not(math_env))
                math_code = ''.join(mathml_tree.xml())
            except SyntaxError as err:
                err_node = self.document.reporter.error(err, base_node=node)
                self.visit_system_message(err_node)
                self.body.append(self.starttag(node, 'p'))
                self.body.append(','.join(err.args))
                self.body.append('</p>\n')
                self.body.append(self.starttag(node, 'pre',
                                               CLASS='literal-block'))
                self.body.append(self.encode(math_code))
                self.body.append('\n</pre>\n')
                self.depart_system_message(err_node)
                raise nodes.SkipNode
        # append to document body
        if tag:
            self.body.append(self.starttag(node, tag,
                                           suffix='\n'*bool(math_env),
                                           CLASS=clsarg))
        self.body.append(math_code)
        if math_env: # block mode (equation, display)
            self.body.append('\n')
        if tag:
            self.body.append('</%s>' % tag)
        if math_env:
            self.body.append('\n')
        # Content already processed:
        raise nodes.SkipNode

    def depart_math(self, node):
        pass # never reached

    def visit_math_block(self, node):
        # print node.astext().encode('utf8')
        math_env = pick_math_environment(node.astext())
        self.visit_math(node, math_env=math_env)

    def depart_math_block(self, node):
        pass # never reached

    def visit_meta(self, node):
        meta = self.emptytag(node, 'meta', **node.non_default_attributes())
        self.add_meta(meta)

    def depart_meta(self, node):
        pass

    def add_meta(self, tag):
        self.meta.append(tag)
        self.head.append(tag)

    def visit_option(self, node):
        if self.context[-1]:
            self.body.append(', ')
        self.body.append(self.starttag(node, 'span', '', CLASS='option'))

    def depart_option(self, node):
        self.body.append('</span>')
        self.context[-1] += 1

    def visit_option_argument(self, node):
        self.body.append(node.get('delimiter', ' '))
        self.body.append(self.starttag(node, 'var', ''))

    def depart_option_argument(self, node):
        self.body.append('</var>')

    def visit_option_group(self, node):
        atts = {}
        if ( self.settings.option_limit
             and len(node.astext()) > self.settings.option_limit):
            atts['colspan'] = 2
            self.context.append('</tr>\n<tr><td>&nbsp;</td>')
        else:
            self.context.append('')
        self.body.append(
            self.starttag(node, 'td', CLASS='option-group', **atts))
        self.body.append('<kbd>')
        self.context.append(0)          # count number of options

    def depart_option_group(self, node):
        self.context.pop()
        self.body.append('</kbd></td>\n')
        self.body.append(self.context.pop())

    def visit_option_list(self, node):
        self.body.append(
              self.starttag(node, 'table', CLASS='docutils option-list',
                            frame="void", rules="none"))
        self.body.append('<col class="option" />\n'
                         '<col class="description" />\n'
                         '<tbody valign="top">\n')

    def depart_option_list(self, node):
        self.body.append('</tbody>\n</table>\n')

    def visit_option_list_item(self, node):
        self.body.append(self.starttag(node, 'tr', ''))

    def depart_option_list_item(self, node):
        self.body.append('</tr>\n')

    def visit_option_string(self, node):
        pass

    def depart_option_string(self, node):
        pass

    def visit_organization(self, node):
        self.visit_docinfo_item(node, 'organization')

    def depart_organization(self, node):
        self.depart_docinfo_item()

    def should_be_compact_paragraph(self, node):
        """
        Determine if the <p> tags around paragraph ``node`` can be omitted.
        """
        if (isinstance(node.parent, nodes.document) or
            isinstance(node.parent, nodes.compound)):
            # Never compact paragraphs in document or compound.
            return False
        for key, value in node.attlist():
            if (node.is_not_default(key) and
                not (key == 'classes' and value in
                     ([], ['first'], ['last'], ['first', 'last']))):
                # Attribute which needs to survive.
                return False
        first = isinstance(node.parent[0], nodes.label) # skip label
        for child in node.parent.children[first:]:
            # only first paragraph can be compact
            if isinstance(child, nodes.Invisible):
                continue
            if child is node:
                break
            return False
        parent_length = len([n for n in node.parent if not isinstance(
            n, (nodes.Invisible, nodes.label))])
        if ( self.compact_simple
             or self.compact_field_list
             or self.compact_p and parent_length == 1):
            return True
        return False

    def visit_paragraph(self, node):
        if self.should_be_compact_paragraph(node):
            self.context.append('')
        else:
            self.body.append(self.starttag(node, 'p', ''))
            self.context.append('</p>\n')

    def depart_paragraph(self, node):
        self.body.append(self.context.pop())

    def visit_problematic(self, node):
        if node.hasattr('refid'):
            self.body.append('<a href="#%s">' % node['refid'])
            self.context.append('</a>')
        else:
            self.context.append('')
        self.body.append(self.starttag(node, 'span', '', CLASS='problematic'))

    def depart_problematic(self, node):
        self.body.append('</span>')
        self.body.append(self.context.pop())

    def visit_raw(self, node):
        if 'html' in node.get('format', '').split():
            t = isinstance(node.parent, nodes.TextElement) and 'span' or 'div'
            if node['classes']:
                self.body.append(self.starttag(node, t, suffix=''))
            self.body.append(node.astext())
            if node['classes']:
                self.body.append('</%s>' % t)
        # Keep non-HTML raw text out of output:
        raise nodes.SkipNode

    def visit_reference(self, node):
        atts = {'class': 'reference'}
        if 'refuri' in node:
            atts['href'] = node['refuri']
            if ( self.settings.cloak_email_addresses
                 and atts['href'].startswith('mailto:')):
                atts['href'] = self.cloak_mailto(atts['href'])
                self.in_mailto = True
            atts['class'] += ' external'
        else:
            assert 'refid' in node, \
                   'References must have "refuri" or "refid" attribute.'
            atts['href'] = '#' + node['refid']
            atts['class'] += ' internal'
        if not isinstance(node.parent, nodes.TextElement):
            assert len(node) == 1 and isinstance(node[0], nodes.image)
            atts['class'] += ' image-reference'
        self.body.append(self.starttag(node, 'a', '', **atts))

    def depart_reference(self, node):
        self.body.append('</a>')
        if not isinstance(node.parent, nodes.TextElement):
            self.body.append('\n')
        self.in_mailto = False

    def visit_revision(self, node):
        self.visit_docinfo_item(node, 'revision', meta=False)

    def depart_revision(self, node):
        self.depart_docinfo_item()

    def visit_row(self, node):
        self.body.append(self.starttag(node, 'tr', ''))
        node.column = 0

    def depart_row(self, node):
        self.body.append('</tr>\n')

    def visit_rubric(self, node):
        self.body.append(self.starttag(node, 'p', '', CLASS='rubric'))

    def depart_rubric(self, node):
        self.body.append('</p>\n')

    def visit_section(self, node):
        self.section_level += 1
        self.body.append(
            self.starttag(node, 'div', CLASS='section'))

    def depart_section(self, node):
        self.section_level -= 1
        self.body.append('</div>\n')

    def visit_sidebar(self, node):
        self.body.append(
            self.starttag(node, 'div', CLASS='sidebar'))
        self.set_first_last(node)
        self.in_sidebar = True

    def depart_sidebar(self, node):
        self.body.append('</div>\n')
        self.in_sidebar = False

    def visit_status(self, node):
        self.visit_docinfo_item(node, 'status', meta=False)

    def depart_status(self, node):
        self.depart_docinfo_item()

    def visit_strong(self, node):
        self.body.append(self.starttag(node, 'strong', ''))

    def depart_strong(self, node):
        self.body.append('</strong>')

    def visit_subscript(self, node):
        self.body.append(self.starttag(node, 'sub', ''))

    def depart_subscript(self, node):
        self.body.append('</sub>')

    def visit_substitution_definition(self, node):
        """Internal only."""
        raise nodes.SkipNode

    def visit_substitution_reference(self, node):
        self.unimplemented_visit(node)

    def visit_subtitle(self, node):
        if isinstance(node.parent, nodes.sidebar):
            self.body.append(self.starttag(node, 'p', '',
                                           CLASS='sidebar-subtitle'))
            self.context.append('</p>\n')
        elif isinstance(node.parent, nodes.document):
            self.body.append(self.starttag(node, 'h2', '', CLASS='subtitle'))
            self.context.append('</h2>\n')
            self.in_document_title = len(self.body)
        elif isinstance(node.parent, nodes.section):
            tag = 'h%s' % (self.section_level + self.initial_header_level - 1)
            self.body.append(
                self.starttag(node, tag, '', CLASS='section-subtitle') +
                self.starttag({}, 'span', '', CLASS='section-subtitle'))
            self.context.append('</span></%s>\n' % tag)

    def depart_subtitle(self, node):
        self.body.append(self.context.pop())
        if self.in_document_title:
            self.subtitle = self.body[self.in_document_title:-1]
            self.in_document_title = 0
            self.body_pre_docinfo.extend(self.body)
            self.html_subtitle.extend(self.body)
            del self.body[:]

    def visit_superscript(self, node):
        self.body.append(self.starttag(node, 'sup', ''))

    def depart_superscript(self, node):
        self.body.append('</sup>')

    def visit_system_message(self, node):
        self.body.append(self.starttag(node, 'div', CLASS='system-message'))
        self.body.append('<p class="system-message-title">')
        backref_text = ''
        if len(node['backrefs']):
            backrefs = node['backrefs']
            if len(backrefs) == 1:
                backref_text = ('; <em><a href="#%s">backlink</a></em>'
                                % backrefs[0])
            else:
                i = 1
                backlinks = []
                for backref in backrefs:
                    backlinks.append('<a href="#%s">%s</a>' % (backref, i))
                    i += 1
                backref_text = ('; <em>backlinks: %s</em>'
                                % ', '.join(backlinks))
        if node.hasattr('line'):
            line = ', line %s' % node['line']
        else:
            line = ''
        self.body.append('System Message: %s/%s '
                         '(<tt class="docutils">%s</tt>%s)%s</p>\n'
                         % (node['type'], node['level'],
                            self.encode(node['source']), line, backref_text))

    def depart_system_message(self, node):
        self.body.append('</div>\n')

    def visit_table(self, node):
        self.context.append(self.compact_p)
        self.compact_p = True
        classes = ' '.join(['docutils', self.settings.table_style]).strip()
        self.body.append(
            self.starttag(node, 'table', CLASS=classes, border="1"))

    def depart_table(self, node):
        self.compact_p = self.context.pop()
        self.body.append('</table>\n')

    def visit_target(self, node):
        if not ('refuri' in node or 'refid' in node
                or 'refname' in node):
            self.body.append(self.starttag(node, 'span', '', CLASS='target'))
            self.context.append('</span>')
        else:
            self.context.append('')

    def depart_target(self, node):
        self.body.append(self.context.pop())

    def visit_tbody(self, node):
        self.write_colspecs()
        self.body.append(self.context.pop()) # '</colgroup>\n' or ''
        self.body.append(self.starttag(node, 'tbody', valign='top'))

    def depart_tbody(self, node):
        self.body.append('</tbody>\n')

    def visit_term(self, node):
        self.body.append(self.starttag(node, 'dt', ''))

    def depart_term(self, node):
        """
        Leave the end tag to `self.visit_definition()`, in case there's a
        classifier.
        """
        pass

    def visit_tgroup(self, node):
        # Mozilla needs <colgroup>:
        self.body.append(self.starttag(node, 'colgroup'))
        # Appended by thead or tbody:
        self.context.append('</colgroup>\n')
        node.stubs = []

    def depart_tgroup(self, node):
        pass

    def visit_thead(self, node):
        self.write_colspecs()
        self.body.append(self.context.pop()) # '</colgroup>\n'
        # There may or may not be a <thead>; this is for <tbody> to use:
        self.context.append('')
        self.body.append(self.starttag(node, 'thead', valign='bottom'))

    def depart_thead(self, node):
        self.body.append('</thead>\n')

    def visit_title(self, node):
        """Only 6 section levels are supported by HTML."""
        check_id = 0  # TODO: is this a bool (False) or a counter?
        close_tag = '</p>\n'
        if isinstance(node.parent, nodes.topic):
            self.body.append(
                  self.starttag(node, 'p', '', CLASS='topic-title first'))
        elif isinstance(node.parent, nodes.sidebar):
            self.body.append(
                  self.starttag(node, 'p', '', CLASS='sidebar-title'))
        elif isinstance(node.parent, nodes.Admonition):
            self.body.append(
                  self.starttag(node, 'p', '', CLASS='admonition-title'))
        elif isinstance(node.parent, nodes.table):
            self.body.append(
                  self.starttag(node, 'caption', ''))
            close_tag = '</caption>\n'
        elif isinstance(node.parent, nodes.document):
            self.body.append(self.starttag(node, 'h1', '', CLASS='title'))
            close_tag = '</h1>\n'
            self.in_document_title = len(self.body)
        else:
            assert isinstance(node.parent, nodes.section)
            h_level = self.section_level + self.initial_header_level - 1
            atts = {}
            if (len(node.parent) >= 2 and
                isinstance(node.parent[1], nodes.subtitle)):
                atts['CLASS'] = 'with-subtitle'
            self.body.append(
                  self.starttag(node, 'h%s' % h_level, '', **atts))
            atts = {}
            if node.hasattr('refid'):
                atts['class'] = 'toc-backref'
                atts['href'] = '#' + node['refid']
            if atts:
                self.body.append(self.starttag({}, 'a', '', **atts))
                close_tag = '</a></h%s>\n' % (h_level)
            else:
                close_tag = '</h%s>\n' % (h_level)
        self.context.append(close_tag)

    def depart_title(self, node):
        self.body.append(self.context.pop())
        if self.in_document_title:
            self.title = self.body[self.in_document_title:-1]
            self.in_document_title = 0
            self.body_pre_docinfo.extend(self.body)
            self.html_title.extend(self.body)
            del self.body[:]

    def visit_title_reference(self, node):
        self.body.append(self.starttag(node, 'cite', ''))

    def depart_title_reference(self, node):
        self.body.append('</cite>')

    def visit_topic(self, node):
        self.body.append(self.starttag(node, 'div', CLASS='topic'))
        self.topic_classes = node['classes']

    def depart_topic(self, node):
        self.body.append('</div>\n')
        self.topic_classes = []

    def visit_transition(self, node):
        self.body.append(self.emptytag(node, 'hr', CLASS='docutils'))

    def depart_transition(self, node):
        pass

    def visit_version(self, node):
        self.visit_docinfo_item(node, 'version', meta=False)

    def depart_version(self, node):
        self.depart_docinfo_item()

    def unimplemented_visit(self, node):
        raise NotImplementedError('visiting unimplemented node type: %s'
                                  % node.__class__.__name__)


class SimpleListChecker(nodes.GenericNodeVisitor):

    """
    Raise `nodes.NodeFound` if non-simple list item is encountered.

    Here "simple" means a list item containing nothing other than a single
    paragraph, a simple list, or a paragraph followed by a simple list.
    """

    def default_visit(self, node):
        raise nodes.NodeFound

    def visit_bullet_list(self, node):
        pass

    def visit_enumerated_list(self, node):
        pass

    def visit_list_item(self, node):
        children = []
        for child in node.children:
            if not isinstance(child, nodes.Invisible):
                children.append(child)
        if (children and isinstance(children[0], nodes.paragraph)
            and (isinstance(children[-1], nodes.bullet_list)
                 or isinstance(children[-1], nodes.enumerated_list))):
            children.pop()
        if len(children) <= 1:
            return
        else:
            raise nodes.NodeFound

    def visit_paragraph(self, node):
        raise nodes.SkipNode

    def invisible_visit(self, node):
        """Invisible nodes should be ignored."""
        raise nodes.SkipNode

    visit_comment = invisible_visit
    visit_substitution_definition = invisible_visit
    visit_target = invisible_visit
    visit_pending = invisible_visit
