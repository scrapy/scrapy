"""
Feed Exports extension

See documentation in docs/topics/feed-exports.rst
"""

import logging
import os
import re
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
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.conf import feed_complete_default_values_from_settings
from scrapy.utils.ftp import ftp_store_file
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.python import get_func_args, without_none_values


logger = logging.getLogger(__name__)


def build_storage(builder, uri, *args, feed_options=None, preargs=(), **kwargs):
    argument_names = get_func_args(builder)
    if 'feed_options' in argument_names:
        kwargs['feed_options'] = feed_options
    else:
        warnings.warn(
            "{} does not support the 'feed_options' keyword argument. Add a "
            "'feed_options' parameter to its signature to remove this "
            "warning. This parameter will become mandatory in a future "
            "version of Scrapy."
            .format(builder.__qualname__),
            category=ScrapyDeprecationWarning
        )
    return builder(*preargs, uri, *args, **kwargs)


class IFeedStorage(Interface):
    """Interface that all Feed Storages must implement"""

    def __init__(uri, *, feed_options=None):
        """Initialize the storage with the parameters given in the URI and the
        feed-specific options (see :setting:`FEEDS`)"""

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

    def __init__(self, uri, _stdout=None, *, feed_options=None):
        if not _stdout:
            _stdout = sys.stdout.buffer
        self._stdout = _stdout
        if feed_options and feed_options.get('overwrite', False) is True:
            logger.warning('Standard output (stdout) storage does not support '
                           'overwriting. To suppress this warning, remove the '
                           'overwrite option from your FEEDS setting, or set '
                           'it to False.')

    def open(self, spider):
        return self._stdout

    def store(self, file):
        pass


@implementer(IFeedStorage)
class FileFeedStorage:

    def __init__(self, uri, *, feed_options=None):
        self.path = file_uri_to_path(uri)
        feed_options = feed_options or {}
        self.write_mode = 'wb' if feed_options.get('overwrite', False) else 'ab'

    def open(self, spider):
        dirname = os.path.dirname(self.path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)
        return open(self.path, self.write_mode)

    def store(self, file):
        file.close()


class S3FeedStorage(BlockingFeedStorage):

    def __init__(self, uri, access_key=None, secret_key=None, acl=None, *,
                 feed_options=None):
        if not is_botocore_available():
            raise NotConfigured('missing botocore library')
        u = urlparse(uri)
        self.bucketname = u.hostname
        self.access_key = u.username or access_key
        self.secret_key = u.password or secret_key
        self.keyname = u.path[1:]  # remove first "/"
        self.acl = acl
        import botocore.session
        session = botocore.session.get_session()
        self.s3_client = session.create_client(
            's3', aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key)
        if feed_options and feed_options.get('overwrite', True) is False:
            logger.warning('S3 does not support appending to files. To '
                           'suppress this warning, remove the overwrite '
                           'option from your FEEDS setting or set it to True.')

    @classmethod
    def from_crawler(cls, crawler, uri, *, feed_options=None):
        return build_storage(
            cls,
            uri,
            access_key=crawler.settings['AWS_ACCESS_KEY_ID'],
            secret_key=crawler.settings['AWS_SECRET_ACCESS_KEY'],
            acl=crawler.settings['FEED_STORAGE_S3_ACL'] or None,
            feed_options=feed_options,
        )

    def _store_in_thread(self, file):
        file.seek(0)
        kwargs = {'ACL': self.acl} if self.acl else {}
        self.s3_client.put_object(
            Bucket=self.bucketname, Key=self.keyname, Body=file,
            **kwargs)
        file.close()


class GCSFeedStorage(BlockingFeedStorage):

    def __init__(self, uri, project_id, acl):
        self.project_id = project_id
        self.acl = acl
        u = urlparse(uri)
        self.bucket_name = u.hostname
        self.blob_name = u.path[1:]  # remove first "/"

    @classmethod
    def from_crawler(cls, crawler, uri):
        return cls(
            uri,
            crawler.settings['GCS_PROJECT_ID'],
            crawler.settings['FEED_STORAGE_GCS_ACL'] or None
        )

    def _store_in_thread(self, file):
        file.seek(0)
        from google.cloud.storage import Client
        client = Client(project=self.project_id)
        bucket = client.get_bucket(self.bucket_name)
        blob = bucket.blob(self.blob_name)
        blob.upload_from_file(file, predefined_acl=self.acl)


class FTPFeedStorage(BlockingFeedStorage):

    def __init__(self, uri, use_active_mode=False, *, feed_options=None):
        u = urlparse(uri)
        self.host = u.hostname
        self.port = int(u.port or '21')
        self.username = u.username
        self.password = unquote(u.password or '')
        self.path = u.path
        self.use_active_mode = use_active_mode
        self.overwrite = not feed_options or feed_options.get('overwrite', True)

    @classmethod
    def from_crawler(cls, crawler, uri, *, feed_options=None):
        return build_storage(
            cls,
            uri,
            crawler.settings.getbool('FEED_STORAGE_FTP_ACTIVE'),
            feed_options=feed_options,
        )

    def _store_in_thread(self, file):
        ftp_store_file(
            path=self.path, file=file, host=self.host,
            port=self.port, username=self.username,
            password=self.password, use_active_mode=self.use_active_mode,
            overwrite=self.overwrite,
        )


class _FeedSlot:
    def __init__(self, file, exporter, storage, uri, format, store_empty, batch_id, uri_template):
        self.file = file
        self.exporter = exporter
        self.storage = storage
        # feed params
        self.batch_id = batch_id
        self.format = format
        self.store_empty = store_empty
        self.uri_template = uri_template
        self.uri = uri
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
            feed_options = {'format': self.settings.get('FEED_FORMAT', 'jsonlines')}
            self.feeds[uri] = feed_complete_default_values_from_settings(feed_options, self.settings)
        # End: Backward compatibility for FEED_URI and FEED_FORMAT settings

        # 'FEEDS' setting takes precedence over 'FEED_URI'
        for uri, feed_options in self.settings.getdict('FEEDS').items():
            uri = str(uri)  # handle pathlib.Path objects
            self.feeds[uri] = feed_complete_default_values_from_settings(feed_options, self.settings)

        self.storages = self._load_components('FEED_STORAGES')
        self.exporters = self._load_components('FEED_EXPORTERS')
        for uri, feed_options in self.feeds.items():
            if not self._storage_supported(uri, feed_options):
                raise NotConfigured
            if not self._settings_are_valid():
                raise NotConfigured
            if not self._exporter_supported(feed_options['format']):
                raise NotConfigured

    def open_spider(self, spider):
        for uri, feed_options in self.feeds.items():
            uri_params = self._get_uri_params(spider, feed_options['uri_params'])
            self.slots.append(self._start_new_batch(
                batch_id=1,
                uri=uri % uri_params,
                feed_options=feed_options,
                spider=spider,
                uri_template=uri,
            ))

    def close_spider(self, spider):
        deferred_list = []
        for slot in self.slots:
            d = self._close_slot(slot, spider)
            deferred_list.append(d)
        return defer.DeferredList(deferred_list) if deferred_list else None

    def _close_slot(self, slot, spider):
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

        # Use `largs=log_args` to copy log_args into function's scope
        # instead of using `log_args` from the outer scope
        d.addCallback(
            lambda _, largs=log_args: logger.info(
                logfmt % "Stored", largs, extra={'spider': spider}
            )
        )
        d.addErrback(
            lambda f, largs=log_args: logger.error(
                logfmt % "Error storing", largs,
                exc_info=failure_to_exc_info(f), extra={'spider': spider}
            )
        )
        return d

    def _start_new_batch(self, batch_id, uri, feed_options, spider, uri_template):
        """
        Redirect the output data stream to a new file.
        Execute multiple times if FEED_EXPORT_BATCH_ITEM_COUNT setting or FEEDS.batch_item_count is specified
        :param batch_id: sequence number of current batch
        :param uri: uri of the new batch to start
        :param feed_options: dict with parameters of feed
        :param spider: user spider
        :param uri_template: template of uri which contains %(batch_time)s or %(batch_id)d to create new uri
        """
        storage = self._get_storage(uri, feed_options)
        file = storage.open(spider)
        exporter = self._get_exporter(
            file=file,
            format=feed_options['format'],
            fields_to_export=feed_options['fields'],
            encoding=feed_options['encoding'],
            indent=feed_options['indent'],
            **feed_options['item_export_kwargs'],
        )
        slot = _FeedSlot(
            file=file,
            exporter=exporter,
            storage=storage,
            uri=uri,
            format=feed_options['format'],
            store_empty=feed_options['store_empty'],
            batch_id=batch_id,
            uri_template=uri_template,
        )
        if slot.store_empty:
            slot.start_exporting()
        return slot

    def item_scraped(self, item, spider):
        slots = []
        for slot in self.slots:
            slot.start_exporting()
            slot.exporter.export_item(item)
            slot.itemcount += 1
            # create new slot for each slot with itemcount == FEED_EXPORT_BATCH_ITEM_COUNT and close the old one
            if (
                self.feeds[slot.uri_template]['batch_item_count']
                and slot.itemcount >= self.feeds[slot.uri_template]['batch_item_count']
            ):
                uri_params = self._get_uri_params(spider, self.feeds[slot.uri_template]['uri_params'], slot)
                self._close_slot(slot, spider)
                slots.append(self._start_new_batch(
                    batch_id=slot.batch_id + 1,
                    uri=slot.uri_template % uri_params,
                    feed_options=self.feeds[slot.uri_template],
                    spider=spider,
                    uri_template=slot.uri_template,
                ))
            else:
                slots.append(slot)
        self.slots = slots

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

    def _settings_are_valid(self):
        """
        If FEED_EXPORT_BATCH_ITEM_COUNT setting or FEEDS.batch_item_count is specified uri has to contain
        %(batch_time)s or %(batch_id)d to distinguish different files of partial output
        """
        for uri_template, values in self.feeds.items():
            if values['batch_item_count'] and not re.search(r'%\(batch_time\)s|%\(batch_id\)', uri_template):
                logger.error(
                    '%(batch_time)s or %(batch_id)d must be in the feed URI ({}) if FEED_EXPORT_BATCH_ITEM_COUNT '
                    'setting or FEEDS.batch_item_count is specified and greater than 0. For more info see: '
                    'https://docs.scrapy.org/en/latest/topics/feed-exports.html#feed-export-batch-item-count'
                    ''.format(uri_template)
                )
                return False
        return True

    def _storage_supported(self, uri, feed_options):
        scheme = urlparse(uri).scheme
        if scheme in self.storages:
            try:
                self._get_storage(uri, feed_options)
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

    def _get_storage(self, uri, feed_options):
        """Fork of create_instance specific to feed storage classes

        It supports not passing the *feed_options* parameters to classes that
        do not support it, and issuing a deprecation warning instead.
        """
        feedcls = self.storages[urlparse(uri).scheme]
        crawler = getattr(self, 'crawler', None)

        def build_instance(builder, *preargs):
            return build_storage(builder, uri, preargs=preargs)

        if crawler and hasattr(feedcls, 'from_crawler'):
            instance = build_instance(feedcls.from_crawler, crawler)
            method_name = 'from_crawler'
        elif hasattr(feedcls, 'from_settings'):
            instance = build_instance(feedcls.from_settings, self.settings)
            method_name = 'from_settings'
        else:
            instance = build_instance(feedcls)
            method_name = '__new__'
        if instance is None:
            raise TypeError("%s.%s returned None" % (feedcls.__qualname__, method_name))
        return instance

    def _get_uri_params(self, spider, uri_params, slot=None):
        params = {}
        for k in dir(spider):
            params[k] = getattr(spider, k)
        utc_now = datetime.utcnow()
        params['time'] = utc_now.replace(microsecond=0).isoformat().replace(':', '-')
        params['batch_time'] = utc_now.isoformat().replace(':', '-')
        params['batch_id'] = slot.batch_id + 1 if slot is not None else 1
        uripar_function = load_object(uri_params) if uri_params else lambda x, y: None
        uripar_function(params, spider)
        return params
