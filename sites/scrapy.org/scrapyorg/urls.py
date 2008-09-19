from django.conf import settings
from django.conf.urls.defaults import *
from django.contrib import admin


admin.autodiscover()


urlpatterns = patterns('',
    url(r"^weblog/", include("scrapyorg.blog.urls")),

    # admin
    url(r"^admin/download/downloadlink/", include("scrapyorg.download.urls")),
    url(r'^admin/(.*)', admin.site.root),
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
