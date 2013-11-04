import sys

if sys.version_info[0] == 2:
    from urlparse import urlparse

    # workaround for http://bugs.python.org/issue7904 - Python < 2.7
    if urlparse('s3://bucket/key').netloc != 'bucket':
        from urlparse import uses_netloc
        uses_netloc.append('s3')

    # workaround for http://bugs.python.org/issue9374 - Python < 2.7.4
    if urlparse('s3://bucket/key?key=value').query != 'key=value':
        from urlparse import uses_query
        uses_query.append('s3')
