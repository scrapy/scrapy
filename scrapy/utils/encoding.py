import codecs

def add_encoding_alias(encoding, alias, overwrite=False):
    try:
        codecs.lookup(alias)
        alias_exists = True
    except LookupError:
        alias_exists = False
    if overwrite or not alias_exists:
        codec = codecs.lookup(encoding)
        codecs.register(lambda x: codec if x == alias else None)
