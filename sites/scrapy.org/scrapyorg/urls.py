from django.conf.urls.defaults import *
from django.views.generic.simple import direct_to_template
from django.conf import settings


urlpatterns = patterns('',
    (r"^weblog/", include("scrapyorg.blog.urls")),

    # admin
    (r"^admin/download/downloadlink/", include("scrapyorg.download.urls")),
    (r"^admin/", include("django.contrib.admin.urls")),
)


if settings.DEBUG: # devel
    urlpatterns += patterns('',         
        (r'^%s/(?P<path>.*)$' % settings.MEDIA_URL[1:], 'django.views.static.serve', {'document_root': settings.MEDIA_ROOT}),
    )
    
# last resort, it's an article
urlpatterns += patterns('',         
    (r"", include("scrapyorg.article.urls")),
)
