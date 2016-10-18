# -*- coding: utf-8 -*-
"""
    sphinx.directives.patches
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.parsers.rst.directives import images


class Figure(images.Figure):
    """The figure directive which applies `:name:` option to the figure node
    instead of the image node.
    """

    def run(self):
        name = self.options.pop('name', None)
        result = images.Figure.run(self)
        if len(result) == 2 or isinstance(result[0], nodes.system_message):
            return result

        (figure_node,) = result
        if name:
            self.options['name'] = name
            self.add_name(figure_node)

        # fill lineno using image node
        if figure_node.line is None and len(figure_node) == 2:
            figure_node.line = figure_node[1].line

        return [figure_node]


directives.register_directive('figure', Figure)
