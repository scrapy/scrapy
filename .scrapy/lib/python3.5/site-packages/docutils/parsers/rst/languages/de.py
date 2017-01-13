# -*- coding: utf-8 -*-
# $Id: de.py 7223 2011-11-21 16:43:06Z milde $
# Authors: Engelbert Gruber <grubert@users.sourceforge.net>;
#          Lea Wiemann <LeWiemann@gmail.com>
# Copyright: This module has been placed in the public domain.

# New language mappings are welcome.  Before doing a new translation, please
# read <http://docutils.sf.net/docs/howto/i18n.html>.  Two files must be
# translated for each language: one in docutils/languages, the other in
# docutils/parsers/rst/languages.

"""
German-language mappings for language-dependent features of
reStructuredText.
"""

__docformat__ = 'reStructuredText'


directives = {
      'achtung': 'attention',
      'vorsicht': 'caution',
      'code': 'code',
      'gefahr': 'danger',
      'fehler': 'error',
      'hinweis': 'hint',
      'wichtig': 'important',
      'notiz': 'note',
      'tipp': 'tip',
      'warnung': 'warning',
      'ermahnung': 'admonition',
      'kasten': 'sidebar',
      'seitenkasten': 'sidebar',
      'thema': 'topic',
      'zeilen-block': 'line-block',
      'parsed-literal (translation required)': 'parsed-literal',
      'rubrik': 'rubric',
      'epigraph': 'epigraph',
      'highlights (translation required)': 'highlights',
      'pull-quote': 'pull-quote', # commonly used in German too
      'seitenansprache': 'pull-quote', # cf. http://www.typografie.info/2/wiki.php?title=Seitenansprache
      'zusammengesetzt': 'compound',
      'verbund': 'compound',
      'container': 'container',
      #'fragen': 'questions',
      'tabelle': 'table',
      'csv-tabelle': 'csv-table',
      'list-table (translation required)': 'list-table',
      'mathe': 'math',
      'formel': 'math',
      'meta': 'meta',
      #'imagemap': 'imagemap',
      'bild': 'image',
      'abbildung': 'figure',
      'unverändert': 'raw',
      'roh': 'raw',
      'einfügen': 'include',
      'ersetzung': 'replace',
      'ersetzen': 'replace',
      'ersetze': 'replace',
      'unicode': 'unicode',
      'datum': 'date',
      'klasse': 'class',
      'rolle': 'role',
      'default-role (translation required)': 'default-role',
      'title (translation required)': 'title',
      'inhalt': 'contents',
      'kapitel-nummerierung': 'sectnum',
      'abschnitts-nummerierung': 'sectnum',
      'linkziel-fußfnoten': 'target-notes',
      'header (translation required)': 'header',
      'footer (translation required)': 'footer',
      #u'fußfnoten': 'footnotes',
      #'zitate': 'citations',
      }
"""German name to registered (in directives/__init__.py) directive name
mapping."""

roles = {
      'abkürzung': 'abbreviation',
      'akronym': 'acronym',
      'code': 'code',
      'index': 'index',
      'tiefgestellt': 'subscript',
      'hochgestellt': 'superscript',
      'titel-referenz': 'title-reference',
      'pep-referenz': 'pep-reference',
      'rfc-referenz': 'rfc-reference',
      'betonung': 'emphasis',
      'fett': 'strong',
      'wörtlich': 'literal',
      'mathe': 'math',
      'benannte-referenz': 'named-reference',
      'unbenannte-referenz': 'anonymous-reference',
      'fußfnoten-referenz': 'footnote-reference',
      'zitat-referenz': 'citation-reference',
      'ersetzungs-referenz': 'substitution-reference',
      'ziel': 'target',
      'uri-referenz': 'uri-reference',
      'unverändert': 'raw',
      'roh': 'raw',}
"""Mapping of German role names to canonical role names for interpreted text.
"""
