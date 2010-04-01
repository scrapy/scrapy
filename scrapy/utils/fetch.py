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
    for url in urls:
        req = Request(url, callback=responses.append, dont_filter=True)
        # @@@ request will require a suitable spider.
        #     If not will not be schedule
        scrapymanager.crawl_request(req)
    scrapymanager.start()
    return responses

