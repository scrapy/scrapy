from django import template
from django_website.apps.blog.models import Entry
import datetime

class LatestBlogEntriesNode(template.Node):
    def __init__(self, num, varname):
        self.num, self.varname = num, varname

    def render(self, context):
        context[self.varname] = list(Entry.objects.filter(pub_date__lte=datetime.datetime.now())[:self.num])
        return ''

def do_get_latest_blog_entries(parser, token):
    """
    {% get_latest_blog_entries 2 as latest_entries %}
    """
    bits = token.contents.split()
    if len(bits) != 4:
        raise template.TemplateSyntaxError, "'%s' tag takes three arguments" % bits[0]
    if bits[2] != 'as':
        raise template.TemplateSyntaxError, "First argument to '%s' tag must be 'as'" % bits[0]
    return LatestBlogEntriesNode(bits[1], bits[3])

register = template.Library()
register.tag('get_latest_blog_entries', do_get_latest_blog_entries)
