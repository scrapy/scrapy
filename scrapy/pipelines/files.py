"""
Files Pipeline

See documentation in topics/media-pipeline.rst
"""
import base64
import functools
import hashlib
import logging
import mimetypes
import os
import time
from collections import defaultdict
from contextlib import suppress
from ftplib import FTP
from io import BytesIO
from os import PathLike
from pathlib import Path
from typing import DefaultDict, Optional, Set, Union
from urllib.parse import urlparse

from itemadapter import ItemAdapter
from twisted.internet import defer, threads

from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.media import MediaPipeline
from scrapy.settings import Settings
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.datatypes import CaselessDict
from scrapy.utils.ftp import ftp_store_file
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import md5sum
from scrapy.utils.python import to_bytes
from scrapy.utils.request import referer_str

logger = logging.getLogger(__name__)


def _to_string(path: Union[str, PathLike]) -> str:
    return str(path)  # convert a Path object to string


class FileException(Exception):
    """General media error exception"""


class FSFilesStore:
    def __init__(self, basedir: Union[str, PathLike]):
        basedir = _to_string(basedir)
        if "://" in basedir:
            basedir = basedir.split("://", 1)[1]
        self.basedir = basedir
        self._mkdir(Path(self.basedir))
        self.created_directories: DefaultDict[str, Set[str]] = defaultdict(set)

    def persist_file(
        self, path: Union[str, PathLike], buf, info, meta=None, headers=None
    ):
        absolute_path = self._get_filesystem_path(path)
        self._mkdir(absolute_path.parent, info)
        absolute_path.write_bytes(buf.getvalue())

    def stat_file(self, path: Union[str, PathLike], info):
        absolute_path = self._get_filesystem_path(path)
        try:
            last_modified = absolute_path.stat().st_mtime
        except os.error:
            return {}

        with absolute_path.open("rb") as f:
            checksum = md5sum(f)

        return {"last_modified": last_modified, "checksum": checksum}

    def _get_filesystem_path(self, path: Union[str, PathLike]) -> Path:
        path_comps = _to_string(path).split("/")
        return Path(self.basedir, *path_comps)

    def _mkdir(self, dirname: Path, domain: Optional[str] = None):
        seen = self.created_directories[domain] if domain else set()
        if str(dirname) not in seen:
            if not dirname.exists():
                dirname.mkdir(parents=True)
            seen.add(str(dirname))


class S3FilesStore:
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_SESSION_TOKEN = None
    AWS_ENDPOINT_URL = None
    AWS_REGION_NAME = None
    AWS_USE_SSL = None
    AWS_VERIFY = None

    POLICY = "private"  # Overridden from settings.FILES_STORE_S3_ACL in FilesPipeline.from_settings
    HEADERS = {
        "Cache-Control": "max-age=172800",
    }

    def __init__(self, uri):
        if not is_botocore_available():
            raise NotConfigured("missing botocore library")
        import botocore.session

        session = botocore.session.get_session()
        self.s3_client = session.create_client(
            "s3",
            aws_access_key_id=self.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.AWS_SECRET_ACCESS_KEY,
            aws_session_token=self.AWS_SESSION_TOKEN,
            endpoint_url=self.AWS_ENDPOINT_URL,
            region_name=self.AWS_REGION_NAME,
            use_ssl=self.AWS_USE_SSL,
            verify=self.AWS_VERIFY,
        )
        if not uri.startswith("s3://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 's3'")
        self.bucket, self.prefix = uri[5:].split("/", 1)

    def stat_file(self, path, info):
        def _onsuccess(boto_key):
            checksum = boto_key["ETag"].strip('"')
            last_modified = boto_key["LastModified"]
            modified_stamp = time.mktime(last_modified.timetuple())
            return {"checksum": checksum, "last_modified": modified_stamp}

        return self._get_boto_key(path).addCallback(_onsuccess)

    def _get_boto_key(self, path):
        key_name = f"{self.prefix}{path}"
        return threads.deferToThread(
            self.s3_client.head_object, Bucket=self.bucket, Key=key_name
        )

    def persist_file(self, path, buf, info, meta=None, headers=None):
        """Upload file to S3 storage"""
        key_name = f"{self.prefix}{path}"
        buf.seek(0)
        extra = self._headers_to_botocore_kwargs(self.HEADERS)
        if headers:
            extra.update(self._headers_to_botocore_kwargs(headers))
        return threads.deferToThread(
            self.s3_client.put_object,
            Bucket=self.bucket,
            Key=key_name,
            Body=buf,
            Metadata={k: str(v) for k, v in (meta or {}).items()},
            ACL=self.POLICY,
            **extra,
        )

    def _headers_to_botocore_kwargs(self, headers):
        """Convert headers to botocore keyword arguments."""
        # This is required while we need to support both boto and botocore.
        mapping = CaselessDict(
            {
                "Content-Type": "ContentType",
                "Cache-Control": "CacheControl",
                "Content-Disposition": "ContentDisposition",
                "Content-Encoding": "ContentEncoding",
                "Content-Language": "ContentLanguage",
                "Content-Length": "ContentLength",
                "Content-MD5": "ContentMD5",
                "Expires": "Expires",
                "X-Amz-Grant-Full-Control": "GrantFullControl",
                "X-Amz-Grant-Read": "GrantRead",
                "X-Amz-Grant-Read-ACP": "GrantReadACP",
                "X-Amz-Grant-Write-ACP": "GrantWriteACP",
                "X-Amz-Object-Lock-Legal-Hold": "ObjectLockLegalHoldStatus",
                "X-Amz-Object-Lock-Mode": "ObjectLockMode",
                "X-Amz-Object-Lock-Retain-Until-Date": "ObjectLockRetainUntilDate",
                "X-Amz-Request-Payer": "RequestPayer",
                "X-Amz-Server-Side-Encryption": "ServerSideEncryption",
                "X-Amz-Server-Side-Encryption-Aws-Kms-Key-Id": "SSEKMSKeyId",
                "X-Amz-Server-Side-Encryption-Context": "SSEKMSEncryptionContext",
                "X-Amz-Server-Side-Encryption-Customer-Algorithm": "SSECustomerAlgorithm",
                "X-Amz-Server-Side-Encryption-Customer-Key": "SSECustomerKey",
                "X-Amz-Server-Side-Encryption-Customer-Key-Md5": "SSECustomerKeyMD5",
                "X-Amz-Storage-Class": "StorageClass",
                "X-Amz-Tagging": "Tagging",
                "X-Amz-Website-Redirect-Location": "WebsiteRedirectLocation",
            }
        )
        extra = {}
        for key, value in headers.items():
            try:
                kwarg = mapping[key]
            except KeyError:
                raise TypeError(f'Header "{key}" is not supported by botocore')
            else:
                extra[kwarg] = value
        return extra


class GCSFilesStore:
    GCS_PROJECT_ID = None

    CACHE_CONTROL = "max-age=172800"

    # The bucket's default object ACL will be applied to the object.
    # Overridden from settings.FILES_STORE_GCS_ACL in FilesPipeline.from_settings.
    POLICY = None

    def __init__(self, uri):
        from google.cloud import storage

        client = storage.Client(project=self.GCS_PROJECT_ID)
        bucket, prefix = uri[5:].split("/", 1)
        self.bucket = client.bucket(bucket)
        self.prefix = prefix
        permissions = self.bucket.test_iam_permissions(
            ["storage.objects.get", "storage.objects.create"]
        )
        if "storage.objects.get" not in permissions:
            logger.warning(
                "No 'storage.objects.get' permission for GSC bucket %(bucket)s. "
                "Checking if files are up to date will be impossible. Files will be downloaded every time.",
                {"bucket": bucket},
            )
        if "storage.objects.create" not in permissions:
            logger.error(
                "No 'storage.objects.create' permission for GSC bucket %(bucket)s. Saving files will be impossible!",
                {"bucket": bucket},
            )

    def stat_file(self, path, info):
        def _onsuccess(blob):
            if blob:
                checksum = base64.b64decode(blob.md5_hash).hex()
                last_modified = time.mktime(blob.updated.timetuple())
                return {"checksum": checksum, "last_modified": last_modified}
            return {}

        blob_path = self._get_blob_path(path)
        return threads.deferToThread(self.bucket.get_blob, blob_path).addCallback(
            _onsuccess
        )

    def _get_content_type(self, headers):
        if headers and "Content-Type" in headers:
            return headers["Content-Type"]
        return "application/octet-stream"

    def _get_blob_path(self, path):
        return self.prefix + path

    def persist_file(self, path, buf, info, meta=None, headers=None):
        blob_path = self._get_blob_path(path)
        blob = self.bucket.blob(blob_path)
        blob.cache_control = self.CACHE_CONTROL
        blob.metadata = {k: str(v) for k, v in (meta or {}).items()}
        return threads.deferToThread(
            blob.upload_from_string,
            data=buf.getvalue(),
            content_type=self._get_content_type(headers),
            predefined_acl=self.POLICY,
        )


class FTPFilesStore:
    FTP_USERNAME = None
    FTP_PASSWORD = None
    USE_ACTIVE_MODE = None

    def __init__(self, uri):
        if not uri.startswith("ftp://"):
            raise ValueError(f"Incorrect URI scheme in {uri}, expected 'ftp'")
        u = urlparse(uri)
        self.port = u.port
        self.host = u.hostname
        self.port = int(u.port or 21)
        self.username = u.username or self.FTP_USERNAME
        self.password = u.password or self.FTP_PASSWORD
        self.basedir = u.path.rstrip("/")

    def persist_file(self, path, buf, info, meta=None, headers=None):
        path = f"{self.basedir}/{path}"
        return threads.deferToThread(
            ftp_store_file,
            path=path,
            file=buf,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            use_active_mode=self.USE_ACTIVE_MODE,
        )

    def stat_file(self, path, info):
        def _stat_file(path):
            try:
                ftp = FTP()
                ftp.connect(self.host, self.port)
                ftp.login(self.username, self.password)
                if self.USE_ACTIVE_MODE:
                    ftp.set_pasv(False)
                file_path = f"{self.basedir}/{path}"
                last_modified = float(ftp.voidcmd(f"MDTM {file_path}")[4:].strip())
                m = hashlib.md5()
                ftp.retrbinary(f"RETR {file_path}", m.update)
                return {"last_modified": last_modified, "checksum": m.hexdigest()}
            # The file doesn't exist
            except Exception:
                return {}

        return threads.deferToThread(_stat_file, path)


class FilesPipeline(MediaPipeline):
    """Abstract pipeline that implement the file downloading

    This pipeline tries to minimize network transfers and file processing,
    doing stat of the files and determining if file is new, up-to-date or
    expired.

    ``new`` files are those that pipeline never processed and needs to be
        downloaded from supplier site the first time.

    ``uptodate`` files are the ones that the pipeline processed and are still
        valid files.

    ``expired`` files are those that pipeline already processed but the last
        modification was made long time ago, so a reprocessing is recommended to
        refresh it in case of change.

    """

    MEDIA_NAME = "file"
    EXPIRES = 90
    STORE_SCHEMES = {
        "": FSFilesStore,
        "file": FSFilesStore,
        "s3": S3FilesStore,
        "gs": GCSFilesStore,
        "ftp": FTPFilesStore,
    }
    DEFAULT_FILES_URLS_FIELD = "file_urls"
    DEFAULT_FILES_RESULT_FIELD = "files"

    def __init__(self, store_uri, download_func=None, settings=None):
        store_uri = _to_string(store_uri)
        if not store_uri:
            raise NotConfigured

        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)
        cls_name = "FilesPipeline"
        self.store = self._get_store(store_uri)
        resolve = functools.partial(
            self._key_for_pipe, base_class_name=cls_name, settings=settings
        )
        self.expires = settings.getint(resolve("FILES_EXPIRES"), self.EXPIRES)
        if not hasattr(self, "FILES_URLS_FIELD"):
            self.FILES_URLS_FIELD = self.DEFAULT_FILES_URLS_FIELD
        if not hasattr(self, "FILES_RESULT_FIELD"):
            self.FILES_RESULT_FIELD = self.DEFAULT_FILES_RESULT_FIELD
        self.files_urls_field = settings.get(
            resolve("FILES_URLS_FIELD"), self.FILES_URLS_FIELD
        )
        self.files_result_field = settings.get(
            resolve("FILES_RESULT_FIELD"), self.FILES_RESULT_FIELD
        )

        super().__init__(download_func=download_func, settings=settings)

    @classmethod
    def from_settings(cls, settings):
        s3store = cls.STORE_SCHEMES["s3"]
        s3store.AWS_ACCESS_KEY_ID = settings["AWS_ACCESS_KEY_ID"]
        s3store.AWS_SECRET_ACCESS_KEY = settings["AWS_SECRET_ACCESS_KEY"]
        s3store.AWS_SESSION_TOKEN = settings["AWS_SESSION_TOKEN"]
        s3store.AWS_ENDPOINT_URL = settings["AWS_ENDPOINT_URL"]
        s3store.AWS_REGION_NAME = settings["AWS_REGION_NAME"]
        s3store.AWS_USE_SSL = settings["AWS_USE_SSL"]
        s3store.AWS_VERIFY = settings["AWS_VERIFY"]
        s3store.POLICY = settings["FILES_STORE_S3_ACL"]

        gcs_store = cls.STORE_SCHEMES["gs"]
        gcs_store.GCS_PROJECT_ID = settings["GCS_PROJECT_ID"]
        gcs_store.POLICY = settings["FILES_STORE_GCS_ACL"] or None

        ftp_store = cls.STORE_SCHEMES["ftp"]
        ftp_store.FTP_USERNAME = settings["FTP_USER"]
        ftp_store.FTP_PASSWORD = settings["FTP_PASSWORD"]
        ftp_store.USE_ACTIVE_MODE = settings.getbool("FEED_STORAGE_FTP_ACTIVE")

        store_uri = settings["FILES_STORE"]
        return cls(store_uri, settings=settings)

    def _get_store(self, uri: str):
        if Path(uri).is_absolute():  # to support win32 paths like: C:\\some\dir
            scheme = "file"
        else:
            scheme = urlparse(uri).scheme
        store_cls = self.STORE_SCHEMES[scheme]
        return store_cls(uri)

    def media_to_download(self, request, info, *, item=None):
        def _onsuccess(result):
            if not result:
                return  # returning None force download

            last_modified = result.get("last_modified", None)
            if not last_modified:
                return  # returning None force download

            age_seconds = time.time() - last_modified
            age_days = age_seconds / 60 / 60 / 24
            if age_days > self.expires:
                return  # returning None force download

            referer = referer_str(request)
            logger.debug(
                "File (uptodate): Downloaded %(medianame)s from %(request)s "
                "referred in <%(referer)s>",
                {"medianame": self.MEDIA_NAME, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            self.inc_stats(info.spider, "uptodate")

            checksum = result.get("checksum", None)
            return {
                "url": request.url,
                "path": path,
                "checksum": checksum,
                "status": "uptodate",
            }

        path = self.file_path(request, info=info, item=item)
        dfd = defer.maybeDeferred(self.store.stat_file, path, info)
        dfd.addCallbacks(_onsuccess, lambda _: None)
        dfd.addErrback(
            lambda f: logger.error(
                self.__class__.__name__ + ".store.stat_file",
                exc_info=failure_to_exc_info(f),
                extra={"spider": info.spider},
            )
        )
        return dfd

    def media_failed(self, failure, request, info):
        if not isinstance(failure.value, IgnoreRequest):
            referer = referer_str(request)
            logger.warning(
                "File (unknown-error): Error downloading %(medianame)s from "
                "%(request)s referred in <%(referer)s>: %(exception)s",
                {
                    "medianame": self.MEDIA_NAME,
                    "request": request,
                    "referer": referer,
                    "exception": failure.value,
                },
                extra={"spider": info.spider},
            )

        raise FileException

    def media_downloaded(self, response, request, info, *, item=None):
        referer = referer_str(request)

        if response.status != 200:
            logger.warning(
                "File (code: %(status)s): Error downloading file from "
                "%(request)s referred in <%(referer)s>",
                {"status": response.status, "request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("download-error")

        if not response.body:
            logger.warning(
                "File (empty-content): Empty file from %(request)s referred "
                "in <%(referer)s>: no-content",
                {"request": request, "referer": referer},
                extra={"spider": info.spider},
            )
            raise FileException("empty-content")

        status = "cached" if "cached" in response.flags else "downloaded"
        logger.debug(
            "File (%(status)s): Downloaded file from %(request)s referred in "
            "<%(referer)s>",
            {"status": status, "request": request, "referer": referer},
            extra={"spider": info.spider},
        )
        self.inc_stats(info.spider, status)

        try:
            path = self.file_path(request, response=response, info=info, item=item)
            checksum = self.file_downloaded(response, request, info, item=item)
        except FileException as exc:
            logger.warning(
                "File (error): Error processing file from %(request)s "
                "referred in <%(referer)s>: %(errormsg)s",
                {"request": request, "referer": referer, "errormsg": str(exc)},
                extra={"spider": info.spider},
                exc_info=True,
            )
            raise
        except Exception as exc:
            logger.error(
                "File (unknown-error): Error processing file from %(request)s "
                "referred in <%(referer)s>",
                {"request": request, "referer": referer},
                exc_info=True,
                extra={"spider": info.spider},
            )
            raise FileException(str(exc))

        return {
            "url": request.url,
            "path": path,
            "checksum": checksum,
            "status": status,
        }

    def inc_stats(self, spider, status):
        spider.crawler.stats.inc_value("file_count", spider=spider)
        spider.crawler.stats.inc_value(f"file_status_count/{status}", spider=spider)

    # Overridable Interface
    def get_media_requests(self, item, info):
        urls = ItemAdapter(item).get(self.files_urls_field, [])
        return [Request(u, callback=NO_CALLBACK) for u in urls]

    def file_downloaded(self, response, request, info, *, item=None):
        path = self.file_path(request, response=response, info=info, item=item)
        buf = BytesIO(response.body)
        checksum = md5sum(buf)
        buf.seek(0)
        self.store.persist_file(path, buf, info)
        return checksum

    def item_completed(self, results, item, info):
        with suppress(KeyError):
            ItemAdapter(item)[self.files_result_field] = [x for ok, x in results if ok]
        return item

    def file_path(self, request, response=None, info=None, *, item=None):
        media_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()
        media_ext = Path(request.url).suffix
        # Handles empty and wild extensions by trying to guess the
        # mime type then extension or default to empty string otherwise
        if media_ext not in mimetypes.types_map:
            media_ext = ""
            media_type = mimetypes.guess_type(request.url)[0]
            if media_type:
                media_ext = mimetypes.guess_extension(media_type)
        return f"full/{media_guid}{media_ext}"
