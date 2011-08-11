"""
--------- WARNING: THIS MODULE IS DEPRECATED -----------

This module is deprecated. If you want to get the Scrapy crawler from your
extension, middleware or pipeline implement the `from_crawler` class method.

For example:

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

"""
