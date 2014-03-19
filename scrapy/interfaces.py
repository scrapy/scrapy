from zope.interface import Interface


class ISpiderManager(Interface):

    def create(spider_name, **spider_args):
        """Returns a new Spider instance for the given spider name, and using
        the given spider arguments. If the spider name is not found, it must
        raise a KeyError."""

    def list():
        """Return a list with the names of all spiders available in the
        project"""

    def find_by_request(request):
        """Returns the list of spiders names that can handle the given request"""
