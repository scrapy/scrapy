from zope.interface import Interface


class ISpiderLoader(Interface):
    """Interface for spider loaders, objects that locate and load the spider
    classes of the project."""

    def from_settings(settings):
        """Return an instance of the class based on the given instance of
        :class:`Settings <scrapy.settings.Settings>`."""
        pass

    def load(spider_name):
        """Return the :class:`Spider <scrapy.Spider>` class for the given
        spider name string.

        If no match is found for *spider_name*, raise a :class:`KeyError`.
        """
        pass

    def list():
        """Return a list with the names of all spiders available in the
        project"""
        pass

    def find_by_request(request):
        """Return the list of spiders names that can handle the given
        :class:`Request <scrapy.Request>` instance."""
        pass