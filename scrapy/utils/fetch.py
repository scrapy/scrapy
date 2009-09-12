from scrapy.http import Request
from scrapy.core.manager import scrapymanager

def fetch(urls):
    """Fetch a list of urls and return a list of the downloaded Scrapy
    Responses.

    This is a blocking function not suitable for calling from spiders. Instead,
    it is indended to be called from outside the framework such as Scrapy
    commands or standalone scripts.
    """
    responses = []
    requests = [Request(url, callback=responses.append, dont_filter=True) \
        for url in urls]
    scrapymanager.runonce(*requests)
    return responses

