# -*- coding: utf-8 -*-
"""
    sphinx.util.i18n
    ~~~~~~~~~~~~~~~~

    Builder superclass for all builders.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
import gettext
import io
import os
import re
import warnings
from os import path
from datetime import datetime
from collections import namedtuple

import babel.dates
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo

from sphinx.errors import SphinxError
from sphinx.util.osutil import walk
from sphinx.util import SEP


LocaleFileInfoBase = namedtuple('CatalogInfo', 'base_dir,domain,charset')


class CatalogInfo(LocaleFileInfoBase):

    @property
    def po_file(self):
        return self.domain + '.po'

    @property
    def mo_file(self):
        return self.domain + '.mo'

    @property
    def po_path(self):
        return path.join(self.base_dir, self.po_file)

    @property
    def mo_path(self):
        return path.join(self.base_dir, self.mo_file)

    def is_outdated(self):
        return (
            not path.exists(self.mo_path) or
            path.getmtime(self.mo_path) < path.getmtime(self.po_path))

    def write_mo(self, locale):
        with io.open(self.po_path, 'rt', encoding=self.charset) as po:
            with io.open(self.mo_path, 'wb') as mo:
                write_mo(mo, read_po(po, locale))


def find_catalog(docname, compaction):
    if compaction:
        ret = docname.split(SEP, 1)[0]
    else:
        ret = docname

    return ret


def find_catalog_files(docname, srcdir, locale_dirs, lang, compaction):
    if not(lang and locale_dirs):
        return []

    domain = find_catalog(docname, compaction)
    files = [gettext.find(domain, path.join(srcdir, dir_), [lang])
             for dir_ in locale_dirs]
    files = [path.relpath(f, srcdir) for f in files if f]
    return files


def find_catalog_source_files(locale_dirs, locale, domains=None, gettext_compact=False,
                              charset='utf-8', force_all=False):
    """
    :param list locale_dirs:
       list of path as `['locale_dir1', 'locale_dir2', ...]` to find
       translation catalogs. Each path contains a structure such as
       `<locale>/LC_MESSAGES/domain.po`.
    :param str locale: a language as `'en'`
    :param list domains: list of domain names to get. If empty list or None
       is specified, get all domain names. default is None.
    :param boolean gettext_compact:
       * False: keep domains directory structure (default).
       * True: domains in the sub directory will be merged into 1 file.
    :param boolean force_all:
       Set True if you want to get all catalogs rather than updated catalogs.
       default is False.
    :return: [CatalogInfo(), ...]
    """
    if not locale:
        return []  # locale is not specified

    catalogs = set()
    for locale_dir in locale_dirs:
        if not locale_dir:
            continue  # skip system locale directory

        base_dir = path.join(locale_dir, locale, 'LC_MESSAGES')

        if not path.exists(base_dir):
            continue  # locale path is not found

        for dirpath, dirnames, filenames in walk(base_dir, followlinks=True):
            filenames = [f for f in filenames if f.endswith('.po')]
            for filename in filenames:
                base = path.splitext(filename)[0]
                domain = path.relpath(path.join(dirpath, base), base_dir)
                if gettext_compact and path.sep in domain:
                    domain = path.split(domain)[0]
                domain = domain.replace(path.sep, SEP)
                if domains and domain not in domains:
                    continue
                cat = CatalogInfo(base_dir, domain, charset)
                if force_all or cat.is_outdated():
                    catalogs.add(cat)

    return catalogs

# date_format mappings: ustrftime() to bable.dates.format_datetime()
date_format_mappings = {
    '%a': 'EEE',     # Weekday as locale’s abbreviated name.
    '%A': 'EEEE',    # Weekday as locale’s full name.
    '%b': 'MMM',     # Month as locale’s abbreviated name.
    '%B': 'MMMM',    # Month as locale’s full name.
    '%c': 'medium',  # Locale’s appropriate date and time representation.
    '%d': 'dd',      # Day of the month as a zero-padded decimal number.
    '%H': 'HH',      # Hour (24-hour clock) as a decimal number [00,23].
    '%I': 'hh',      # Hour (12-hour clock) as a decimal number [01,12].
    '%j': 'DDD',     # Day of the year as a zero-padded decimal number.
    '%m': 'MM',      # Month as a zero-padded decimal number.
    '%M': 'mm',      # Minute as a decimal number [00,59].
    '%p': 'a',       # Locale’s equivalent of either AM or PM.
    '%S': 'ss',      # Second as a decimal number.
    '%U': 'WW',      # Week number of the year (Sunday as the first day of the week)
                     # as a zero padded decimal number. All days in a new year preceding
                     # the first Sunday are considered to be in week 0.
    '%w': 'e',       # Weekday as a decimal number, where 0 is Sunday and 6 is Saturday.
    '%W': 'WW',      # Week number of the year (Monday as the first day of the week)
                     # as a decimal number. All days in a new year preceding the first
                     # Monday are considered to be in week 0.
    '%x': 'medium',  # Locale’s appropriate date representation.
    '%X': 'medium',  # Locale’s appropriate time representation.
    '%y': 'YY',      # Year without century as a zero-padded decimal number.
    '%Y': 'YYYY',    # Year with century as a decimal number.
    '%Z': 'zzzz',    # Time zone name (no characters if no time zone exists).
    '%%': '%',
}


def babel_format_date(date, format, locale, warn=None, formatter=babel.dates.format_date):
    if locale is None:
        locale = 'en'

    # Check if we have the tzinfo attribute. If not we cannot do any time
    # related formats.
    if not hasattr(date, 'tzinfo'):
        formatter = babel.dates.format_date

    try:
        return formatter(date, format, locale=locale)
    except (ValueError, babel.core.UnknownLocaleError):
        # fallback to English
        return formatter(date, format, locale='en')
    except AttributeError:
        if warn:
            warn('Invalid date format. Quote the string by single quote '
                 'if you want to output it directly: %s' % format)

        return format


def format_date(format, date=None, language=None, warn=None):
    if format is None:
        format = 'medium'

    if date is None:
        # If time is not specified, try to use $SOURCE_DATE_EPOCH variable
        # See https://wiki.debian.org/ReproducibleBuilds/TimestampsProposal
        source_date_epoch = os.getenv('SOURCE_DATE_EPOCH')
        if source_date_epoch is not None:
            date = datetime.utcfromtimestamp(float(source_date_epoch))
        else:
            date = datetime.now()

    if re.match('EEE|MMM|dd|DDD|MM|WW|medium|YY', format):
        # consider the format as babel's
        warnings.warn('LDML format support will be dropped at Sphinx-1.5',
                      DeprecationWarning)

        return babel_format_date(date, format, locale=language, warn=warn,
                                 formatter=babel.dates.format_datetime)
    else:
        # consider the format as ustrftime's and try to convert it to babel's
        result = []
        tokens = re.split('(%.)', format)
        for token in tokens:
            if token in date_format_mappings:
                babel_format = date_format_mappings.get(token, '')

                # Check if we have to use a different babel formatter then
                # format_datetime, because we only want to format a date
                # or a time.
                if token == '%x':
                    function = babel.dates.format_date
                elif token == '%X':
                    function = babel.dates.format_time
                else:
                    function = babel.dates.format_datetime

                result.append(babel_format_date(date, babel_format, locale=language,
                                                formatter=function))
            else:
                result.append(token)

        return "".join(result)


def get_image_filename_for_language(filename, env):
    if not env.config.language:
        return filename

    filename_format = env.config.figure_language_filename
    root, ext = path.splitext(filename)
    try:
        return filename_format.format(root=root, ext=ext,
                                      language=env.config.language)
    except KeyError as exc:
        raise SphinxError('Invalid figure_language_filename: %r' % exc)


def search_image_for_language(filename, env):
    if not env.config.language:
        return filename

    translated = get_image_filename_for_language(filename, env)
    dirname = path.dirname(env.docname)
    if path.exists(path.join(env.srcdir, dirname, translated)):
        return translated
    else:
        return filename
