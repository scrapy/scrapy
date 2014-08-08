
"""
Obsolete module, kept for giving a meaningful error message when trying to
import.
"""

raise ImportError("""scrapy.project usage has become obsolete.

If you want to get the Scrapy crawler from your extension, middleware or
pipeline implement the `from_crawler` class method (or look up for extending
components that have already done it, such as spiders).

For example:

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)""")
