import zope.interface

class ISpiderLoader(zope.interface.Interface):

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


# ISpiderManager is deprecated, don't use it!
# An alias is kept for backwards compatibility.
ISpiderManager = ISpiderLoader


class IAddon(zope.interface.Interface):
    """Scrapy add-on"""

    name = zope.interface.Attribute("""Add-on name""")
    version = zope.interface.Attribute("""Add-on version string (PEP440)""")

    # XXX: Can methods be declared optional? I.e., can I enforce the signature
    #      but not the existence of a method?

    #def update_addons(config, addons):
    #    """Enables and configures other add-ons"""

    #def update_settings(config, settings):
    #    """Modifies `settings` to enable and configure required components"""

    #def check_configuration(config, crawler):
    #    """Performs post-initialization checks on fully configured `crawler`"""
