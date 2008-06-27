from django import template

from lib.templatetags import *

from link.models import GroupLink


register = template.Library()


@register.tag(name="load_links")
def do_load_links(parser, token):
    syntax_msg = 'Template tag syntax: load_links "SLUG_NAME" as "VAR_NAME"'

    try:
        tag, slug, _as, var_name = token.split_contents()
        if not is_string(slug) or not is_string(var_name):
            raise_syntax(syntax_msg)
    except:
        raise_syntax(syntax_msg)
    return LoadLinksNode(unquoute(slug), unquoute(var_name))


class LoadLinksNode(template.Node):
    def __init__(self, slug, var_name):
        self.slug = slug
        self.var_name = var_name

    def render(self, context):
        context[self.var_name] = GroupLink.objects.filter(group__slug=self.slug)
        return ''
