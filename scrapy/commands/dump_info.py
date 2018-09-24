#!/usr/bin/env python
# encoding: utf-8
"""
    @file: dump_info.py
    
    ~~~~~~~~~~~


    :copyright: (c) 2017 by the eigen.
    :license: BSD, see LICENSE for more details.
    @time: 2018/9/24 下午4:44
"""


import os
import json
from scrapy.commands import ScrapyCommand
from scrapy.utils.project import get_project_settings


# eigen modified
# dump_info 是为了拿到爬虫的信息，在多project的架构下是必要的，但是在单project的架构下，后续可以直接从server端获取
class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'DUMP_INFO': True, 'LOG_ENABLED': False, 'SPIDER_LOADER_WARN_ONLY': True}

    def short_desc(self):
        return "Dump project information to MySQL"

    def run(self, args, opts):
        result = {}
        result['project_settings'], result['user_project_settings'] = self.get_project_priority_settings()
        result['spiders_settings'], result['spiders'] = self.get_spiders_settings()
        dumpped_result = json.dumps(result)
        dumpped_result_tagged = '<dumpped_settings>%s</dumpped_settings>'%dumpped_result
        print(dumpped_result_tagged)
        try:
            os.remove('/tmp/scrapy_dumpped_info.txt')
        except OSError:
            pass
        with open('/tmp/scrapy_dumpped_info.txt', 'w') as f:
            f.write(dumpped_result)

    def spider_list(self):
        return sorted(self.crawler_process.spider_loader.list())

    def get_project_priority_settings(self):
        settings = get_project_settings()
        project_settings = settings.get_priority_settings('project')
        user_project_settings = settings.get_priority_settings('user_project')
        return project_settings, user_project_settings

    def get_spiders_settings(self):
        spiders_settings = {}
        spiders_checked = {key:None for key in self.spider_list()}
        for spider in spiders_checked:
            try:
                crawler = self.crawler_process.create_crawler(spider)
                spiders_settings[spider] = crawler.settings.get_priority_settings('spider')
            except Exception as e:
                spiders_checked[spider] = repr(e)
        failed_modules = self.crawler_process.spider_loader.failed_modules
        if failed_modules:
            for path in failed_modules:
                spider = path.split('.')[-1]
                spiders_checked[spider] = failed_modules[path].message
        return spiders_settings, spiders_checked
