# pragma: no file cover
# pylint: disable=no-method-argument,no-self-argument
import warnings

from zope.interface import Interface

from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.interfaces module is deprecated.",
    ScrapyDeprecationWarning,
    stacklevel=2,
)


class ISpiderLoader(Interface):
    def from_settings(settings):
        """Return an instance of the class for the given settings"""

    def load(spider_name):
        """Return the Spider class for the given spider name. If the spider
        name is not found, it must raise a KeyError."""

    def list():
        """Return a list with the names of all spiders available in the
        project"""

    def find_by_request(request):
        """Return the list of spiders names that can handle the given request"""
