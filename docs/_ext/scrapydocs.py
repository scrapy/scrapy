from docutils.parsers.rst.roles import set_classes
from docutils import nodes

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
