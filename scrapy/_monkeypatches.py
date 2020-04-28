import copyreg


# Undo what Twisted's perspective broker adds to pickle register
# to prevent bugs like Twisted#7989 while serializing requests
import twisted.persisted.styles  # NOQA
# Remove only entries with twisted serializers for non-twisted types.
for k, v in frozenset(copyreg.dispatch_table.items()):
    if not str(getattr(k, '__module__', '')).startswith('twisted') \
            and str(getattr(v, '__module__', '')).startswith('twisted'):
        copyreg.dispatch_table.pop(k)
