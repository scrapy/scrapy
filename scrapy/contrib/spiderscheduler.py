"""
The Spider Scheduler keeps track of next spiders to scrape. They must implement
the following methods:

* next_spider()
  return next spider to scrape and remove it from pending queue

* add_spider(spider)
  add spider to pending queue

* remove_pending_spider(spider)
  remove (all occurrences) of spider from pending queue, do nothing if not
  pending

* has_pending_spider(spider)
  Return ``True`` if the spider is pending to scrape, ``False`` otherwise

"""

class FifoSpiderScheduler(object):
    """Basic spider scheduler based on a FIFO queue"""

    def __init__(self):
        self._pending_spiders = []

    def next_spider(self) :
        if self._pending_spiders:
            return self._pending_spiders.pop(0)

    def add_spider(self, spider):
        self._pending_spiders.append(spider)

    def remove_pending_spider(self, spider):
        self._pending_spiders = [d for d in self._pending_spiders if d != spider]

    def has_pending_spider(self, spider):
        return spider in self._pending_spiders
