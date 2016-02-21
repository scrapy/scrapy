"""
This module contains some assorted functions used in tests
"""

from __future__ import absolute_import
import os

from importlib import import_module
from twisted.trial.unittest import SkipTest

from scrapy.exceptions import NotConfigured
from scrapy.utils.boto import is_botocore


def assert_aws_environ():
    """Asserts the current environment is suitable for running AWS testsi.
    Raises SkipTest with the reason if it's not.
    """
    skip_if_no_boto()
    if 'AWS_ACCESS_KEY_ID' not in os.environ:
        raise SkipTest("AWS keys not found")

def skip_if_no_boto():
    try:
        is_botocore()
    except NotConfigured as e:
        raise SkipTest(e)

def get_s3_content_and_delete(bucket, path, with_key=False):
    """ Get content from s3 key, and delete key afterwards.
    """
    if is_botocore():
        import botocore.session
        session = botocore.session.get_session()
        client = session.create_client('s3')
        key = client.get_object(Bucket=bucket, Key=path)
        content = key['Body'].read()
        client.delete_object(Bucket=bucket, Key=path)
    else:
        import boto
        # assuming boto=2.2.2
        bucket = boto.connect_s3().get_bucket(bucket, validate=False)
        key = bucket.get_key(path)
        content = key.get_contents_as_string()
        bucket.delete_key(path)
    return (content, key) if with_key else content

def get_crawler(spidercls=None, settings_dict=None):
    """Return an unconfigured Crawler object. If settings_dict is given, it
    will be used to populate the crawler settings with a project level
    priority.
    """
    from scrapy.crawler import CrawlerRunner
    from scrapy.spiders import Spider

    runner = CrawlerRunner(settings_dict)
    return runner.create_crawler(spidercls or Spider)

def get_pythonpath():
    """Return a PYTHONPATH suitable to use in processes so that they find this
    installation of Scrapy"""
    scrapy_path = import_module('scrapy').__path__[0]
    return os.path.dirname(scrapy_path) + os.pathsep + os.environ.get('PYTHONPATH', '')

def get_testenv():
    """Return a OS environment dict suitable to fork processes that need to import
    this installation of Scrapy, instead of a system installed one.
    """
    env = os.environ.copy()
    env['PYTHONPATH'] = get_pythonpath()
    return env

def assert_samelines(testcase, text1, text2, msg=None):
    """Asserts text1 and text2 have the same lines, ignoring differences in
    line endings between platforms
    """
    testcase.assertEqual(text1.splitlines(), text2.splitlines(), msg)
