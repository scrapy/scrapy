"""
Dupe Filter classes implement a mechanism for filtering duplicate requests.
They must implement the following methods:

* open_domain(domain)
  open a domain for tracking duplicates (typically used to reserve resources)

* close_domain(domain)
  close a domain (typically used for freeing resources)

* request_seen(domain, request, dont_record=False)
  return ``True`` if the request was seen before, or ``False`` otherwise. If
  ``dont_record`` is ``True`` the request must not be recorded as seen.

"""

from scrapy.utils.request import request_fingerprint


class NullDupeFilter(dict):
    def open_domain(self, domain):
        pass

    def close_domain(self, domain):
        pass

    def request_seen(self, domain, request, dont_record=False):
        return False


class RequestFingerprintDupeFilter(object):
    """Duplicate filter using scrapy.utils.request.request_fingerprint"""

    def __init__(self):
        self.fingerprints = {}

    def open_domain(self, domain):
        self.fingerprints[domain] = set()

    def close_domain(self, domain):
        del self.fingerprints[domain]

    def request_seen(self, domain, request, dont_record=False):
        fp = request_fingerprint(request)
        if fp in self.fingerprints[domain]:
            return True
        if not dont_record:
            self.fingerprints[domain].add(fp)
        return False
