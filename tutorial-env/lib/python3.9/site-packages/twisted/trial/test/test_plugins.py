# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#
# Maintainer: Jonathan Lange

"""
Tests for L{twisted.plugins.twisted_trial}.
"""

from twisted.plugin import getPlugins
from twisted.trial import unittest
from twisted.trial.itrial import IReporter


class PluginsTests(unittest.SynchronousTestCase):
    """
    Tests for Trial's reporter plugins.
    """

    def getPluginsByLongOption(self, longOption):
        """
        Return the Trial reporter plugin with the given long option.

        If more than one is found, raise ValueError. If none are found, raise
        IndexError.
        """
        plugins = [
            plugin for plugin in getPlugins(IReporter) if plugin.longOpt == longOption
        ]
        if len(plugins) > 1:
            raise ValueError(
                "More than one plugin found with long option %r: %r"
                % (longOption, plugins)
            )
        return plugins[0]

    def test_subunitPlugin(self):
        """
        One of the reporter plugins is the subunit reporter plugin.
        """
        subunitPlugin = self.getPluginsByLongOption("subunit")
        self.assertEqual("Subunit Reporter", subunitPlugin.name)
        self.assertEqual("twisted.trial.reporter", subunitPlugin.module)
        self.assertEqual("subunit", subunitPlugin.longOpt)
        self.assertIdentical(None, subunitPlugin.shortOpt)
        self.assertEqual("SubunitReporter", subunitPlugin.klass)
