"""
Utility for autodetecting and decompressing responses
"""

import zipfile
import tarfile
import gzip
import bz2
from cStringIO import StringIO
from scrapy.http import ResponseBody

class Decompressor(object):
    class ArchiveIsEmpty(Exception):
        pass
    
    def __init__(self):
        self.decompressors = [self.is_tar, self.is_zip,
                              self.is_gzip, self.is_bzip2]        
    def is_tar(self, response):
        try:
            tar_file = tarfile.open(fileobj=self.archive)
        except tarfile.ReadError:
            return False
        if tar_file.members:
            return response.replace(body=ResponseBody(tar_file.extractfile(tar_file.members[0]).read()))
        else:
            raise self.ArchiveIsEmpty
    
    def is_zip(self, response):
        try:
            zip_file = zipfile.ZipFile(self.archive)
        except zipfile.BadZipfile:
            return False
        namelist = zip_file.namelist()
        if namelist:
            return response.replace(body=ResponseBody(zip_file.read(namelist[0])))
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
        return response.replace(body=ResponseBody(decompressed_body))
            
    def extract(self, response):
        self.body = response.body.to_string()
        self.archive = StringIO()
        self.archive.write(self.body)

        for decompressor in self.decompressors:
            self.archive.seek(0)
            ret = decompressor(response)
            if ret:
                return ret
        return response
