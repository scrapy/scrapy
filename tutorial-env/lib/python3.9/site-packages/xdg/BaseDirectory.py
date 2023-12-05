"""
This module is based on a rox module (LGPL):

http://cvs.sourceforge.net/viewcvs.py/rox/ROX-Lib2/python/rox/basedir.py?rev=1.9&view=log

The freedesktop.org Base Directory specification provides a way for
applications to locate shared data and configuration:

    http://standards.freedesktop.org/basedir-spec/

(based on version 0.6)

This module can be used to load and save from and to these directories.

Typical usage:

    from rox import basedir
    
    for dir in basedir.load_config_paths('mydomain.org', 'MyProg', 'Options'):
        print "Load settings from", dir

    dir = basedir.save_config_path('mydomain.org', 'MyProg')
    print >>file(os.path.join(dir, 'Options'), 'w'), "foo=2"

Note: see the rox.Options module for a higher-level API for managing options.
"""

import os, stat

_home = os.path.expanduser('~')
xdg_data_home = os.environ.get('XDG_DATA_HOME') or \
            os.path.join(_home, '.local', 'share')

xdg_data_dirs = [xdg_data_home] + \
    (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':')

xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or \
            os.path.join(_home, '.config')

xdg_config_dirs = [xdg_config_home] + \
    (os.environ.get('XDG_CONFIG_DIRS') or '/etc/xdg').split(':')

xdg_cache_home = os.environ.get('XDG_CACHE_HOME') or \
            os.path.join(_home, '.cache')

xdg_state_home = os.environ.get('XDG_STATE_HOME') or \
            os.path.join(_home, '.local', 'state')

xdg_data_dirs = [x for x in xdg_data_dirs if x]
xdg_config_dirs = [x for x in xdg_config_dirs if x]

def save_config_path(*resource):
    """Ensure ``$XDG_CONFIG_HOME/<resource>/`` exists, and return its path.
    'resource' should normally be the name of your application. Use this
    when saving configuration settings.
    """
    resource = os.path.join(*resource)
    assert not resource.startswith('/')
    path = os.path.join(xdg_config_home, resource)
    if not os.path.isdir(path):
        os.makedirs(path, 0o700)
    return path

def save_data_path(*resource):
    """Ensure ``$XDG_DATA_HOME/<resource>/`` exists, and return its path.
    'resource' should normally be the name of your application or a shared
    resource. Use this when saving or updating application data.
    """
    resource = os.path.join(*resource)
    assert not resource.startswith('/')
    path = os.path.join(xdg_data_home, resource)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path

def save_cache_path(*resource):
    """Ensure ``$XDG_CACHE_HOME/<resource>/`` exists, and return its path.
    'resource' should normally be the name of your application or a shared
    resource."""
    resource = os.path.join(*resource)
    assert not resource.startswith('/')
    path = os.path.join(xdg_cache_home, resource)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path

def save_state_path(*resource):
    """Ensure ``$XDG_STATE_HOME/<resource>/`` exists, and return its path.
    'resource' should normally be the name of your application or a shared
    resource."""
    resource = os.path.join(*resource)
    assert not resource.startswith('/')
    path = os.path.join(xdg_state_home, resource)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path

def load_config_paths(*resource):
    """Returns an iterator which gives each directory named 'resource' in the
    configuration search path. Information provided by earlier directories should
    take precedence over later ones, and the user-specific config dir comes
    first."""
    resource = os.path.join(*resource)
    for config_dir in xdg_config_dirs:
        path = os.path.join(config_dir, resource)
        if os.path.exists(path): yield path

def load_first_config(*resource):
    """Returns the first result from load_config_paths, or None if there is nothing
    to load."""
    for x in load_config_paths(*resource):
        return x
    return None

def load_data_paths(*resource):
    """Returns an iterator which gives each directory named 'resource' in the
    application data search path. Information provided by earlier directories
    should take precedence over later ones."""
    resource = os.path.join(*resource)
    for data_dir in xdg_data_dirs:
        path = os.path.join(data_dir, resource)
        if os.path.exists(path): yield path

def get_runtime_dir(strict=True):
    """Returns the value of $XDG_RUNTIME_DIR, a directory path.
    
    This directory is intended for 'user-specific non-essential runtime files
    and other file objects (such as sockets, named pipes, ...)', and
    'communication and synchronization purposes'.
    
    As of late 2012, only quite new systems set $XDG_RUNTIME_DIR. If it is not
    set, with ``strict=True`` (the default), a KeyError is raised. With 
    ``strict=False``, PyXDG will create a fallback under /tmp for the current
    user. This fallback does *not* provide the same guarantees as the
    specification requires for the runtime directory.
    
    The strict default is deliberately conservative, so that application
    developers can make a conscious decision to allow the fallback.
    """
    try:
        return os.environ['XDG_RUNTIME_DIR']
    except KeyError:
        if strict:
            raise
        
        import getpass
        fallback = '/tmp/pyxdg-runtime-dir-fallback-' + getpass.getuser()
        create = False

        try:
            # This must be a real directory, not a symlink, so attackers can't
            # point it elsewhere. So we use lstat to check it.
            st = os.lstat(fallback)
        except OSError as e:
            import errno
            if e.errno == errno.ENOENT:
                create = True
            else:
                raise
        else:
            # The fallback must be a directory
            if not stat.S_ISDIR(st.st_mode):
                os.unlink(fallback)
                create = True
            # Must be owned by the user and not accessible by anyone else
            elif (st.st_uid != os.getuid()) \
              or (st.st_mode & (stat.S_IRWXG | stat.S_IRWXO)):
                os.rmdir(fallback)
                create = True

        if create:
            os.mkdir(fallback, 0o700)

        return fallback
