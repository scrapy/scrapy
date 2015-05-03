from docutils.parsers.rst.roles import set_classes
from docutils import nodes
from sphinx.util.compat import Directive
from sphinx.util.nodes import make_refnode


class settingslist_node(nodes.General, nodes.Element):
    pass


class SettingsListDirective(Directive):
    def run(self):
        return [settingslist_node('')]


def is_setting_node(node):
    return node.tagname == 'pending_xref' and node['reftype'] == 'setting'


def collect_scrapy_settings_refs(app, doctree):
    env = app.builder.env

    if not hasattr(env, 'scrapy_all_settings'):
        env.scrapy_all_settings = []

    for node in doctree.traverse(is_setting_node):
        try:
            targetnode = node.parent[node.parent.index(node) - 1]
            if not isinstance(targetnode, nodes.target):
                raise IndexError
        except IndexError:
            targetid = "setting-%d" % env.new_serialno('setting')
            targetnode = nodes.target('', '', ids=[targetid])
            node.replace_self([targetnode, node])

        env.scrapy_all_settings.append({
            'docname': env.docname,
            'lineno': node.line,
            'node': node.deepcopy(),
            'target': targetnode,
        })


def make_setting_element(setting_data, app, fromdocname):
    text = nodes.Text(setting_data['node'].astext())
    targetid = ''  # TODO: resolve to a proper id
    refnode = make_refnode(app.builder, fromdocname,
                           setting_data['docname'], targetid, text)

    p = nodes.paragraph()
    p.append(refnode)
    return p


def replace_settingslist_nodes(app, doctree, fromdocname):
    env = app.builder.env

    for node in doctree.traverse(settingslist_node):
        node.replace_self([make_setting_element(d, app, fromdocname)
                           for d in env.scrapy_all_settings])

def setup(app):
    app.add_crossref_type(
        directivename = "setting",
        rolename      = "setting",
        indextemplate = "pair: %s; setting",
    )
    app.add_crossref_type(
        directivename = "signal",
        rolename      = "signal",
        indextemplate = "pair: %s; signal",
    )
    app.add_crossref_type(
        directivename = "command",
        rolename      = "command",
        indextemplate = "pair: %s; command",
    )
    app.add_crossref_type(
        directivename = "reqmeta",
        rolename      = "reqmeta",
        indextemplate = "pair: %s; reqmeta",
    )
    app.add_role('source', source_role)
    app.add_role('commit', commit_role)
    app.add_role('issue', issue_role)
    app.add_role('rev', rev_role)

    app.add_node(settingslist_node)
    app.add_directive('settingslist', SettingsListDirective)

    app.connect('doctree-read', collect_scrapy_settings_refs)
    app.connect('doctree-resolved', replace_settingslist_nodes)

def source_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = 'https://github.com/scrapy/scrapy/blob/master/' + text
    set_classes(options)
    node = nodes.reference(rawtext, text, refuri=ref, **options)
    return [node], []

def issue_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = 'https://github.com/scrapy/scrapy/issues/' + text
    set_classes(options)
    node = nodes.reference(rawtext, 'issue ' + text, refuri=ref, **options)
    return [node], []

def commit_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = 'https://github.com/scrapy/scrapy/commit/' + text
    set_classes(options)
    node = nodes.reference(rawtext, 'commit ' + text, refuri=ref, **options)
    return [node], []

def rev_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = 'http://hg.scrapy.org/scrapy/changeset/' + text
    set_classes(options)
    node = nodes.reference(rawtext, 'r' + text, refuri=ref, **options)
    return [node], []
