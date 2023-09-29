import logging

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError
from scrapy.utils.log import failure_to_exc_info

logger = logging.getLogger(__name__)

class Command(BaseRunSpiderCommand):
    requires_project = True
    

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Run a spider"

    def run(self, args, opts):
        
        if opts.output:
            extensions_base = self.settings.getdict("EXTENSIONS_BASE")
            extensions = self.settings.getdict("EXTENSIONS")

            feed_exporter_base = extensions_base.get("scrapy.extensions.feedexport.FeedExporter")
            feed_exporter = extensions.get("scrapy.extensions.feedexport.FeedExporter")

            if feed_exporter_base is None:
                logger.warning("A file output was specified but the FeedExporter extension is not enabled in EXTENSIONS_BASE.")
            elif "scrapy.extensions.feedexport.FeedExporter" in extensions.keys() and feed_exporter is None:
                logger.warning("A file output was specified but the FeedExporter extension is not enabled in EXTENSIONS.")

        if len(args) < 1:
            raise UsageError()
        elif len(args) > 1:
            raise UsageError(
                "running 'scrapy crawl' with more than one spider is not supported"
            )
        spname = args[0]

        crawl_defer = self.crawler_process.crawl(spname, **opts.spargs)

        if getattr(crawl_defer, "result", None) is not None and issubclass(
            crawl_defer.result.type, Exception
        ):
            self.exitcode = 1
        else:
            self.crawler_process.start()

            if (
                self.crawler_process.bootstrap_failed
                or hasattr(self.crawler_process, "has_exception")
                and self.crawler_process.has_exception
            ):
                self.exitcode = 1
