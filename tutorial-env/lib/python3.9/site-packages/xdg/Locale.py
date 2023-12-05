"""
Helper Module for Locale settings

This module is based on a ROX module (LGPL):

http://cvs.sourceforge.net/viewcvs.py/rox/ROX-Lib2/python/rox/i18n.py?rev=1.3&view=log
"""

import os
from locale import normalize

regex = r"(\[([a-zA-Z]+)(_[a-zA-Z]+)?(\.[a-zA-Z0-9-]+)?(@[a-zA-Z]+)?\])?"

def _expand_lang(locale):
    locale = normalize(locale)
    COMPONENT_CODESET   = 1 << 0
    COMPONENT_MODIFIER  = 1 << 1
    COMPONENT_TERRITORY = 1 << 2
    # split up the locale into its base components
    mask = 0
    pos = locale.find('@')
    if pos >= 0:
        modifier = locale[pos:]
        locale = locale[:pos]
        mask |= COMPONENT_MODIFIER
    else:
        modifier = ''
    pos = locale.find('.')
    codeset = ''
    if pos >= 0:
        locale = locale[:pos]
    pos = locale.find('_')
    if pos >= 0:
        territory = locale[pos:]
        locale = locale[:pos]
        mask |= COMPONENT_TERRITORY
    else:
        territory = ''
    language = locale
    ret = []
    for i in range(mask+1):
        if not (i & ~mask):  # if all components for this combo exist ...
            val = language
            if i & COMPONENT_TERRITORY: val += territory
            if i & COMPONENT_CODESET:   val += codeset
            if i & COMPONENT_MODIFIER:  val += modifier
            ret.append(val)
    ret.reverse()
    return ret

def expand_languages(languages=None):
    # Get some reasonable defaults for arguments that were not supplied
    if languages is None:
        languages = []
        for envar in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
            val = os.environ.get(envar)
            if val:
                languages = val.split(':')
                break
    #if 'C' not in languages:
    #   languages.append('C')

    # now normalize and expand the languages
    nelangs = []
    for lang in languages:
        for nelang in _expand_lang(lang):
            if nelang not in nelangs:
                nelangs.append(nelang)
    return nelangs

def update(language=None):
    global langs
    if language:
        langs = expand_languages([language])
    else:
        langs = expand_languages()

langs = []
update()
