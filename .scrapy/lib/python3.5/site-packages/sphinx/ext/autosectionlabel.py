# -*- coding: utf-8 -*-
"""
    sphinx.ext.autosectionlabel
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Allow reference sections by :ref: role using its title.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from docutils import nodes
from sphinx.util.nodes import clean_astext


def register_sections_as_label(app, document):
    labels = app.env.domaindata['std']['labels']
    anonlabels = app.env.domaindata['std']['anonlabels']
    for node in document.traverse(nodes.section):
        name = nodes.fully_normalize_name(node[0].astext())
        labelid = node['ids'][0]
        docname = app.env.docname
        sectname = clean_astext(node[0])

        if name in labels:
            app.env.warn_node('duplicate label %s, ' % name + 'other instance '
                              'in ' + app.env.doc2path(labels[name][0]), node)

        anonlabels[name] = docname, labelid
        labels[name] = docname, labelid, sectname


def setup(app):
    app.connect('doctree-read', register_sections_as_label)
