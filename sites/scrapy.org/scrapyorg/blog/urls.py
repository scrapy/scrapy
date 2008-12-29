from django.conf.urls.defaults import *
from scrapyorg.blog import views as blog_views


urlpatterns = patterns('',
    url(r'^(?P<year>\d{4})/(?P<month>\w{3})/(?P<day>\d{1,2})/(?P<slug>[-\w]+)/$',
        view=blog_views.post_detail,
        name='blog_detail'),

    url(r'^(?P<year>\d{4})/(?P<month>\w{3})/(?P<day>\d{1,2})/$',
        view=blog_views.post_archive_day,
        name='blog_archive_day'),

    url(r'^(?P<year>\d{4})/(?P<month>\w{3})/$',
        view=blog_views.post_archive_month,
        name='blog_archive_month'),

    url(r'^(?P<year>\d{4})/$',
        view=blog_views.post_archive_year,
        name='blog_archive_year'),

    url(r'^categories/(?P<slug>[-\w]+)/$',
        view=blog_views.category_detail,
        name='blog_category_detail'),

    url (r'^categories/$',
        view=blog_views.category_list,
        name='blog_category_list'),

    url (r'^search/$',
        view=blog_views.search,
        name='blog_search'),

    url(r'^page/(?P<page>\w)/$',
        view=blog_views.post_list,
        name='blog_index_paginated'),

    url(r'^$',
        view=blog_views.post_list,
        name='blog_index'),
)