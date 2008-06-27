from django import template

from scrapyorg.lib.templatetags import *

from scrapyorg.download.models import DownloadLink


register = template.Library()


@register.tag(name="load_download_links")
def do_load_links(parser, token):
    syntax_msg = 'Syntax: %s "COUNT" as "VAR_NAME"'

    try:
        splited = token.split_contents()
        if len(splited) == 4:
            tag, count, _as, var_name = splited
        elif len(splited) == 3:
            tag, _as, var_name = splited
            count = None

        if count and not is_string(count) or not is_string(var_name):
            raise_syntax(syntax_msg % tag)
        count = count and int(unquoute(count)) or count
    except:
        raise_syntax(syntax_msg % token.split_contents()[0])
    return LoadLinksNode(count, unquoute(var_name))


class LoadLinksNode(template.Node):
    def __init__(self, count, var_name):
        self.count = count
        self.var_name = var_name

    def render(self, context):
        links = DownloadLink.objects.filter(public=True)[:self.count]
        context[self.var_name] = links
        return ''
