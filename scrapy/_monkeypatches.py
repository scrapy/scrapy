import six
from six.moves import copyreg


if six.PY2:
    from urlparse import urlparse

    # workaround for https://bugs.python.org/issue7904 - Python < 2.7
    if urlparse('s3://bucket/key').netloc != 'bucket':
        from urlparse import uses_netloc
        uses_netloc.append('s3')

    # workaround for https://bugs.python.org/issue9374 - Python < 2.7.4
    if urlparse('s3://bucket/key?key=value').query != 'key=value':
        from urlparse import uses_query
        uses_query.append('s3')


# Undo what Twisted's perspective broker adds to pickle register
# to prevent bugs like Twisted#7989 while serializing requests
import twisted.persisted.styles  # NOQA
# Remove only entries with twisted serializers for non-twisted types.
for k, v in frozenset(copyreg.dispatch_table.items()):
    if not str(getattr(k, '__module__', '')).startswith('twisted') \
            and str(getattr(v, '__module__', '')).startswith('twisted'):
        copyreg.dispatch_table.pop(k)
