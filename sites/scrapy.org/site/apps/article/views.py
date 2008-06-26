from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect

from article.models import Article


def order_up(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    article.order_up()
    return HttpResponseRedirect("/admin/article/article/")


def order_down(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    article.order_down()
    return HttpResponseRedirect("/admin/article/article/")
