"""Boto/botocore helpers"""

import io

from scrapy.exceptions import NotConfigured


def is_botocore():
    try:
        import botocore  # noqa: F401
        return True
    except ImportError:
        raise NotConfigured('missing botocore library')


class S3Writer(io.IOBase):
    """A synchronous writer for Amazon S3 Objects using Multipart Uploads.
    This class is not Thread Safe!
    """
    def __init__(self, access_key, secret_key, bucket_name, key):
        """Connect to the Amazon S3 resource and start the multipart upload.

        :param access_key: AWS Access Key ID
        :param secret_key: AWS Secret Access Key
        :param bucket_name: S3 Bucket Name
        :param key: S3 Object Key
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.key = key

        self.open = False
        self.client = self.create_client()
        self.multipart_upload = self.create_multipart_upload()
        self.total_parts = 0
        self.parts = []

    def create_client(self):
        """Create a boto3 service client by name using the default session.

        Credentials, bucket name and file key are acquired from the project
        settings.

        :return: Service client instance
        """
        try:
            import boto3
        except ImportError:
            raise NotConfigured('missing boto3 library')

        self.open = True
        return boto3.client(
            's3',
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key
        )

    def create_multipart_upload(self):
        """Create/begin a multipart upload.

        :return: Multipart Upload dict
        """
        return self.client.create_multipart_upload(
            Bucket=self.bucket_name, Key=self.key
        )

    def writable(self):
        return True

    def write(self, raw):
        """Write bytes by uploading a new part.

        :param raw: raw data to be written (Memory View)
        :return: number of bytes written
        """
        self.total_parts += 1
        body = raw.tobytes()
        part = self.client.upload_part(
            Bucket=self.bucket_name,
            Key=self.key,
            UploadId=self.multipart_upload['UploadId'],
            PartNumber=self.total_parts,
            Body=body
        )
        self.parts.append({
            'PartNumber': self.total_parts,
            'ETag': part['ETag'],
        })

        return len(body)

    def close(self):
        """Complete the Multipart Upload process.

        If there's not even a single uploaded part, abort the process.
        """
        if not self.open:
            return

        self.open = False

        if self.parts:
            self.client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=self.key,
                UploadId=self.multipart_upload['UploadId'],
                MultipartUpload={'Parts': self.parts}
            )
        else:
            self.client.abort_multipart_upload(
                Bucket=self.bucket_name,
                Key=self.key,
                UploadId=self.multipart_upload['UploadId']
            )
