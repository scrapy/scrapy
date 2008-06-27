from django.contrib.syndication.feeds import Feed
from django_website.apps.blog.models import Entry
import datetime

class WeblogEntryFeed(Feed):
    title = "The Django weblog"
    link = "http://www.djangoproject.com/weblog/"
    description = "Latest news about Django, the Python Web framework."

    def items(self):
        return Entry.objects.filter(pub_date__lte=datetime.datetime.now())[:10]

    def item_pubdate(self, item):
        return item.pub_date
