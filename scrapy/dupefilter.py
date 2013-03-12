import os
from scrapy.utils.request import request_fingerprint
from scrapy.utils.job import job_dir
from scrapy import log


class BaseDupeFilter(object):

    @classmethod
    def from_settings(cls, settings):
        return cls()

    def request_seen(self, request):
        return False

    def open(self):  # can return deferred
        pass

    def close(self, reason): # can return a deferred
        pass

    def log(self, request, spider): # log that a request has been filtered
        pass

class RFPDupeFilter(BaseDupeFilter):
    """Request Fingerprint duplicates filter"""

    def __init__(self, path=None):
        self.file = None
        self.fingerprints = set()
        self.logdupes = True
        if path:
            self.file = open(os.path.join(path, 'requests.seen'), 'a+')
            self.fingerprints.update(x.rstrip() for x in self.file)

    @classmethod
    def from_settings(cls, settings):
        return cls(job_dir(settings))

    def request_seen(self, request):
        fp = request_fingerprint(request)
        if fp in self.fingerprints:
            return True
        self.fingerprints.add(fp)
        if self.file:
            self.file.write(fp + os.linesep)

    def close(self, reason):
        if self.file:
            self.file.close()

    def log(self, request, spider):
        if self.logdupes:
            fmt = "Filtered duplicate request: %(request)s - no more duplicates will be shown (see DUPEFILTER_CLASS)"
            log.msg(format=fmt, request=request, level=log.DEBUG, spider=spider)
            self.logdupes = False
