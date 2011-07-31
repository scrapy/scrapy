"""
Dupe Filter classes implement a mechanism for filtering duplicate requests.
They must implement the following method:

* request_seen(request, dont_record=False)
  return ``True`` if the request was seen before, or ``False`` otherwise. If
  ``dont_record`` is ``True`` the request must not be recorded as seen.

"""

from scrapy.utils.request import request_fingerprint


class BaseDupeFilter(object):

    @classmethod
    def from_settings(cls, settings):
        return cls()

    def request_seen(self, request, dont_record=False):
        return False


class RequestFingerprintDupeFilter(BaseDupeFilter):
    """Duplicate filter using scrapy.utils.request.request_fingerprint"""

    def __init__(self):
        super(RequestFingerprintDupeFilter, self).__init__()
        self.fingerprints = set()

    def request_seen(self, request, dont_record=False):
        fp = request_fingerprint(request)
        if fp in self.fingerprints:
            return True
        if not dont_record:
            self.fingerprints.add(fp)
        return False
