#!/usr/bin/python
# -*- coding: utf-8 -*-

from scrapy.crawler import Crawler
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor
from spiders.newenglandfilm import NewenglandFilm
from spiders.mandy import Mandy
from spiders.productionhub import ProductionHub
from spiders.craiglist import Craiglist
from spiders.my_settings import options, logfile

settings = get_project_settings()
settings.overrides.update(options)

crawler = Crawler(settings)
crawler.configure()
crawler.crawl(NewenglandFilm())
crawler.start()

crawler = Crawler(settings)
crawler.configure()
crawler.crawl(Mandy())
crawler.start()

crawler = Crawler(settings)
crawler.configure()
crawler.crawl(ProductionHub())
crawler.start()

crawler = Crawler(settings)
crawler.configure()
crawler.crawl(Craiglist())
crawler.start()

reactor.run()

