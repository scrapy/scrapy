"""
Feed Exports extension

See documentation in docs/topics/feed-exports.rst
"""

import logging
import os
import sys
import warnings
from datetime import datetime
from tempfile import NamedTemporaryFile
from urllib.parse import unquote, urlparse

from twisted.internet import defer, threads
from w3lib.url import file_uri_to_path
from zope.interface import implementer, Interface

from scrapy import signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.utils.boto import is_botocore
from scrapy.utils.conf import feed_complete_default_values_from_settings
from scrapy.utils.ftp import ftp_store_file
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.python import without_none_values


logger = logging.getLogger(__name__)


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
class BlockingFeedStorage:

    def open(self, spider):
        path = spider.crawler.settings['FEED_TEMPDIR']
        if path and not os.path.isdir(path):
            raise OSError('Not a Directory: ' + str(path))

        return NamedTemporaryFile(prefix='feed-', dir=path)

    def store(self, file):
        return threads.deferToThread(self._store_in_thread, file)

    def _store_in_thread(self, file):
        raise NotImplementedError


@implementer(IFeedStorage)
class StdoutFeedStorage:

    def __init__(self, uri, _stdout=None):
        if not _stdout:
            _stdout = sys.stdout.buffer
        self._stdout = _stdout

    def open(self, spider):
        return self._stdout

    def store(self, file):
        pass


@implementer(IFeedStorage)
class FileFeedStorage:

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

    def __init__(self, uri, access_key=None, secret_key=None, acl=None):
        # BEGIN Backward compatibility for initialising without keys (and
        # without using from_crawler)
        no_defaults = access_key is None and secret_key is None
        if no_defaults:
            from scrapy.utils.project import get_project_settings
            settings = get_project_settings()
            if 'AWS_ACCESS_KEY_ID' in settings or 'AWS_SECRET_ACCESS_KEY' in settings:
                warnings.warn(
                    "Initialising `scrapy.extensions.feedexport.S3FeedStorage` "
                    "without AWS keys is deprecated. Please supply credentials or "
                    "use the `from_crawler()` constructor.",
                    category=ScrapyDeprecationWarning,
                    stacklevel=2
                )
                access_key = settings['AWS_ACCESS_KEY_ID']
                secret_key = settings['AWS_SECRET_ACCESS_KEY']
        # END Backward compatibility
        u = urlparse(uri)
        self.bucketname = u.hostname
        self.access_key = u.username or access_key
        self.secret_key = u.password or secret_key
        self.is_botocore = is_botocore()
        self.keyname = u.path[1:]  # remove first "/"
        self.acl = acl
        if self.is_botocore:
            import botocore.session
            session = botocore.session.get_session()
            self.s3_client = session.create_client(
                's3', aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key)
        else:
            import boto
            self.connect_s3 = boto.connect_s3

    @classmethod
    def from_crawler(cls, crawler, uri):
        return cls(
            uri=uri,
            access_key=crawler.settings['AWS_ACCESS_KEY_ID'],
            secret_key=crawler.settings['AWS_SECRET_ACCESS_KEY'],
            acl=crawler.settings['FEED_STORAGE_S3_ACL'] or None
        )

    def _store_in_thread(self, file):
        file.seek(0)
        if self.is_botocore:
            kwargs = {'ACL': self.acl} if self.acl else {}
            self.s3_client.put_object(
                Bucket=self.bucketname, Key=self.keyname, Body=file,
                **kwargs)
        else:
            conn = self.connect_s3(self.access_key, self.secret_key)
            bucket = conn.get_bucket(self.bucketname, validate=False)
            key = bucket.new_key(self.keyname)
            kwargs = {'policy': self.acl} if self.acl else {}
            key.set_contents_from_file(file, **kwargs)
            key.close()


class FTPFeedStorage(BlockingFeedStorage):

    def __init__(self, uri, use_active_mode=False):
        u = urlparse(uri)
        self.host = u.hostname
        self.port = int(u.port or '21')
        self.username = u.username
        self.password = unquote(u.password)
        self.path = u.path
        self.use_active_mode = use_active_mode

    @classmethod
    def from_crawler(cls, crawler, uri):
        return cls(
            uri=uri,
            use_active_mode=crawler.settings.getbool('FEED_STORAGE_FTP_ACTIVE')
        )

    def _store_in_thread(self, file):
        ftp_store_file(
            path=self.path, file=file, host=self.host,
            port=self.port, username=self.username,
            password=self.password, use_active_mode=self.use_active_mode
        )


class _FeedSlot:
    def __init__(self, file, exporter, storage, uri, format, store_empty):
        self.file = file
        self.exporter = exporter
        self.storage = storage
        # feed params
        self.uri = uri
        self.format = format
        self.store_empty = store_empty
        # flags
        self.itemcount = 0
        self._exporting = False

    def start_exporting(self):
        if not self._exporting:
            self.exporter.start_exporting()
            self._exporting = True

    def finish_exporting(self):
        if self._exporting:
            self.exporter.finish_exporting()
            self._exporting = False


class FeedExporter:

    @classmethod
    def from_crawler(cls, crawler):
        exporter = cls(crawler)
        crawler.signals.connect(exporter.open_spider, signals.spider_opened)
        crawler.signals.connect(exporter.close_spider, signals.spider_closed)
        crawler.signals.connect(exporter.item_scraped, signals.item_scraped)
        return exporter

    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.feeds = {}
        self.slots = []

        if not self.settings['FEEDS'] and not self.settings['FEED_URI']:
            raise NotConfigured

        # Begin: Backward compatibility for FEED_URI and FEED_FORMAT settings
        if self.settings['FEED_URI']:
            warnings.warn(
                'The `FEED_URI` and `FEED_FORMAT` settings have been deprecated in favor of '
                'the `FEEDS` setting. Please see the `FEEDS` setting docs for more details',
                category=ScrapyDeprecationWarning, stacklevel=2,
            )
            uri = str(self.settings['FEED_URI'])  # handle pathlib.Path objects
            feed = {'format': self.settings.get('FEED_FORMAT', 'jsonlines')}
            self.feeds[uri] = feed_complete_default_values_from_settings(feed, self.settings)
        # End: Backward compatibility for FEED_URI and FEED_FORMAT settings

        # 'FEEDS' setting takes precedence over 'FEED_URI'
        for uri, feed in self.settings.getdict('FEEDS').items():
            uri = str(uri)  # handle pathlib.Path objects
            self.feeds[uri] = feed_complete_default_values_from_settings(feed, self.settings)

        self.storages = self._load_components('FEED_STORAGES')
        self.exporters = self._load_components('FEED_EXPORTERS')
        for uri, feed in self.feeds.items():
            if not self._storage_supported(uri):
                raise NotConfigured
            if not self._exporter_supported(feed['format']):
                raise NotConfigured

    def open_spider(self, spider):
        for uri, feed in self.feeds.items():
            uri = uri % self._get_uri_params(spider, feed['uri_params'])
            storage = self._get_storage(uri)
            file = storage.open(spider)
            exporter = self._get_exporter(
                file=file,
                format=feed['format'],
                fields_to_export=feed['fields'],
                encoding=feed['encoding'],
                indent=feed['indent'],
            )
            slot = _FeedSlot(file, exporter, storage, uri, feed['format'], feed['store_empty'])
            self.slots.append(slot)
            if slot.store_empty:
                slot.start_exporting()

    def close_spider(self, spider):
        deferred_list = []
        for slot in self.slots:
            if not slot.itemcount and not slot.store_empty:
                # We need to call slot.storage.store nonetheless to get the file
                # properly closed.
                return defer.maybeDeferred(slot.storage.store, slot.file)
            slot.finish_exporting()
            logfmt = "%s %%(format)s feed (%%(itemcount)d items) in: %%(uri)s"
            log_args = {'format': slot.format,
                        'itemcount': slot.itemcount,
                        'uri': slot.uri}
            d = defer.maybeDeferred(slot.storage.store, slot.file)
            d.addCallback(lambda _: logger.info(logfmt % "Stored", log_args,
                                                extra={'spider': spider}))
            d.addErrback(lambda f: logger.error(logfmt % "Error storing", log_args,
                                                exc_info=failure_to_exc_info(f),
                                                extra={'spider': spider}))
            deferred_list.append(d)
        return defer.DeferredList(deferred_list) if deferred_list else None

    def item_scraped(self, item, spider):
        for slot in self.slots:
            slot.start_exporting()
            slot.exporter.export_item(item)
            slot.itemcount += 1

    def _load_components(self, setting_prefix):
        conf = without_none_values(self.settings.getwithbase(setting_prefix))
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
        logger.error("Unknown feed format: %(format)s", {'format': format})

    def _storage_supported(self, uri):
        scheme = urlparse(uri).scheme
        if scheme in self.storages:
            try:
                self._get_storage(uri)
                return True
            except NotConfigured as e:
                logger.error("Disabled feed storage scheme: %(scheme)s. "
                             "Reason: %(reason)s",
                             {'scheme': scheme, 'reason': str(e)})
        else:
            logger.error("Unknown feed storage scheme: %(scheme)s",
                         {'scheme': scheme})

    def _get_instance(self, objcls, *args, **kwargs):
        return create_instance(
            objcls, self.settings, getattr(self, 'crawler', None),
            *args, **kwargs)

    def _get_exporter(self, file, format, *args, **kwargs):
        return self._get_instance(self.exporters[format], file, *args, **kwargs)

    def _get_storage(self, uri):
        return self._get_instance(self.storages[urlparse(uri).scheme], uri)

    def _get_uri_params(self, spider, uri_params):
        params = {}
        for k in dir(spider):
            params[k] = getattr(spider, k)
        ts = datetime.utcnow().replace(microsecond=0).isoformat().replace(':', '-')
        params['time'] = ts
        uripar_function = load_object(uri_params) if uri_params else lambda x, y: None
        uripar_function(params, spider)
        return params
