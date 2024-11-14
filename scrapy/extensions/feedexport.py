"""
Feed Exports extension

See documentation in docs/topics/feed-exports.rst
"""

from __future__ import annotations

import logging
import re
import sys
import warnings
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from tempfile import NamedTemporaryFile
from typing import IO, TYPE_CHECKING, Any, Optional, Protocol, TypeVar, cast
from urllib.parse import unquote, urlparse

from twisted.internet.defer import Deferred, DeferredList, maybeDeferred
from twisted.internet.threads import deferToThread
from w3lib.url import file_uri_to_path
from zope.interface import Interface, implementer

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.extensions.postprocessing import PostProcessingManager
from scrapy.settings import Settings
from scrapy.utils.conf import feed_complete_default_values_from_settings
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.ftp import ftp_store_file
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import without_none_values

if TYPE_CHECKING:
    from collections.abc import Iterable

    from _typeshed import OpenBinaryMode
    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.exporters import BaseItemExporter
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)

UriParamsCallableT = Callable[[dict[str, Any], Spider], Optional[dict[str, Any]]]

_StorageT = TypeVar("_StorageT", bound="FeedStorageProtocol")


def build_storage(
    builder: Callable[..., _StorageT],
    uri: str,
    *args: Any,
    feed_options: dict[str, Any] | None = None,
    preargs: Iterable[Any] = (),
    **kwargs: Any,
) -> _StorageT:
    warnings.warn(
        "scrapy.extensions.feedexport.build_storage() is deprecated, call the builder directly.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
    kwargs["feed_options"] = feed_options
    return builder(*preargs, uri, *args, **kwargs)


class ItemFilter:
    """
    This will be used by FeedExporter to decide if an item should be allowed
    to be exported to a particular feed.

    :param feed_options: feed specific options passed from FeedExporter
    :type feed_options: dict
    """

    feed_options: dict[str, Any] | None
    item_classes: tuple[type, ...]

    def __init__(self, feed_options: dict[str, Any] | None) -> None:
        self.feed_options = feed_options
        if feed_options is not None:
            self.item_classes = tuple(
                load_object(item_class)
                for item_class in feed_options.get("item_classes") or ()
            )
        else:
            self.item_classes = ()

    def accepts(self, item: Any) -> bool:
        """
        Return ``True`` if `item` should be exported or ``False`` otherwise.

        :param item: scraped item which user wants to check if is acceptable
        :type item: :ref:`Scrapy items <topics-items>`
        :return: `True` if accepted, `False` otherwise
        :rtype: bool
        """
        if self.item_classes:
            return isinstance(item, self.item_classes)
        return True  # accept all items by default


class IFeedStorage(Interface):
    """Interface that all Feed Storages must implement"""

    def __init__(uri, *, feed_options=None):  # pylint: disable=super-init-not-called
        """Initialize the storage with the parameters given in the URI and the
        feed-specific options (see :setting:`FEEDS`)"""

    def open(spider):
        """Open the storage for the given spider. It must return a file-like
        object that will be used for the exporters"""

    def store(file):
        """Store the given file stream"""


class FeedStorageProtocol(Protocol):
    """Reimplementation of ``IFeedStorage`` that can be used in type hints."""

    def __init__(self, uri: str, *, feed_options: dict[str, Any] | None = None):
        """Initialize the storage with the parameters given in the URI and the
        feed-specific options (see :setting:`FEEDS`)"""

    def open(self, spider: Spider) -> IO[bytes]:
        """Open the storage for the given spider. It must return a file-like
        object that will be used for the exporters"""

    def store(self, file: IO[bytes]) -> Deferred[None] | None:
        """Store the given file stream"""


@implementer(IFeedStorage)
class BlockingFeedStorage:
    def open(self, spider: Spider) -> IO[bytes]:
        path = spider.crawler.settings["FEED_TEMPDIR"]
        if path and not Path(path).is_dir():
            raise OSError("Not a Directory: " + str(path))

        return NamedTemporaryFile(prefix="feed-", dir=path)

    def store(self, file: IO[bytes]) -> Deferred[None] | None:
        return deferToThread(self._store_in_thread, file)

    def _store_in_thread(self, file: IO[bytes]) -> None:
        raise NotImplementedError


@implementer(IFeedStorage)
class StdoutFeedStorage:
    def __init__(
        self,
        uri: str,
        _stdout: IO[bytes] | None = None,
        *,
        feed_options: dict[str, Any] | None = None,
    ):
        if not _stdout:
            _stdout = sys.stdout.buffer
        self._stdout: IO[bytes] = _stdout
        if feed_options and feed_options.get("overwrite", False) is True:
            logger.warning(
                "Standard output (stdout) storage does not support "
                "overwriting. To suppress this warning, remove the "
                "overwrite option from your FEEDS setting, or set "
                "it to False."
            )

    def open(self, spider: Spider) -> IO[bytes]:
        return self._stdout

    def store(self, file: IO[bytes]) -> Deferred[None] | None:
        pass


@implementer(IFeedStorage)
class FileFeedStorage:
    def __init__(self, uri: str, *, feed_options: dict[str, Any] | None = None):
        self.path: str = file_uri_to_path(uri)
        feed_options = feed_options or {}
        self.write_mode: OpenBinaryMode = (
            "wb" if feed_options.get("overwrite", False) else "ab"
        )

    def open(self, spider: Spider) -> IO[bytes]:
        dirname = Path(self.path).parent
        if dirname and not dirname.exists():
            dirname.mkdir(parents=True)
        return Path(self.path).open(self.write_mode)

    def store(self, file: IO[bytes]) -> Deferred[None] | None:
        file.close()
        return None


class S3FeedStorage(BlockingFeedStorage):
    def __init__(
        self,
        uri: str,
        access_key: str | None = None,
        secret_key: str | None = None,
        acl: str | None = None,
        endpoint_url: str | None = None,
        *,
        feed_options: dict[str, Any] | None = None,
        session_token: str | None = None,
        region_name: str | None = None,
    ):
        try:
            import boto3.session
        except ImportError:
            raise NotConfigured("missing boto3 library")
        u = urlparse(uri)
        assert u.hostname
        self.bucketname: str = u.hostname
        self.access_key: str | None = u.username or access_key
        self.secret_key: str | None = u.password or secret_key
        self.session_token: str | None = session_token
        self.keyname: str = u.path[1:]  # remove first "/"
        self.acl: str | None = acl
        self.endpoint_url: str | None = endpoint_url
        self.region_name: str | None = region_name

        boto3_session = boto3.session.Session()
        self.s3_client = boto3_session.client(
            "s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            aws_session_token=self.session_token,
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
        )

        if feed_options and feed_options.get("overwrite", True) is False:
            logger.warning(
                "S3 does not support appending to files. To "
                "suppress this warning, remove the overwrite "
                "option from your FEEDS setting or set it to True."
            )

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        uri: str,
        *,
        feed_options: dict[str, Any] | None = None,
    ) -> Self:
        return cls(
            uri,
            access_key=crawler.settings["AWS_ACCESS_KEY_ID"],
            secret_key=crawler.settings["AWS_SECRET_ACCESS_KEY"],
            session_token=crawler.settings["AWS_SESSION_TOKEN"],
            acl=crawler.settings["FEED_STORAGE_S3_ACL"] or None,
            endpoint_url=crawler.settings["AWS_ENDPOINT_URL"] or None,
            region_name=crawler.settings["AWS_REGION_NAME"] or None,
            feed_options=feed_options,
        )

    def _store_in_thread(self, file: IO[bytes]) -> None:
        file.seek(0)
        kwargs: dict[str, Any] = {"ExtraArgs": {"ACL": self.acl}} if self.acl else {}
        self.s3_client.upload_fileobj(
            Bucket=self.bucketname, Key=self.keyname, Fileobj=file, **kwargs
        )
        file.close()


class GCSFeedStorage(BlockingFeedStorage):
    def __init__(self, uri: str, project_id: str | None, acl: str | None):
        self.project_id: str | None = project_id
        self.acl: str | None = acl
        u = urlparse(uri)
        assert u.hostname
        self.bucket_name: str = u.hostname
        self.blob_name: str = u.path[1:]  # remove first "/"

    @classmethod
    def from_crawler(cls, crawler: Crawler, uri: str) -> Self:
        return cls(
            uri,
            crawler.settings["GCS_PROJECT_ID"],
            crawler.settings["FEED_STORAGE_GCS_ACL"] or None,
        )

    def _store_in_thread(self, file: IO[bytes]) -> None:
        file.seek(0)
        from google.cloud.storage import Client

        client = Client(project=self.project_id)
        bucket = client.get_bucket(self.bucket_name)
        blob = bucket.blob(self.blob_name)
        blob.upload_from_file(file, predefined_acl=self.acl)


class FTPFeedStorage(BlockingFeedStorage):
    def __init__(
        self,
        uri: str,
        use_active_mode: bool = False,
        *,
        feed_options: dict[str, Any] | None = None,
    ):
        u = urlparse(uri)
        if not u.hostname:
            raise ValueError(f"Got a storage URI without a hostname: {uri}")
        self.host: str = u.hostname
        self.port: int = int(u.port or "21")
        self.username: str = u.username or ""
        self.password: str = unquote(u.password or "")
        self.path: str = u.path
        self.use_active_mode: bool = use_active_mode
        self.overwrite: bool = not feed_options or feed_options.get("overwrite", True)

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        uri: str,
        *,
        feed_options: dict[str, Any] | None = None,
    ) -> Self:
        return cls(
            uri,
            use_active_mode=crawler.settings.getbool("FEED_STORAGE_FTP_ACTIVE"),
            feed_options=feed_options,
        )

    def _store_in_thread(self, file: IO[bytes]) -> None:
        ftp_store_file(
            path=self.path,
            file=file,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            use_active_mode=self.use_active_mode,
            overwrite=self.overwrite,
        )


class FeedSlot:
    def __init__(
        self,
        storage: FeedStorageProtocol,
        uri: str,
        format: str,
        store_empty: bool,
        batch_id: int,
        uri_template: str,
        filter: ItemFilter,
        feed_options: dict[str, Any],
        spider: Spider,
        exporters: dict[str, type[BaseItemExporter]],
        settings: BaseSettings,
        crawler: Crawler,
    ):
        self.file: IO[bytes] | None = None
        self.exporter: BaseItemExporter | None = None
        self.storage: FeedStorageProtocol = storage
        # feed params
        self.batch_id: int = batch_id
        self.format: str = format
        self.store_empty: bool = store_empty
        self.uri_template: str = uri_template
        self.uri: str = uri
        self.filter: ItemFilter = filter
        # exporter params
        self.feed_options: dict[str, Any] = feed_options
        self.spider: Spider = spider
        self.exporters: dict[str, type[BaseItemExporter]] = exporters
        self.settings: BaseSettings = settings
        self.crawler: Crawler = crawler
        # flags
        self.itemcount: int = 0
        self._exporting: bool = False
        self._fileloaded: bool = False

    def start_exporting(self) -> None:
        if not self._fileloaded:
            self.file = self.storage.open(self.spider)
            if "postprocessing" in self.feed_options:
                self.file = cast(
                    IO[bytes],
                    PostProcessingManager(
                        self.feed_options["postprocessing"],
                        self.file,
                        self.feed_options,
                    ),
                )
            self.exporter = self._get_exporter(
                file=self.file,
                format=self.feed_options["format"],
                fields_to_export=self.feed_options["fields"],
                encoding=self.feed_options["encoding"],
                indent=self.feed_options["indent"],
                **self.feed_options["item_export_kwargs"],
            )
            self._fileloaded = True

        if not self._exporting:
            assert self.exporter
            self.exporter.start_exporting()
            self._exporting = True

    def _get_exporter(
        self, file: IO[bytes], format: str, *args: Any, **kwargs: Any
    ) -> BaseItemExporter:
        return build_from_crawler(
            self.exporters[format], self.crawler, file, *args, **kwargs
        )

    def finish_exporting(self) -> None:
        if self._exporting:
            assert self.exporter
            self.exporter.finish_exporting()
            self._exporting = False


class FeedExporter:
    _pending_deferreds: list[Deferred[None]] = []

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        exporter = cls(crawler)
        crawler.signals.connect(exporter.open_spider, signals.spider_opened)
        crawler.signals.connect(exporter.close_spider, signals.spider_closed)
        crawler.signals.connect(exporter.item_scraped, signals.item_scraped)
        return exporter

    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler
        self.settings: Settings = crawler.settings
        self.feeds = {}
        self.slots: list[FeedSlot] = []
        self.filters: dict[str, ItemFilter] = {}

        if not self.settings["FEEDS"] and not self.settings["FEED_URI"]:
            raise NotConfigured

        # Begin: Backward compatibility for FEED_URI and FEED_FORMAT settings
        if self.settings["FEED_URI"]:
            warnings.warn(
                "The `FEED_URI` and `FEED_FORMAT` settings have been deprecated in favor of "
                "the `FEEDS` setting. Please see the `FEEDS` setting docs for more details",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
            uri = self.settings["FEED_URI"]
            # handle pathlib.Path objects
            uri = str(uri) if not isinstance(uri, Path) else uri.absolute().as_uri()
            feed_options = {"format": self.settings.get("FEED_FORMAT", "jsonlines")}
            self.feeds[uri] = feed_complete_default_values_from_settings(
                feed_options, self.settings
            )
            self.filters[uri] = self._load_filter(feed_options)
        # End: Backward compatibility for FEED_URI and FEED_FORMAT settings

        # 'FEEDS' setting takes precedence over 'FEED_URI'
        for uri, feed_options in self.settings.getdict("FEEDS").items():
            # handle pathlib.Path objects
            uri = str(uri) if not isinstance(uri, Path) else uri.absolute().as_uri()
            self.feeds[uri] = feed_complete_default_values_from_settings(
                feed_options, self.settings
            )
            self.filters[uri] = self._load_filter(feed_options)

        self.storages: dict[str, type[FeedStorageProtocol]] = self._load_components(
            "FEED_STORAGES"
        )
        self.exporters: dict[str, type[BaseItemExporter]] = self._load_components(
            "FEED_EXPORTERS"
        )
        for uri, feed_options in self.feeds.items():
            if not self._storage_supported(uri, feed_options):
                raise NotConfigured
            if not self._settings_are_valid():
                raise NotConfigured
            if not self._exporter_supported(feed_options["format"]):
                raise NotConfigured

    def open_spider(self, spider: Spider) -> None:
        for uri, feed_options in self.feeds.items():
            uri_params = self._get_uri_params(spider, feed_options["uri_params"])
            self.slots.append(
                self._start_new_batch(
                    batch_id=1,
                    uri=uri % uri_params,
                    feed_options=feed_options,
                    spider=spider,
                    uri_template=uri,
                )
            )

    async def close_spider(self, spider: Spider) -> None:
        for slot in self.slots:
            self._close_slot(slot, spider)

        # Await all deferreds
        if self._pending_deferreds:
            await maybe_deferred_to_future(DeferredList(self._pending_deferreds))

        # Send FEED_EXPORTER_CLOSED signal
        await maybe_deferred_to_future(
            self.crawler.signals.send_catch_log_deferred(signals.feed_exporter_closed)
        )

    def _close_slot(self, slot: FeedSlot, spider: Spider) -> Deferred[None] | None:
        def get_file(slot_: FeedSlot) -> IO[bytes]:
            assert slot_.file
            if isinstance(slot_.file, PostProcessingManager):
                slot_.file.close()
                return slot_.file.file
            return slot_.file

        if slot.itemcount:
            # Normal case
            slot.finish_exporting()
        elif slot.store_empty and slot.batch_id == 1:
            # Need to store the empty file
            slot.start_exporting()
            slot.finish_exporting()
        else:
            # In this case, the file is not stored, so no processing is required.
            return None

        logmsg = f"{slot.format} feed ({slot.itemcount} items) in: {slot.uri}"
        d: Deferred[None] = maybeDeferred(slot.storage.store, get_file(slot))  # type: ignore[call-overload]

        d.addCallback(
            self._handle_store_success, logmsg, spider, type(slot.storage).__name__
        )
        d.addErrback(
            self._handle_store_error, logmsg, spider, type(slot.storage).__name__
        )
        self._pending_deferreds.append(d)
        d.addCallback(
            lambda _: self.crawler.signals.send_catch_log_deferred(
                signals.feed_slot_closed, slot=slot
            )
        )
        d.addBoth(lambda _: self._pending_deferreds.remove(d))

        return d

    def _handle_store_error(
        self, f: Failure, logmsg: str, spider: Spider, slot_type: str
    ) -> None:
        logger.error(
            "Error storing %s",
            logmsg,
            exc_info=failure_to_exc_info(f),
            extra={"spider": spider},
        )
        assert self.crawler.stats
        self.crawler.stats.inc_value(f"feedexport/failed_count/{slot_type}")

    def _handle_store_success(
        self, result: Any, logmsg: str, spider: Spider, slot_type: str
    ) -> None:
        logger.info("Stored %s", logmsg, extra={"spider": spider})
        assert self.crawler.stats
        self.crawler.stats.inc_value(f"feedexport/success_count/{slot_type}")

    def _start_new_batch(
        self,
        batch_id: int,
        uri: str,
        feed_options: dict[str, Any],
        spider: Spider,
        uri_template: str,
    ) -> FeedSlot:
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
        slot = FeedSlot(
            storage=storage,
            uri=uri,
            format=feed_options["format"],
            store_empty=feed_options["store_empty"],
            batch_id=batch_id,
            uri_template=uri_template,
            filter=self.filters[uri_template],
            feed_options=feed_options,
            spider=spider,
            exporters=self.exporters,
            settings=self.settings,
            crawler=self.crawler,
        )
        return slot

    def item_scraped(self, item: Any, spider: Spider) -> None:
        slots = []
        for slot in self.slots:
            if not slot.filter.accepts(item):
                slots.append(
                    slot
                )  # if slot doesn't accept item, continue with next slot
                continue

            slot.start_exporting()
            assert slot.exporter
            slot.exporter.export_item(item)
            slot.itemcount += 1
            # create new slot for each slot with itemcount == FEED_EXPORT_BATCH_ITEM_COUNT and close the old one
            if (
                self.feeds[slot.uri_template]["batch_item_count"]
                and slot.itemcount >= self.feeds[slot.uri_template]["batch_item_count"]
            ):
                uri_params = self._get_uri_params(
                    spider, self.feeds[slot.uri_template]["uri_params"], slot
                )
                self._close_slot(slot, spider)
                slots.append(
                    self._start_new_batch(
                        batch_id=slot.batch_id + 1,
                        uri=slot.uri_template % uri_params,
                        feed_options=self.feeds[slot.uri_template],
                        spider=spider,
                        uri_template=slot.uri_template,
                    )
                )
            else:
                slots.append(slot)
        self.slots = slots

    def _load_components(self, setting_prefix: str) -> dict[str, Any]:
        conf = without_none_values(
            cast(dict[str, str], self.settings.getwithbase(setting_prefix))
        )
        d = {}
        for k, v in conf.items():
            try:
                d[k] = load_object(v)
            except NotConfigured:
                pass
        return d

    def _exporter_supported(self, format: str) -> bool:
        if format in self.exporters:
            return True
        logger.error("Unknown feed format: %(format)s", {"format": format})
        return False

    def _settings_are_valid(self) -> bool:
        """
        If FEED_EXPORT_BATCH_ITEM_COUNT setting or FEEDS.batch_item_count is specified uri has to contain
        %(batch_time)s or %(batch_id)d to distinguish different files of partial output
        """
        for uri_template, values in self.feeds.items():
            if values["batch_item_count"] and not re.search(
                r"%\(batch_time\)s|%\(batch_id\)", uri_template
            ):
                logger.error(
                    "%%(batch_time)s or %%(batch_id)d must be in the feed URI (%s) if FEED_EXPORT_BATCH_ITEM_COUNT "
                    "setting or FEEDS.batch_item_count is specified and greater than 0. For more info see: "
                    "https://docs.scrapy.org/en/latest/topics/feed-exports.html#feed-export-batch-item-count",
                    uri_template,
                )
                return False
        return True

    def _storage_supported(self, uri: str, feed_options: dict[str, Any]) -> bool:
        scheme = urlparse(uri).scheme
        if scheme in self.storages or PureWindowsPath(uri).drive:
            try:
                self._get_storage(uri, feed_options)
                return True
            except NotConfigured as e:
                logger.error(
                    "Disabled feed storage scheme: %(scheme)s. " "Reason: %(reason)s",
                    {"scheme": scheme, "reason": str(e)},
                )
        else:
            logger.error("Unknown feed storage scheme: %(scheme)s", {"scheme": scheme})
        return False

    def _get_storage(
        self, uri: str, feed_options: dict[str, Any]
    ) -> FeedStorageProtocol:
        feedcls = self.storages.get(urlparse(uri).scheme, self.storages["file"])
        return build_from_crawler(feedcls, self.crawler, uri, feed_options=feed_options)

    def _get_uri_params(
        self,
        spider: Spider,
        uri_params_function: str | UriParamsCallableT | None,
        slot: FeedSlot | None = None,
    ) -> dict[str, Any]:
        params = {}
        for k in dir(spider):
            params[k] = getattr(spider, k)
        utc_now = datetime.now(tz=timezone.utc)
        params["time"] = utc_now.replace(microsecond=0).isoformat().replace(":", "-")
        params["batch_time"] = utc_now.isoformat().replace(":", "-")
        params["batch_id"] = slot.batch_id + 1 if slot is not None else 1
        uripar_function: UriParamsCallableT = (
            load_object(uri_params_function)
            if uri_params_function
            else lambda params, _: params
        )
        new_params = uripar_function(params, spider)
        return new_params if new_params is not None else params

    def _load_filter(self, feed_options: dict[str, Any]) -> ItemFilter:
        # load the item filter if declared else load the default filter class
        item_filter_class: type[ItemFilter] = load_object(
            feed_options.get("item_filter", ItemFilter)
        )
        return item_filter_class(feed_options)
