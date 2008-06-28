class ScrapedItem(object):
    """
    This is the base class for all scraped items.

    The only required attributes are:
    * guid (unique global indentifier)
    * url (URL where that item was scraped from)
    """

    def assign(self, name, value):
        """Assign an attribute. Can receive a Selector in value which will
        extract its data """

        if hasattr(value, 'extract'):
            value = value.extract()
        setattr(self, name, value)
