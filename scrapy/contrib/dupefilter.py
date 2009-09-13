"""
Dupe Filter classes implement a mechanism for filtering duplicate requests.
They must implement the following methods:

* open_spider(spider)
  open a spider for tracking duplicates (typically used to reserve resources)

* close_spider(spider)
  close a spider (typically used for freeing resources)

* request_seen(spider, request, dont_record=False)
  return ``True`` if the request was seen before, or ``False`` otherwise. If
  ``dont_record`` is ``True`` the request must not be recorded as seen.

"""

from scrapy.utils.request import request_fingerprint


class NullDupeFilter(dict):
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def request_seen(self, spider, request, dont_record=False):
        return False


class RequestFingerprintDupeFilter(object):
    """Duplicate filter using scrapy.utils.request.request_fingerprint"""

    def __init__(self):
        self.fingerprints = {}

    def open_spider(self, spider):
        self.fingerprints[spider] = set()

    def close_spider(self, spider):
        del self.fingerprints[spider]

    def request_seen(self, spider, request, dont_record=False):
        fp = request_fingerprint(request)
        if fp in self.fingerprints[spider]:
            return True
        if not dont_record:
            self.fingerprints[spider].add(fp)
        return False
