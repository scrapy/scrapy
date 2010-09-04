from urlparse import urlparse, uses_netloc

# workaround for http://bugs.python.org/issue7904
if urlparse('s3://bucket/key').netloc != 'bucket':
    uses_netloc.append('s3')
