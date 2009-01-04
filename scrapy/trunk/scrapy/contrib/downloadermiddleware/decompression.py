import zipfile
import tarfile
import gzip
import bz2
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

from scrapy import log
from scrapy.http import Response

class DecompressionMiddleware(object):
    """ This middleware tries to recognise and extract the possibly compressed
    responses that may arrive. """

    def __init__(self):
        self.decompressors = {
            'tar': self.is_tar,
            'zip': self.is_zip,
            'gz': self.is_gzip,
            'bz2': self.is_bzip2
        }

    def is_tar(self, response):
        try:
            tar_file = tarfile.open(name='tar.tmp', fileobj=self.archive)
        except tarfile.ReadError:
            return False
        if tar_file.members:
            return response.replace(body=tar_file.extractfile(tar_file.members[0]).read())
        else:
            raise self.ArchiveIsEmpty

    def is_zip(self, response):
        try:
            zip_file = zipfile.ZipFile(self.archive)
        except zipfile.BadZipfile:
            return False
        namelist = zip_file.namelist()
        if namelist:
            return response.replace(body=zip_file.read(namelist[0]))
        else:
            raise self.ArchiveIsEmpty

    def is_gzip(self, response):
        try:
            gzip_file = gzip.GzipFile(fileobj=self.archive)
            decompressed_body = gzip_file.read()
        except IOError:
            return False
        return response.replace(body=decompressed_body)

    def is_bzip2(self, response):
        try:
            decompressed_body = bz2.decompress(self.body)
        except IOError:
            return False
        return response.replace(body=decompressed_body)

    def extract(self, response):
        """ This method tries to decompress the given response, if possible,
        and returns a tuple containing the resulting response, and the name
        of the used decompressor """

        self.body = response.body.to_string()
        self.archive = StringIO()
        self.archive.write(self.body)

        for decompressor in self.decompressors.keys():
            self.archive.seek(0)
            new_response = self.decompressors[decompressor](response)
            if new_response:
                return (new_response, decompressor)
        return (response, None)

    def process_response(self, request, response, spider):
        if isinstance(response, Response):
            response, format = self.extract(response)
            if format:
                log.msg('Decompressed response with format: %s' % format, log.DEBUG, domain=spider.domain_name)
        return response
