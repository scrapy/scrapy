#-*- coding:utf-8 –*-
from __future__ import print_function
from scrapy.commands import ScrapyCommand

# 查看项目内有效的爬虫
class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        for s in sorted(self.crawler_process.spider_loader.list()):
            print(s)
