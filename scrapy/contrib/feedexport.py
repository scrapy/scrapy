"""
Feed Exports extension

See documentation in docs/topics/feed-exports.rst
"""

import sys, os, posixpath
from tempfile import TemporaryFile
from datetime import datetime
from six.moves.urllib.parse import urlparse
from ftplib import FTP

from zope.interface import Interface, implementer
from twisted.internet import defer, threads
from w3lib.url import file_uri_to_path

from scrapy import log, signals
from scrapy.utils.ftp import ftp_makedirs_cwd
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy.utils.python import get_func_args


class IFeedStorage(Interface):
    """Interface that all Feed Storages must implement"""

    def __init__(uri):
        """Initialize the storage with the parameters given in the URI"""

    def open(spider):
        """Open the storage for the given spider. It must return a file-like
        object that will be used for the exporters"""

    def store(file):
        """Store the given file stream"""


@implementer(IFeedStorage)
class BlockingFeedStorage(object):

    def open(self, spider):
        return TemporaryFile(prefix='feed-')

    def store(self, file):
        return threads.deferToThread(self._store_in_thread, file)

    def _store_in_thread(self, file):
        raise NotImplementedError


@implementer(IFeedStorage)
class StdoutFeedStorage(object):

    def __init__(self, uri, _stdout=sys.stdout):
        self._stdout = _stdout

    def open(self, spider):
        return self._stdout

    def store(self, file):
        pass


@implementer(IFeedStorage)
class FileFeedStorage(object):

    def __init__(self, uri):
        self.path = file_uri_to_path(uri)

    def open(self, spider):
        dirname = os.path.dirname(self.path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)
        return open(self.path, 'ab')

    def store(self, file):
        file.close()


class S3FeedStorage(BlockingFeedStorage):

    def __init__(self, uri):
        from scrapy.conf import settings
        try:
            import boto
        except ImportError:
            raise NotConfigured
        self.connect_s3 = boto.connect_s3
        u = urlparse(uri)
        self.bucketname = u.hostname
        self.access_key = u.username or settings['AWS_ACCESS_KEY_ID']
        self.secret_key = u.password or settings['AWS_SECRET_ACCESS_KEY']
        self.keyname = u.path

    def _store_in_thread(self, file):
        file.seek(0)
        conn = self.connect_s3(self.access_key, self.secret_key)
        bucket = conn.get_bucket(self.bucketname, validate=False)
        key = bucket.new_key(self.keyname)
        key.set_contents_from_file(file)
        key.close()


class FTPFeedStorage(BlockingFeedStorage):

    def __init__(self, uri):
        u = urlparse(uri)
        self.host = u.hostname
        self.port = int(u.port or '21')
        self.username = u.username
        self.password = u.password
        self.path = u.path

    def _store_in_thread(self, file):
        file.seek(0)
        ftp = FTP()
        ftp.connect(self.host, self.port)
        ftp.login(self.username, self.password)
        dirname, filename = posixpath.split(self.path)
        ftp_makedirs_cwd(ftp, dirname)
        ftp.storbinary('STOR %s' % filename, file)
        ftp.quit()


class SpiderSlot(object):
    def __init__(self, file, exporter, storage, uri):
        self.file = file
        self.exporter = exporter
        self.storage = storage
        self.uri = uri
        self.itemcount = 0


class FeedExporter(object):

    def __init__(self, settings):
        self.settings = settings
        self.urifmt = settings['FEED_URI']
        if not self.urifmt:
            raise NotConfigured
        self.format = settings['FEED_FORMAT'].lower()
        self.storages = self._load_components('FEED_STORAGES')
        self.exporters = self._load_components('FEED_EXPORTERS')
        if not self._storage_supported(self.urifmt):
            raise NotConfigured
        if not self._exporter_supported(self.format):
            raise NotConfigured
        self.store_empty = settings.getbool('FEED_STORE_EMPTY')
        uripar = settings['FEED_URI_PARAMS']
        self._uripar = load_object(uripar) if uripar else lambda x, y: None

    @classmethod
    def from_crawler(cls, crawler):
        if len(get_func_args(cls)) < 1:
            # FIXME: remove for scrapy 0.17
            import warnings
            from scrapy.exceptions import ScrapyDeprecationWarning
            warnings.warn("%s must receive a settings object as first constructor argument." % cls.__name__,
                ScrapyDeprecationWarning, stacklevel=2)
            o = cls()
        else:
            o = cls(crawler.settings)
        crawler.signals.connect(o.open_spider, signals.spider_opened)
        crawler.signals.connect(o.close_spider, signals.spider_closed)
        crawler.signals.connect(o.item_scraped, signals.item_scraped)
        return o

    def open_spider(self, spider):
        uri = self.urifmt % self._get_uri_params(spider)
        storage = self._get_storage(uri)
        file = storage.open(spider)
        exporter = self._get_exporter(file)
        exporter.start_exporting()
        self.slot = SpiderSlot(file, exporter, storage, uri)

    def close_spider(self, spider):
        slot = self.slot
        if not slot.itemcount and not self.store_empty:
            return
        slot.exporter.finish_exporting()
        logfmt = "%%s %s feed (%d items) in: %s" % (self.format, \
            slot.itemcount, slot.uri)
        d = defer.maybeDeferred(slot.storage.store, slot.file)
        d.addCallback(lambda _: log.msg(logfmt % "Stored", spider=spider))
        d.addErrback(log.err, logfmt % "Error storing", spider=spider)
        return d

    def item_scraped(self, item, spider):
        slot = self.slot
        slot.exporter.export_item(item)
        slot.itemcount += 1
        return item

    def _load_components(self, setting_prefix):
        conf = dict(self.settings['%s_BASE' % setting_prefix])
        conf.update(self.settings[setting_prefix])
        d = {}
        for k, v in conf.items():
            try:
                d[k] = load_object(v)
            except NotConfigured:
                pass
        return d

    def _exporter_supported(self, format):
        if format in self.exporters:
            return True
        log.msg("Unknown feed format: %s" % format, log.ERROR)

    def _storage_supported(self, uri):
        scheme = urlparse(uri).scheme
        if scheme in self.storages:
            try:
                self._get_storage(uri)
                return True
            except NotConfigured:
                log.msg("Disabled feed storage scheme: %s" % scheme, log.ERROR)
        else:
            log.msg("Unknown feed storage scheme: %s" % scheme, log.ERROR)

    def _get_exporter(self, *a, **kw):
        return self.exporters[self.format](*a, **kw)

    def _get_storage(self, uri):
        return self.storages[urlparse(uri).scheme](uri)

    def _get_uri_params(self, spider):
        params = {}
        for k in dir(spider):
            params[k] = getattr(spider, k)
        ts = datetime.utcnow().replace(microsecond=0).isoformat().replace(':', '-')
        params['time'] = ts
        self._uripar(params, spider)
        return params
