from urlparse import urlparse, uses_netloc, uses_query

# workaround for http://bugs.python.org/issue7904
if urlparse('s3://bucket/key').netloc != 'bucket':
    uses_netloc.append('s3')
if urlparse('s3://bucket/key?key=value').query != 'key=value':
    uses_query.append('s3')
