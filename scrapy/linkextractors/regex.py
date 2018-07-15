import re
from six.moves.urllib.parse import urljoin

from w3lib.html import remove_tags, replace_entities, replace_escape_chars, get_base_url

from scrapy.link import Link
from .sgml import SgmlLinkExtractor

linkre = re.compile(
        "<a\s.*?href=(\"[.#]+?\"|\'[.#]+?\'|[^\s]+?)(>|\s.*?>)(.*?)<[/ ]?a>",
        re.DOTALL | re.IGNORECASE)


def clean_link(link_text):
    """Remove leading and trailing whitespace and punctuation"""
    return link_text.strip("\t\r\n '\"\x0c")


class RegexLinkExtractor(SgmlLinkExtractor):
    """High performant link extractor"""

    def _extract_links(self, response_text, response_url, response_encoding, base_url=None):
        def clean_text(text):
            return replace_escape_chars(remove_tags(text.decode(response_encoding))).strip()

        def clean_url(url):
            clean_url = ''
            try:
                clean_url = urljoin(base_url, replace_entities(clean_link(url.decode(response_encoding))))
            except ValueError:
                pass
            return clean_url

        if base_url is None:
            base_url = get_base_url(response_text, response_url, response_encoding)

        links_text = linkre.findall(response_text)
        return [Link(clean_url(url).encode(response_encoding),
                     clean_text(text))
                for url, _, text in links_text]
