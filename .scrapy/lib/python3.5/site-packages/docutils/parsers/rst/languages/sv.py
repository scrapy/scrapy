# $Id: sv.py 7119 2011-09-02 13:00:23Z milde $
# Author: Adam Chodorowski <chodorowski@users.sourceforge.net>
# Copyright: This module has been placed in the public domain.

# New language mappings are welcome.  Before doing a new translation, please
# read <http://docutils.sf.net/docs/howto/i18n.html>.  Two files must be
# translated for each language: one in docutils/languages, the other in
# docutils/parsers/rst/languages.

"""
Swedish language mappings for language-dependent features of reStructuredText.
"""

__docformat__ = 'reStructuredText'


directives = {
      'observera': 'attention',
      'caution (translation required)': 'caution',
      'code (translation required)': 'code',
      'fara': 'danger',
      'fel': 'error',
      'v\u00e4gledning': 'hint',
      'viktigt': 'important',
      'notera': 'note',
      'tips': 'tip',
      'varning': 'warning',
      'admonition (translation required)': 'admonition',
      'sidebar (translation required)': 'sidebar',
      '\u00e4mne': 'topic',
      'line-block (translation required)': 'line-block',
      'parsed-literal (translation required)': 'parsed-literal',
      'mellanrubrik': 'rubric',
      'epigraph (translation required)': 'epigraph',
      'highlights (translation required)': 'highlights',
      'pull-quote (translation required)': 'pull-quote',
      'compound (translation required)': 'compound',
      'container (translation required)': 'container',
      # u'fr\u00e5gor': 'questions',
      # NOTE: A bit long, but recommended by http://www.nada.kth.se/dataterm/:
      # u'fr\u00e5gor-och-svar': 'questions',
      # u'vanliga-fr\u00e5gor': 'questions',  
      'table (translation required)': 'table',
      'csv-table (translation required)': 'csv-table',
      'list-table (translation required)': 'list-table',
      'meta': 'meta',
      'math (translation required)': 'math',
      # u'bildkarta': 'imagemap',   # FIXME: Translation might be too literal.
      'bild': 'image',
      'figur': 'figure',
      'inkludera': 'include',   
      'r\u00e5': 'raw',            # FIXME: Translation might be too literal.
      'ers\u00e4tt': 'replace', 
      'unicode': 'unicode',
      'datum': 'date',
      'class (translation required)': 'class',
      'role (translation required)': 'role',
      'default-role (translation required)': 'default-role',
      'title (translation required)': 'title',
      'inneh\u00e5ll': 'contents',
      'sektionsnumrering': 'sectnum',
      'target-notes (translation required)': 'target-notes',
      'header (translation required)': 'header',
      'footer (translation required)': 'footer',
      # u'fotnoter': 'footnotes',
      # u'citeringar': 'citations',
      }
"""Swedish name to registered (in directives/__init__.py) directive name
mapping."""

roles = {
      'abbreviation (translation required)': 'abbreviation',
      'acronym (translation required)': 'acronym',
      'code (translation required)': 'code',
      'index (translation required)': 'index',
      'subscript (translation required)': 'subscript',
      'superscript (translation required)': 'superscript',
      'title-reference (translation required)': 'title-reference',
      'pep-reference (translation required)': 'pep-reference',
      'rfc-reference (translation required)': 'rfc-reference',
      'emphasis (translation required)': 'emphasis',
      'strong (translation required)': 'strong',
      'literal (translation required)': 'literal',
    'math (translation required)': 'math',
      'named-reference (translation required)': 'named-reference',
      'anonymous-reference (translation required)': 'anonymous-reference',
      'footnote-reference (translation required)': 'footnote-reference',
      'citation-reference (translation required)': 'citation-reference',
      'substitution-reference (translation required)': 'substitution-reference',
      'target (translation required)': 'target',
      'uri-reference (translation required)': 'uri-reference',
      'r\u00e5': 'raw',}
"""Mapping of Swedish role names to canonical role names for interpreted text.
"""
