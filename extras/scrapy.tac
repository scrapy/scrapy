from twisted.application.service import Application
from scrapy.service import ScrapyService

application = Application("Scrapy")
ScrapyService().setServiceParent(application)
