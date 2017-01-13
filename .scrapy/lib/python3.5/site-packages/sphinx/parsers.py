# -*- coding: utf-8 -*-
"""
    sphinx.parsers
    ~~~~~~~~~~~~~~

    A Base class for additional parsers.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import docutils.parsers


class Parser(docutils.parsers.Parser):
    """
    A base class of source parsers.  The additonal parsers should inherits this class instead
    of ``docutils.parsers.Parser``.  Compared with ``docutils.parsers.Parser``, this class
    improves accessibility to Sphinx APIs.

    The subclasses can access following objects and functions:

    self.app
        The application object (:class:`sphinx.application.Sphinx`)
    self.config
        The config object (:class:`sphinx.config.Config`)
    self.env
        The environment object (:class:`sphinx.environment.BuildEnvironment`)
    self.warn()
        Emit a warning. (Same as :meth:`sphinx.application.Sphinx.warn()`)
    self.info()
        Emit a informational message. (Same as :meth:`sphinx.application.Sphinx.info()`)
    """

    def set_application(self, app):
        """set_application will be called from Sphinx to set app and other instance variables

        :param sphinx.application.Sphinx app: Sphinx application object
        """
        self.app = app
        self.config = app.config
        self.env = app.env
        self.warn = app.warn
        self.info = app.info
