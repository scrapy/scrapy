from scrapy.crawler import CrawlerProcess

CrawlerProcess(
    settings={
        "TWISTED_ENABLED": False,
        "DOWNLOAD_HANDLERS": {
            "http": None,
            "https": None,
            "ftp": None,
        },
    }
)
