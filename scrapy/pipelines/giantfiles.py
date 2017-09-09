from scrapy.http.request.giantfiles import GiantFilesRequest
from scrapy.pipelines.files import FilesPipeline

from scrapy.utils.misc import md5sum

class GiantFilesPipeline(FilesPipeline):
    """Abstract pipeline that implement the giant file downloading
    """
    def gen_giant_file_request(self,url): 
   
        return GiantFilesRequest(url,self.store.basedir)
    
        #GiantFilesPipeline._get_store(
    def get_media_requests(self, item, info):
        #print self.store.basedir
        return [GiantFilesRequest(x,self.store.basedir) for x in item.get(self.files_urls_field, [])]
    def file_downloaded(self, response, request, info):
        if isinstance(request,GiantFilesRequest):
            #response.body here is the stream of the giant file in fact 
            checksum=""
            try:
                f = open(response.body,'r')
                checksum = md5sum(f)
            finally:
                f.close()
            
            return checksum
        else:
            raise Exception("Type error: not  a request of a giantfile")