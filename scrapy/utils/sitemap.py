"""
Module for processing Sitemaps.

Note: The main purpose of this module is to provide support for the
SitemapSpider, its API is subject to change without notice.
"""
import lxml.etree as ET
from cStringIO import StringIO


def _get_tag_without_namespace(elem):
    return elem.tag.split('}', 1)[1] if '}' in elem.tag else elem.tag


class Sitemap(object):
    """Class to parse Sitemap (type=urlset) and Sitemap Index
    (type=sitemapindex) files"""

    def __init__(self, xmltext):
        io = StringIO(xmltext)

        try:
            self.xml_iterator = ET.iterparse(io,
                                             events=("start", "end", ),
                                             remove_comments=True,
                                             recover=True,
                                             )
        except TypeError:
            # previous versions of lxml don't support recover= option
            # workaround:
            start = xmltext.find('<?xml')
            if start == -1:
                raise Exception("Invalid xml file: doesn't start with '<?xml")

            io.seek(start)
            self.xml_iterator = ET.iterparse(io,
                                             events=("start", "end", ),
                                             remove_comments=True,
                                             )

        _, root = self.xml_iterator.next()
        self.type = _get_tag_without_namespace(root)

    def __iter__(self):
        for event, elem in self.xml_iterator:
            if event == "start":
                continue

            tag = _get_tag_without_namespace(elem)

            #We don't want to dig into element if it's not url or sitemap
            if tag not in ["url", "sitemap"]:
                continue

            d = {}
            for el in elem.getchildren():
                name = _get_tag_without_namespace(el)

                if name == 'link':
                    if 'href' in el.attrib:
                        d.setdefault('alternate', []).append(el.get('href'))
                else:
                    d[name] = el.text.strip() if el.text else ''

            #in the end, when element is fully processed - we just remove it
            elem.clear()
            if 'loc' in d:
                yield d


def sitemap_urls_from_robots(robots_text):
    """Return an iterator over all sitemap urls contained in the given
    robots.txt file
    """
    for line in robots_text.splitlines():
        if line.lstrip().startswith('Sitemap:'):
            yield line.split(':', 1)[1].strip()
