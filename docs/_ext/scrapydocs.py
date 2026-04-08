# pylint: disable=import-error
from collections.abc import Sequence
from operator import itemgetter
from typing import Any, TypedDict

from docutils import nodes
from docutils.nodes import Element, General, Node, document
from docutils.parsers.rst import Directive
from sphinx.application import Sphinx
from sphinx.util.nodes import make_refnode


class SettingData(TypedDict):
    docname: str
    setting_name: str
    refid: str


class SettingslistNode(General, Element):
    pass


class SettingsListDirective(Directive):
    def run(self) -> Sequence[Node]:
        return [SettingslistNode()]


def is_setting_index(node: Node) -> bool:
    if node.tagname == "index" and node["entries"]:  # type: ignore[index,attr-defined]
        # index entries for setting directives look like:
        # [('pair', 'SETTING_NAME; setting', 'std:setting-SETTING_NAME', '')]
        entry_type, info, _ = node["entries"][0][:3]  # type: ignore[index]
        return entry_type == "pair" and info.endswith("; setting")
    return False


def get_setting_name_and_refid(node: Node) -> tuple[str, str]:
    """Extract setting name from directive index node"""
    _, info, refid = node["entries"][0][:3]  # type: ignore[index]
    return info.replace("; setting", ""), refid


def collect_scrapy_settings_refs(app: Sphinx, doctree: document) -> None:
    env = app.builder.env

    if not hasattr(env, "scrapy_all_settings"):
        emptyList: list[SettingData] = []
        env.scrapy_all_settings = emptyList  # type: ignore[attr-defined]

    for node in doctree.findall(is_setting_index):
        setting_name, refid = get_setting_name_and_refid(node)

        env.scrapy_all_settings.append(  # type: ignore[attr-defined]
            SettingData(
                docname=env.docname,
                setting_name=setting_name,
                refid=refid,
            )
        )


def make_setting_element(
    setting_data: SettingData, app: Sphinx, fromdocname: str
) -> Any:
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


def make_setting_markdown_item(
    setting_data: SettingData, app: Sphinx, fromdocname: str
) -> str:
    uri = app.builder.get_relative_uri(fromdocname, setting_data["docname"])
    if uri.startswith("#"):
        target = f"#{setting_data['refid']}"
    else:
        target = f"{uri}#{setting_data['refid']}"
    return f"* [{setting_data['setting_name']}]({target})"


def _iter_sorted_settings(env: Any, fromdocname: str) -> list[SettingData]:
    return [
        d
        for d in sorted(env.scrapy_all_settings, key=itemgetter("setting_name"))  # type: ignore[attr-defined]
        if fromdocname != d["docname"]
    ]


def replace_settingslist_nodes(
    app: Sphinx, doctree: document, fromdocname: str
) -> None:
    env = app.builder.env

    for node in doctree.findall(SettingslistNode):
        settings_list = nodes.bullet_list()
        settings_list.extend(
            [
                make_setting_element(d, app, fromdocname)
                for d in _iter_sorted_settings(env, fromdocname)
            ]
        )
        node.replace_self(settings_list)


def visit_settingslist_node_markdown(translator: Any, _node: Node) -> None:
    builder = translator.builder
    env = builder.env
    fromdocname = getattr(builder, "current_doc_name", env.docname)
    lines = [
        make_setting_markdown_item(setting_data, builder.app, fromdocname)
        for setting_data in _iter_sorted_settings(env, fromdocname)
    ]
    if lines:
        translator.add("\n".join(lines), prefix_eol=2, suffix_eol=2)
    raise nodes.SkipNode


def depart_settingslist_node_markdown(_translator: Any, _node: Node) -> None:
    return None


def source_role(
    name, rawtext, text: str, lineno, inliner, options=None, content=None
) -> tuple[list[Any], list[Any]]:
    ref = "https://github.com/scrapy/scrapy/blob/master/" + text
    node = nodes.reference(rawtext, text, refuri=ref, **options)
    return [node], []


def issue_role(
    name, rawtext, text: str, lineno, inliner, options=None, content=None
) -> tuple[list[Any], list[Any]]:
    ref = "https://github.com/scrapy/scrapy/issues/" + text
    node = nodes.reference(rawtext, "issue " + text, refuri=ref)
    return [node], []


def commit_role(
    name, rawtext, text: str, lineno, inliner, options=None, content=None
) -> tuple[list[Any], list[Any]]:
    ref = "https://github.com/scrapy/scrapy/commit/" + text
    node = nodes.reference(rawtext, "commit " + text, refuri=ref)
    return [node], []


def rev_role(
    name, rawtext, text: str, lineno, inliner, options=None, content=None
) -> tuple[list[Any], list[Any]]:
    ref = "http://hg.scrapy.org/scrapy/changeset/" + text
    node = nodes.reference(rawtext, "r" + text, refuri=ref)
    return [node], []


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_role("source", source_role)
    app.add_role("commit", commit_role)
    app.add_role("issue", issue_role)
    app.add_role("rev", rev_role)

    app.add_node(
        SettingslistNode,
        markdown=(visit_settingslist_node_markdown, depart_settingslist_node_markdown),
        singlemarkdown=(
            visit_settingslist_node_markdown,
            depart_settingslist_node_markdown,
        ),
    )
    app.add_directive("settingslist", SettingsListDirective)

    app.connect("doctree-read", collect_scrapy_settings_refs)
    app.connect("doctree-resolved", replace_settingslist_nodes)
    return {"parallel_read_safe": True}
