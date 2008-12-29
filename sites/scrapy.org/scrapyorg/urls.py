from django.conf import settings
from django.conf.urls.defaults import *
from django.contrib import admin


admin.autodiscover()


urlpatterns = patterns('',
    # admin
    url(r"^admin/download/downloadlink/", include("scrapyorg.download.urls")),
    url(r'^admin/(.*)', admin.site.root),

    # docs
    url(r"^docs/", include("scrapyorg.docs.urls")),
    # news
    url(r"^news/", include("scrapyorg.blog.urls")),
)


if settings.DEBUG: # devel
    urlpatterns += patterns('',         
        (r'^%s/(?P<path>.*)$' % settings.MEDIA_URL[1:],
          'django.views.static.serve',
          {'document_root': settings.MEDIA_ROOT}),
    )
    
# last resort, it's an article
urlpatterns += patterns('',         
    url(r"", include("scrapyorg.article.urls")),
)
