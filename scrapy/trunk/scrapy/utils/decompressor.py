"""
Utility for autodetecting and decompressing responses
"""

import zipfile
import tarfile
import gzip
import bz2
from tempfile import NamedTemporaryFile
from scrapy.http import ResponseBody

class Decompressor(object):
    class ArchiveIsEmpty(Exception):
        pass
    
    def extract(self, response):
        temp = NamedTemporaryFile()
        temp.file.write(response.body.to_string())
        temp.file.seek(0)
        
        if tarfile.is_tarfile(temp.name):
            tar = tarfile.open(temp.name)
            if tar.members:
                return response.replace(body=ResponseBody(tar.extractfile(tar.members[0]).read()))
            else:
                raise self.ArchiveIsEmpty
           
        elif zipfile.is_zipfile(temp.name):
            zipf = zipfile.ZipFile(temp.name, 'r')
            namelist = zipf.namelist()
            if namelist:
                return response.replace(body=ResponseBody(zipf.read(namelist[0])))
            else:
                raise self.ArchiveIsEmpty
           
        else:
            # It's neither a tar or a zip, so we try to decompress using Gzip now
            try:
                gzip_file = gzip.GzipFile(temp.name)
                return response.replace(body=ResponseBody(gzip_file.read()))
            except IOError:
                pass
      
            # Finally, we try with Bzip2
            try:
                bzip_file = bz2.BZ2File(temp.name)
                return response.replace(body=ResponseBody(bzip_file.read()))
            except IOError:
                pass
        
            # We couldn't decompress the file, so we return the same response
            return response
    
