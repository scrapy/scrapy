from zope.interface import Interface


class ISpiderLoader(Interface):
    """Interface for spider loaders, objects that locate and load the spider
    classes of the project.

    See :attr:`CrawlerRunner.spider_loader
    <scrapy.crawler.CrawlerRunner.spider_loader>`.
    """

    def from_settings(settings):
        """Return an instance of the class based on the given instance of
        :class:`Settings <scrapy.settings.Settings>`."""

    def load(spider_name):
        """Return the :class:`Spider <scrapy.Spider>` class for the given
        spider name string.

        If no match is found for `spider_name`, raise a :class:`KeyError`.
        """

    def list():
        """Return a list with the names of all spiders available in the
        project."""

    def find_by_request(request):
        """Return the list of spiders names that can handle the given
        :class:`~scrapy.http.Request` object."""
