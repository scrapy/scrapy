from __future__ import print_function
from scrapy.commands import ScrapyCommand

class Command(ScrapyCommand):

    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def short_desc(self):
        return "List available spiders"

    def run(self, args, opts):
        for s in sorted(self.crawler_process.spider_loader.list()):
            print(s)
        # eigen modified
        # 输出加载失败的模块报错信息
        failed_modules = self.crawler_process.spider_loader.failed_modules
        if failed_modules:
            for path in failed_modules:
                spider = path.split('.')[-1]
                print('%s: %s'%(spider, failed_modules[path].message))
        # end
        # ------------------------------------------------------------
