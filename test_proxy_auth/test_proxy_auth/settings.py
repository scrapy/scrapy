# -*- coding: utf-8 -*-
BOT_NAME = 'test_proxy_auth'
SPIDER_MODULES = ['test_proxy_auth.spiders']
NEWSPIDER_MODULE = 'test_proxy_auth.spiders'
ROBOTSTXT_OBEY = False
CONCURRENT_REQUESTS = 1
DOWNLOAD_DELAY = 0.1
DOWNLOAD_TIMEOUT = 0.1
COOKIES_ENABLED = False
RETRY_TIMES = 10

DOWNLOADER_MIDDLEWARES = {
    'test_proxy_auth.middlewares.ProxyMiddleware': 543,
}

