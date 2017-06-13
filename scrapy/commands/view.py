#-*- coding:utf-8 –*-
from scrapy.commands import fetch, ScrapyCommand
from scrapy.utils.response import open_in_browser

# 使用浏览器打开网页(父类是fetch)
class Command(fetch.Command):

    def short_desc(self):
        return "Open URL in browser, as seen by Scrapy"

    def long_desc(self):
        return "Fetch a URL using the Scrapy downloader and show its " \
            "contents in a browser"
            
    # 类似命令: scrapy view http://www.baidu.com
    def add_options(self, parser):
        super(Command, self).add_options(parser)
        # 移除掉父类的--headers参数
        parser.remove_option("--headers")

    def _print_response(self, response, opts):
        open_in_browser(response)
