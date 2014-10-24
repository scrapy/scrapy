import re
from six.moves.urllib.parse import urljoin

from w3lib.html import remove_tags, replace_entities, replace_escape_chars

from scrapy.link import Link
from .sgml import SgmlLinkExtractor

linkre = re.compile(
        "<a\s.*?href=(\"[.#]+?\"|\'[.#]+?\'|[^\s]+?)(>|\s.*?>)(.*?)<[/ ]?a>",
        re.DOTALL | re.IGNORECASE)

class RegexLinkExtractor(SgmlLinkExtractor):
    """High performant link extractor"""

    def _extract_links(self, response_text, response_url, response_encoding, base_url=None):
        if base_url is None:
            base_url = urljoin(response_url, self.base_url) if self.base_url else response_url
        links_text = linkre.findall(response_text)

        ret = []
        for url, _, text in links_text:
            clean_link = url.decode(response_encoding).strip("\t\r\n '\"")
            try:
                clean_url = urljoin(base_url, replace_entities(clean_link))
            except ValueError:
                continue
            clean_text = replace_escape_chars(remove_tags(text.decode(response_encoding))).strip()
            ret.append(Link(clean_url.encode(response_encoding), clean_text))

        return ret
