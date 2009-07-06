import rfc822

from scrapy.http import Request
from scrapy.core.engine import scrapyengine
from scrapy.core.exceptions import NotConfigured
from scrapy.contrib.pipeline.images import BaseImagesPipeline, md5sum
from scrapy.conf import settings


class S3ImagesPipeline(BaseImagesPipeline):
    """Images pipeline with amazon S3 support as image's store backend

    This pipeline tries to minimize the PUT requests made to amazon doing a
    HEAD per full image, if HEAD returns a successfully response, then the
    Last-Modified header is compared to current timestamp and if the difference
    in days are greater that IMAGE_EXPIRES setting, then the image is
    downloaded, reprocessed and uploaded to S3 again including its thumbnails.

    It is recommended to add an spider with domain_name 's3.amazonaws.com',
    doing that you will overcome the limit of request per spider. The following
    is the minimal code for this spider:

        from scrapy.spider import BaseSpider

        class S3AmazonAWSSpider(BaseSpider):
            domain_name = "s3.amazonaws.com"
            max_concurrent_requests = 100
            start_urls = ('http://s3.amazonaws.com/',)

        SPIDER = S3AmazonAWSSpider()

    Commonly uploading images to S3 requires requests to be signed, the
    recommended way is to enable scrapy.contrib.aws.AWSMiddleware downloader
    middleware and configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
    settings

    More info about amazon S3 at http://docs.amazonwebservices.com/AmazonS3/2006-03-01/

    """

    # amazon s3 bucket name to put images
    bucket_name = settings.get('S3_BUCKET')

    # prefix to prepend to image keys
    key_prefix = settings.get('S3_PREFIX', '')

    # Optional spider to use for image uploading
    AmazonS3Spider = None

    def __init__(self):
        if not settings['S3_IMAGES']:
            raise NotConfigured
        super(S3ImagesPipeline, self).__init__()

    def s3_request(self, key, method, body=None, headers=None):
        url = 'http://%s.s3.amazonaws.com/%s%s' % (self.bucket_name, self.key_prefix, key)
        req = Request(url, method=method, body=body, headers=headers)
        return req

    def stat_key(self, key, info):
        def _onsuccess(response):
            if response.status == 200:
                checksum = response.headers['Etag'].strip('"')
                last_modified = response.headers['Last-Modified']
                modified_tuple = rfc822.parsedate_tz(last_modified)
                modified_stamp = int(rfc822.mktime_tz(modified_tuple))
                return {'checksum': checksum, 'last_modified': modified_stamp}

        req = self.s3_request(key, method='HEAD')
        dfd = self.s3_download(req, info)
        dfd.addCallback(_onsuccess)
        return dfd

    def store_image(self, key, image, buf, info):
        """Upload image to S3 storage"""
        width, height = image.size
        headers = {
                'Content-Type': 'image/jpeg',
                'X-Amz-Acl': 'public-read',
                'X-Amz-Meta-Width': str(width),
                'X-Amz-Meta-Height': str(height),
                'Cache-Control': 'max-age=172800',
                }

        buf.seek(0)
        req = self.s3_request(key, method='PUT', body=buf.read(), headers=headers)
        self.s3_download(req, info)

    def s3_download(self, request, info):
        """This method is used for HEAD and PUT requests sent to amazon S3

        It tries to use a specific spider domain for uploads, or defaults
        to current domain spider.

        """
        if self.AmazonS3Spider:
            return scrapyengine.schedule(request, self.AmazonS3Spider)
        return self.download(request, info)


