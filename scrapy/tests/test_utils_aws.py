from unittest import TestCase, main

from scrapy.utils import aws
from scrapy.http import Request

# just some random keys. keys are provided by amazon developer guide at
# http://s3.amazonaws.com/awsdocs/S3/20060301/s3-dg-20060301.pdf
# and the tests described here are the examples from that manual

AWS_ACCESS_KEY_ID = '0PN5J17HBGZHT7JJ3X82'
AWS_SECRET_ACCESS_KEY = 'uV3F3YluFJax1cknvbcGwgjvx4QpvB+leU8dUj2o'


class ScrapyAWSTest(TestCase):
    def test_cannonical_string1(self):
        cs = aws.canonical_string('GET', '/johnsmith/photos/puppy.jpg', {
            'Host': 'johnsmith.s3.amazonaws.com',
            'Date': 'Tue, 27 Mar 2007 19:36:42 +0000',
            })
        self.assertEqual(cs, \
                '''GET\n\n\nTue, 27 Mar 2007 19:36:42 +0000\n/johnsmith/photos/puppy.jpg''')

    def test_cannonical_string2(self):
        cs = aws.canonical_string('PUT', '/johnsmith/photos/puppy.jpg', {
            'Content-Type': 'image/jpeg',
            'Host': 'johnsmith.s3.amazonaws.com',
            'Date': 'Tue, 27 Mar 2007 21:15:45 +0000',
            'Content-Length': '94328',
            })
        self.assertEqual(cs, \
                '''PUT\n\nimage/jpeg\nTue, 27 Mar 2007 21:15:45 +0000\n/johnsmith/photos/puppy.jpg''')

    def test_request_signing1(self):
        # gets an object from the johnsmith bucket.
        req = Request('http://johnsmith.s3.amazonaws.com/photos/puppy.jpg', headers={
            'Date': 'Tue, 27 Mar 2007 19:36:42 +0000',
            })
        aws.sign_request(req, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        self.assertEqual(req.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:xXjDGYUmKxnwqr5KXNPGldn5LbA=')

    def test_request_signing2(self):
        # puts an object into the johnsmith bucket.
        req = Request('http://johnsmith.s3.amazonaws.com/photos/puppy.jpg', method='PUT', headers={
            'Content-Type': 'image/jpeg',
            'Date': 'Tue, 27 Mar 2007 21:15:45 +0000',
            'Content-Length': '94328',
            })
        aws.sign_request(req, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        self.assertEqual(req.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:hcicpDDvL9SsO6AkvxqmIWkmOuQ=')

    def test_request_signing3(self):
        # lists the content of the johnsmith bucket.
        req = Request('http://johnsmith.s3.amazonaws.com/?prefix=photos&max-keys=50&marker=puppy', \
                method='GET', headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Date': 'Tue, 27 Mar 2007 19:42:41 +0000',
                    })
        aws.sign_request(req, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        self.assertEqual(req.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:jsRt/rhG+Vtp88HrYL706QhE4w4=')

    def test_request_signing4(self):
        # fetches the access control policy sub-resource for the 'johnsmith' bucket.
        req = Request('http://johnsmith.s3.amazonaws.com/?acl', \
                method='GET', headers={
                    'Date': 'Tue, 27 Mar 2007 19:44:46 +0000',
                    })
        aws.sign_request(req, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        self.assertEqual(req.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:thdUi9VAkzhkniLj96JIrOPGi0g=')

    def test_request_signing5(self):
        # deletes an object from the 'johnsmith' bucket using the path-style and Date alternative.
        req = Request('http://johnsmith.s3.amazonaws.com/photos/puppy.jpg', \
                method='DELETE', headers={
                    'Date': 'Tue, 27 Mar 2007 21:20:27 +0000',
                    'x-amz-date': 'Tue, 27 Mar 2007 21:20:26 +0000',
                    })
        aws.sign_request(req, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        self.assertEqual(req.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:k3nL7gH3+PadhTEVn5Ip83xlYzk=')

    def test_request_signing6(self):
        # uploads an object to a CNAME style virtual hosted bucket with metadata.
        req = Request('http://static.johnsmith.net:8080/db-backup.dat.gz', \
                method='PUT', headers={
                    'User-Agent': 'curl/7.15.5',
                    'Host': 'static.johnsmith.net:8080',
                    'Date': 'Tue, 27 Mar 2007 21:06:08 +0000',
                    'x-amz-acl': 'public-read',
                    'content-type': 'application/x-download',
                    'Content-MD5': '4gJE4saaMU4BqNR0kLY+lw==',
                    'X-Amz-Meta-ReviewedBy': 'joe@johnsmith.net,jane@johnsmith.net',
                    'X-Amz-Meta-FileChecksum': '0x02661779',
                    'X-Amz-Meta-ChecksumAlgorithm': 'crc32',
                    'Content-Disposition': 'attachment; filename=database.dat',
                    'Content-Encoding': 'gzip',
                    'Content-Length': '5913339',
                    })
        aws.sign_request(req, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        self.assertEqual(req.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:C0FlOtU8Ylb9KDTpZqYkZPX91iI=')


if __name__ == '__main__':
    main()
