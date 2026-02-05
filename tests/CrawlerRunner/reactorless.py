from scrapy.crawler import CrawlerRunner

CrawlerRunner(
    settings={
        "TWISTED_ENABLED": False,
        "DOWNLOAD_HANDLERS": {
            "http": None,
            "https": None,
            "ftp": None,
        },
    }
)
