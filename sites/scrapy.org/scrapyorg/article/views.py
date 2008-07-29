from os.path import join

from django.template import TemplateDoesNotExist
from django.template.context import RequestContext
from django.shortcuts import render_to_response
from django.http import Http404


ARTICLES_TEMPLATES_DIR = "articles"


def render_template(request, path):
    if not path.endswith(".html"):
        path = path + ".html"
    path = join(ARTICLES_TEMPLATES_DIR, path)

    try:
        c = RequestContext(request)
        return render_to_response(path, context_instance=c)
    except TemplateDoesNotExist, e:
        raise Http404("Article does not exists")
