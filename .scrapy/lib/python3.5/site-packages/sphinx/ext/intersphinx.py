# -*- coding: utf-8 -*-
"""
    sphinx.ext.intersphinx
    ~~~~~~~~~~~~~~~~~~~~~~

    Insert links to objects documented in remote Sphinx documentation.

    This works as follows:

    * Each Sphinx HTML build creates a file named "objects.inv" that contains a
      mapping from object names to URIs relative to the HTML set's root.

    * Projects using the Intersphinx extension can specify links to such mapping
      files in the `intersphinx_mapping` config value.  The mapping will then be
      used to resolve otherwise missing references to objects into links to the
      other documentation.

    * By default, the mapping file is assumed to be at the same location as the
      rest of the documentation; however, the location of the mapping file can
      also be specified individually, e.g. if the docs should be buildable
      without Internet access.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from __future__ import print_function

import time
import zlib
import codecs
import posixpath
from os import path
import re

from six import iteritems, string_types
from six.moves.urllib import request
from six.moves.urllib.parse import urlsplit, urlunsplit
from docutils import nodes
from docutils.utils import relative_path

import sphinx
from sphinx.locale import _
from sphinx.builders.html import INVENTORY_FILENAME


default_handlers = [request.ProxyHandler(), request.HTTPRedirectHandler(),
                    request.HTTPHandler()]
try:
    default_handlers.append(request.HTTPSHandler)
except AttributeError:
    pass

default_opener = request.build_opener(*default_handlers)

UTF8StreamReader = codecs.lookup('utf-8')[2]


def read_inventory_v1(f, uri, join):
    f = UTF8StreamReader(f)
    invdata = {}
    line = next(f)
    projname = line.rstrip()[11:]
    line = next(f)
    version = line.rstrip()[11:]
    for line in f:
        name, type, location = line.rstrip().split(None, 2)
        location = join(uri, location)
        # version 1 did not add anchors to the location
        if type == 'mod':
            type = 'py:module'
            location += '#module-' + name
        else:
            type = 'py:' + type
            location += '#' + name
        invdata.setdefault(type, {})[name] = (projname, version, location, '-')
    return invdata


def read_inventory_v2(f, uri, join, bufsize=16*1024):
    invdata = {}
    line = f.readline()
    projname = line.rstrip()[11:].decode('utf-8')
    line = f.readline()
    version = line.rstrip()[11:].decode('utf-8')
    line = f.readline().decode('utf-8')
    if 'zlib' not in line:
        raise ValueError

    def read_chunks():
        decompressor = zlib.decompressobj()
        for chunk in iter(lambda: f.read(bufsize), b''):
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def split_lines(iter):
        buf = b''
        for chunk in iter:
            buf += chunk
            lineend = buf.find(b'\n')
            while lineend != -1:
                yield buf[:lineend].decode('utf-8')
                buf = buf[lineend+1:]
                lineend = buf.find(b'\n')
        assert not buf

    for line in split_lines(read_chunks()):
        # be careful to handle names with embedded spaces correctly
        m = re.match(r'(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)',
                     line.rstrip())
        if not m:
            continue
        name, type, prio, location, dispname = m.groups()
        if type == 'py:module' and type in invdata and \
                name in invdata[type]:  # due to a bug in 1.1 and below,
                                        # two inventory entries are created
                                        # for Python modules, and the first
                                        # one is correct
            continue
        if location.endswith(u'$'):
            location = location[:-1] + name
        location = join(uri, location)
        invdata.setdefault(type, {})[name] = (projname, version,
                                              location, dispname)
    return invdata


def _strip_basic_auth(url):
    """Returns *url* with basic auth credentials removed. Also returns the
    basic auth username and password if they're present in *url*.

    E.g.: https://user:pass@example.com => https://example.com

    *url* need not include basic auth credentials.

    :param url: url which may or may not contain basic auth credentials
    :type url: ``str``

    :return: 3-``tuple`` of:

      * (``str``) -- *url* with any basic auth creds removed
      * (``str`` or ``NoneType``) -- basic auth username or ``None`` if basic
        auth username not given
      * (``str`` or ``NoneType``) -- basic auth password or ``None`` if basic
        auth password not given

    :rtype: ``tuple``
    """
    url_parts = urlsplit(url)
    username = url_parts.username
    password = url_parts.password
    frags = list(url_parts)
    # swap out "user[:pass]@hostname" for "hostname"
    if url_parts.port:
        frags[1] = "%s:%s" % (url_parts.hostname, url_parts.port)
    else:
        frags[1] = url_parts.hostname
    url = urlunsplit(frags)
    return (url, username, password)


def _read_from_url(url):
    """Reads data from *url* with an HTTP *GET*.

    This function supports fetching from resources which use basic HTTP auth as
    laid out by RFC1738 § 3.1. See § 5 for grammar definitions for URLs.

    .. seealso:

       https://www.ietf.org/rfc/rfc1738.txt

    :param url: URL of an HTTP resource
    :type url: ``str``

    :return: data read from resource described by *url*
    :rtype: ``file``-like object
    """
    url, username, password = _strip_basic_auth(url)
    if username is not None and password is not None:
        # case: url contains basic auth creds
        password_mgr = request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, url, username, password)
        handler = request.HTTPBasicAuthHandler(password_mgr)
        opener = request.build_opener(*(default_handlers + [handler]))
    else:
        opener = default_opener

    return opener.open(url)


def _get_safe_url(url):
    """Gets version of *url* with basic auth passwords obscured. This function
    returns results suitable for printing and logging.

    E.g.: https://user:12345@example.com => https://user:********@example.com

    .. note::

       The number of astrisks is invariant in the length of the basic auth
       password, so minimal information is leaked.

    :param url: a url
    :type url: ``str``

    :return: *url* with password obscured
    :rtype: ``str``
    """
    safe_url = url
    url, username, _ = _strip_basic_auth(url)
    if username is not None:
        # case: url contained basic auth creds; obscure password
        url_parts = urlsplit(url)
        safe_netloc = '{0}@{1}'.format(username, url_parts.hostname)
        # replace original netloc w/ obscured version
        frags = list(url_parts)
        frags[1] = safe_netloc
        safe_url = urlunsplit(frags)

    return safe_url


def fetch_inventory(app, uri, inv):
    """Fetch, parse and return an intersphinx inventory file."""
    # both *uri* (base URI of the links to generate) and *inv* (actual
    # location of the inventory file) can be local or remote URIs
    localuri = '://' not in uri
    if not localuri:
        # case: inv URI points to remote resource; strip any existing auth
        uri, _, _ = _strip_basic_auth(uri)
    join = localuri and path.join or posixpath.join
    try:
        if '://' in inv:
            f = _read_from_url(inv)
        else:
            f = open(path.join(app.srcdir, inv), 'rb')
    except Exception as err:
        app.warn('intersphinx inventory %r not fetchable due to '
                 '%s: %s' % (inv, err.__class__, err))
        return
    try:
        if hasattr(f, 'geturl'):
            newinv = f.geturl()
            if inv != newinv:
                app.info('intersphinx inventory has moved: %s -> %s' % (inv, newinv))

                if uri in (inv, path.dirname(inv), path.dirname(inv) + '/'):
                    uri = path.dirname(newinv)
        line = f.readline().rstrip().decode('utf-8')
        try:
            if line == '# Sphinx inventory version 1':
                invdata = read_inventory_v1(f, uri, join)
            elif line == '# Sphinx inventory version 2':
                invdata = read_inventory_v2(f, uri, join)
            else:
                raise ValueError
            f.close()
        except ValueError:
            f.close()
            raise ValueError('unknown or unsupported inventory version')
    except Exception as err:
        app.warn('intersphinx inventory %r not readable due to '
                 '%s: %s' % (inv, err.__class__.__name__, err))
    else:
        return invdata


def load_mappings(app):
    """Load all intersphinx mappings into the environment."""
    now = int(time.time())
    cache_time = now - app.config.intersphinx_cache_limit * 86400
    env = app.builder.env
    if not hasattr(env, 'intersphinx_cache'):
        env.intersphinx_cache = {}
        env.intersphinx_inventory = {}
        env.intersphinx_named_inventory = {}
    cache = env.intersphinx_cache
    update = False
    for key, value in iteritems(app.config.intersphinx_mapping):
        if isinstance(value, tuple):
            # new format
            name, (uri, inv) = key, value
            if not isinstance(name, string_types):
                app.warn('intersphinx identifier %r is not string. Ignored' % name)
                continue
        else:
            # old format, no name
            name, uri, inv = None, key, value
        # we can safely assume that the uri<->inv mapping is not changed
        # during partial rebuilds since a changed intersphinx_mapping
        # setting will cause a full environment reread
        if not isinstance(inv, tuple):
            invs = (inv, )
        else:
            invs = inv

        for inv in invs:
            if not inv:
                inv = posixpath.join(uri, INVENTORY_FILENAME)
            # decide whether the inventory must be read: always read local
            # files; remote ones only if the cache time is expired
            if '://' not in inv or uri not in cache \
                    or cache[uri][1] < cache_time:
                safe_inv_url = _get_safe_url(inv)
                app.info(
                    'loading intersphinx inventory from %s...' % safe_inv_url)
                invdata = fetch_inventory(app, uri, inv)
                if invdata:
                    cache[uri] = (name, now, invdata)
                    update = True
                    break

    if update:
        env.intersphinx_inventory = {}
        env.intersphinx_named_inventory = {}
        # Duplicate values in different inventories will shadow each
        # other; which one will override which can vary between builds
        # since they are specified using an unordered dict.  To make
        # it more consistent, we sort the named inventories and then
        # add the unnamed inventories last.  This means that the
        # unnamed inventories will shadow the named ones but the named
        # ones can still be accessed when the name is specified.
        cached_vals = list(cache.values())
        named_vals = sorted(v for v in cached_vals if v[0])
        unnamed_vals = [v for v in cached_vals if not v[0]]
        for name, _x, invdata in named_vals + unnamed_vals:
            if name:
                env.intersphinx_named_inventory[name] = invdata
            for type, objects in iteritems(invdata):
                env.intersphinx_inventory.setdefault(
                    type, {}).update(objects)


def missing_reference(app, env, node, contnode):
    """Attempt to resolve a missing reference via intersphinx references."""
    target = node['reftarget']
    if node['reftype'] == 'any':
        # we search anything!
        objtypes = ['%s:%s' % (domain.name, objtype)
                    for domain in env.domains.values()
                    for objtype in domain.object_types]
        domain = None
    elif node['reftype'] == 'doc':
        domain = 'std'  # special case
        objtypes = ['std:doc']
    else:
        domain = node.get('refdomain')
        if not domain:
            # only objects in domains are in the inventory
            return
        objtypes = env.domains[domain].objtypes_for_role(node['reftype'])
        if not objtypes:
            return
        objtypes = ['%s:%s' % (domain, objtype) for objtype in objtypes]
    to_try = [(env.intersphinx_inventory, target)]
    in_set = None
    if ':' in target:
        # first part may be the foreign doc set name
        setname, newtarget = target.split(':', 1)
        if setname in env.intersphinx_named_inventory:
            in_set = setname
            to_try.append((env.intersphinx_named_inventory[setname], newtarget))
    for inventory, target in to_try:
        for objtype in objtypes:
            if objtype not in inventory or target not in inventory[objtype]:
                continue
            proj, version, uri, dispname = inventory[objtype][target]
            if '://' not in uri and node.get('refdoc'):
                # get correct path in case of subdirectories
                uri = path.join(relative_path(node['refdoc'], '.'), uri)
            newnode = nodes.reference('', '', internal=False, refuri=uri,
                                      reftitle=_('(in %s v%s)') % (proj, version))
            if node.get('refexplicit'):
                # use whatever title was given
                newnode.append(contnode)
            elif dispname == '-' or \
                    (domain == 'std' and node['reftype'] == 'keyword'):
                # use whatever title was given, but strip prefix
                title = contnode.astext()
                if in_set and title.startswith(in_set+':'):
                    newnode.append(contnode.__class__(title[len(in_set)+1:],
                                                      title[len(in_set)+1:]))
                else:
                    newnode.append(contnode)
            else:
                # else use the given display name (used for :ref:)
                newnode.append(contnode.__class__(dispname, dispname))
            return newnode
    # at least get rid of the ':' in the target if no explicit title given
    if in_set is not None and not node.get('refexplicit', True):
        if len(contnode) and isinstance(contnode[0], nodes.Text):
            contnode[0] = nodes.Text(newtarget, contnode[0].rawsource)


def setup(app):
    app.add_config_value('intersphinx_mapping', {}, True)
    app.add_config_value('intersphinx_cache_limit', 5, False)
    app.connect('missing-reference', missing_reference)
    app.connect('builder-inited', load_mappings)
    return {'version': sphinx.__display_version__, 'parallel_read_safe': True}


if __name__ == '__main__':
    # debug functionality to print out an inventory
    import sys

    class MockApp(object):
        srcdir = ''

        def warn(self, msg):
            print(msg, file=sys.stderr)

    filename = sys.argv[1]
    invdata = fetch_inventory(MockApp(), '', filename)
    for key in sorted(invdata or {}):
        print(key)
        for entry, einfo in sorted(invdata[key].items()):
            print('\t%-40s %s%s' % (entry,
                                    einfo[3] != '-' and '%-40s: ' % einfo[3] or '',
                                    einfo[2]))
