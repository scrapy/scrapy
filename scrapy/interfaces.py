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
    def from_settings(settings): ...

    def load(spider_name): ...

    def list(): ...

    def find_by_request(request): ...
