# -*- coding: utf-8 -*-
"""
    sphinx.errors
    ~~~~~~~~~~~~~

    Contains SphinxError and a few subclasses (in an extra module to avoid
    circular import problems).

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import traceback


class SphinxError(Exception):
    """
    Base class for Sphinx errors that are shown to the user in a nicer
    way than normal exceptions.
    """
    category = 'Sphinx error'


class SphinxWarning(SphinxError):
    """Raised for warnings if warnings are treated as errors."""
    category = 'Warning, treated as error'


class ExtensionError(SphinxError):
    """Raised if something's wrong with the configuration."""
    category = 'Extension error'

    def __init__(self, message, orig_exc=None):
        SphinxError.__init__(self, message)
        self.orig_exc = orig_exc

    def __repr__(self):
        if self.orig_exc:
            return '%s(%r, %r)' % (self.__class__.__name__,
                                   self.message, self.orig_exc)
        return '%s(%r)' % (self.__class__.__name__, self.message)

    def __str__(self):
        parent_str = SphinxError.__str__(self)
        if self.orig_exc:
            return '%s (exception: %s)' % (parent_str, self.orig_exc)
        return parent_str


class ConfigError(SphinxError):
    category = 'Configuration error'


class ThemeError(SphinxError):
    category = 'Theme error'


class VersionRequirementError(SphinxError):
    category = 'Sphinx version error'


class PycodeError(Exception):
    def __str__(self):
        res = self.args[0]
        if len(self.args) > 1:
            res += ' (exception was: %r)' % self.args[1]
        return res


class SphinxParallelError(Exception):
    def __init__(self, orig_exc, traceback):
        self.orig_exc = orig_exc
        self.traceback = traceback

    def __str__(self):
        return traceback.format_exception_only(
            self.orig_exc.__class__, self.orig_exc)[0].strip()
