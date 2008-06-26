from django import template

from lib.templatetags import *

from article.models import Article


register = template.Library()


@register.tag(name="load_main_articles")
def do_load_main_articles(parser, token):
    return do_load(parser, token, True)


@register.tag(name="load_last_articles")
def do_load_last_articles(parser, token):
    return do_load(parser, token)


def do_load(parser, token, only_main=False):
    syntax_msg = 'Syntax: %s "COUNT" as "VAR_NAME"'

    try:
        tag, count, _as, var_name = token.split_contents()

        if not is_string(count) or not is_string(var_name):
            raise_syntax(syntax_msg % tag)
        count = int(unquoute(count))
    except:
        raise_syntax(syntax_msg % token.split_contents()[0])
    return LoadArticlesNode(count, unquoute(var_name), only_main)


class LoadArticlesNode(template.Node):
    def __init__(self, count, var_name, only_main=False):
        self.only_main = only_main
        self.count = count
        self.var_name = var_name

    def render(self, context):
        articles = Article.objects.all()
        if self.only_main:
            articles = articles.filter(main=True)

        context[self.var_name] = articles[:self.count]
        return ''
