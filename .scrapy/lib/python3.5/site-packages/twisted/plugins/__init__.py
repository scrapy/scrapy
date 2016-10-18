# -*- test-case-name: twisted.test.test_plugin -*-
# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Plugins for services implemented in Twisted.

Plugins go in directories on your PYTHONPATH named twisted/plugins:
this is the only place where an __init__.py is necessary, thanks to
the __path__ variable.

@author: Jp Calderone
@author: Glyph Lefkowitz
"""

from twisted.plugin import pluginPackagePaths
__path__.extend(pluginPackagePaths(__name__))
__all__ = []                    # nothing to see here, move along, move along
