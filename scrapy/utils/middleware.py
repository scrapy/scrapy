from operator import itemgetter

def build_middleware_list(base, custom):
    """Compose a middleware list based on a custom and base dict of
    middlewares, unless custom is already a list, in which case it's returned.
    """
    if isinstance(custom, (list, tuple)):
        return custom
    mwdict = base.copy()
    mwdict.update(custom)
    return [k for k, v in sorted(mwdict.items(), key=itemgetter(1)) if v is not None]
