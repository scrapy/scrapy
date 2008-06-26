from django.conf.urls.defaults import *
from django.views.generic.simple import direct_to_template
from django.conf import settings


urlpatterns = patterns('',
    (r"^$", direct_to_template, { "template": "home.html" }),
    (r"^article/", include("article.urls")),
    (r"^download/", include("download.urls")),
    (r"^weblog/", include("blog.urls")),

    (r"^admin/", include("django.contrib.admin.urls")),
)


if settings.DEBUG: # devel
    urlpatterns += patterns('',         
        (r"^site-media/(?P<path>.*)$", "django.views.static.serve", { "document_root": settings.MEDIA_ROOT }),
    )
