from django.conf.urls.defaults import *

from article.views import *


urlpatterns = patterns('',
    (r"^(?P<article_id>\d+)/order/up/$", order_up),
    (r"^(?P<article_id>\d+)/order/down/$", order_down),
)
