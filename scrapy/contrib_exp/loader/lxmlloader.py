from lxml import html, etree

from scrapy.contrib.loader import ItemLoader


class LxmlItemLoader(ItemLoader):

    def __init__(self, response, item=None, **context):
        self.tree = html.fromstring(response.body_as_unicode())
        context.update(response=response)
        super(LxmlItemLoader, self).__init__(item, **context)

    def add_xpath(self, field_name, xpath):
        self.add_value(field_name, self._get_xpath(xpath))

    def replace_xpath(self, field_name, xpath):
        self.replace_value(field_name, self._get_xpath(xpath))

    def _get_xpath(self, xpath):
        return self._get_values(self.tree.xpath(xpath))

    def add_css(self, field_name, css):
        self.add_value(field_name, self._get_css(css))

    def replace_css(self, field_name, css):
        self.replace_value(field_name, self._get_css(css))

    def _get_css(self, css):
        return self._get_values(self.tree.cssselect(css))

    def _get_values(self, elems):
        for e in elems:
            yield etree.tostring(e) if isinstance(e, etree.ElementBase) else e

