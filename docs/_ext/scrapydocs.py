from operator import itemgetter

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.parsers.rst.roles import set_classes
from sphinx.util.nodes import make_refnode


class settingslist_node(nodes.General, nodes.Element):
    pass


class SettingsListDirective(Directive):
    def run(self):
        return [settingslist_node("")]


def is_setting_index(node):
    if node.tagname == "index" and node["entries"]:
        # index entries for setting directives look like:
        # [('pair', 'SETTING_NAME; setting', 'std:setting-SETTING_NAME', '')]
        entry_type, info, refid = node["entries"][0][:3]
        return entry_type == "pair" and info.endswith("; setting")
    return False


def get_setting_target(node):
    # target nodes are placed next to the node in the doc tree
    return node.parent[node.parent.index(node) + 1]


def get_setting_name_and_refid(node):
    """Extract setting name from directive index node"""
    entry_type, info, refid = node["entries"][0][:3]
    return info.replace("; setting", ""), refid


def collect_scrapy_settings_refs(app, doctree):
    env = app.builder.env

    if not hasattr(env, "scrapy_all_settings"):
        env.scrapy_all_settings = []

    for node in doctree.traverse(is_setting_index):
        targetnode = get_setting_target(node)
        assert isinstance(targetnode, nodes.target), "Next node is not a target"

        setting_name, refid = get_setting_name_and_refid(node)

        env.scrapy_all_settings.append(
            {
                "docname": env.docname,
                "setting_name": setting_name,
                "refid": refid,
            }
        )


def make_setting_element(setting_data, app, fromdocname):
    refnode = make_refnode(
        app.builder,
        fromdocname,
        todocname=setting_data["docname"],
        targetid=setting_data["refid"],
        child=nodes.Text(setting_data["setting_name"]),
    )
    p = nodes.paragraph()
    p += refnode

    item = nodes.list_item()
    item += p
    return item


def replace_settingslist_nodes(app, doctree, fromdocname):
    env = app.builder.env

    for node in doctree.traverse(settingslist_node):
        settings_list = nodes.bullet_list()
        settings_list.extend(
            [
                make_setting_element(d, app, fromdocname)
                for d in sorted(env.scrapy_all_settings, key=itemgetter("setting_name"))
                if fromdocname != d["docname"]
            ]
        )
        node.replace_self(settings_list)


def setup(app):
    app.add_crossref_type(
        directivename="setting",
        rolename="setting",
        indextemplate="pair: %s; setting",
    )
    app.add_crossref_type(
        directivename="signal",
        rolename="signal",
        indextemplate="pair: %s; signal",
    )
    app.add_crossref_type(
        directivename="command",
        rolename="command",
        indextemplate="pair: %s; command",
    )
    app.add_crossref_type(
        directivename="reqmeta",
        rolename="reqmeta",
        indextemplate="pair: %s; reqmeta",
    )
    app.add_role("source", source_role)
    app.add_role("commit", commit_role)
    app.add_role("issue", issue_role)
    app.add_role("rev", rev_role)

    app.add_node(settingslist_node)
    app.add_directive("settingslist", SettingsListDirective)

    app.connect("doctree-read", collect_scrapy_settings_refs)
    app.connect("doctree-resolved", replace_settingslist_nodes)


def source_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = "https://github.com/scrapy/scrapy/blob/master/" + text
    set_classes(options)
    node = nodes.reference(rawtext, text, refuri=ref, **options)
    return [node], []


def issue_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = "https://github.com/scrapy/scrapy/issues/" + text
    set_classes(options)
    node = nodes.reference(rawtext, "issue " + text, refuri=ref, **options)
    return [node], []


def commit_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = "https://github.com/scrapy/scrapy/commit/" + text
    set_classes(options)
    node = nodes.reference(rawtext, "commit " + text, refuri=ref, **options)
    return [node], []


def rev_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    ref = "http://hg.scrapy.org/scrapy/changeset/" + text
    set_classes(options)
    node = nodes.reference(rawtext, "r" + text, refuri=ref, **options)
    return [node], []
