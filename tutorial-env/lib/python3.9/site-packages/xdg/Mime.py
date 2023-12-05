"""
This module is based on a rox module (LGPL):

http://cvs.sourceforge.net/viewcvs.py/rox/ROX-Lib2/python/rox/mime.py?rev=1.21&view=log

This module provides access to the shared MIME database.

types is a dictionary of all known MIME types, indexed by the type name, e.g.
types['application/x-python']

Applications can install information about MIME types by storing an
XML file as <MIME>/packages/<application>.xml and running the
update-mime-database command, which is provided by the freedesktop.org
shared mime database package.

See http://www.freedesktop.org/standards/shared-mime-info-spec/ for
information about the format of these files.

(based on version 0.13)
"""

import os
import re
import stat
import sys
import fnmatch

from xdg import BaseDirectory
import xdg.Locale

from xml.dom import minidom, XML_NAMESPACE
from collections import defaultdict

FREE_NS = 'http://www.freedesktop.org/standards/shared-mime-info'

types = {}      # Maps MIME names to type objects

exts = None     # Maps extensions to types
globs = None    # List of (glob, type) pairs
literals = None # Maps liternal names to types
magic = None

PY3 = (sys.version_info[0] >= 3)

def _get_node_data(node):
    """Get text of XML node"""
    return ''.join([n.nodeValue for n in node.childNodes]).strip()

def lookup(media, subtype = None):
    """Get the MIMEtype object for the given type.
    
    This remains for backwards compatibility; calling MIMEtype now does
    the same thing.
    
    The name can either be passed as one part ('text/plain'), or as two
    ('text', 'plain').
    """
    return MIMEtype(media, subtype)

class MIMEtype(object):
    """Class holding data about a MIME type.
    
    Calling the class will return a cached instance, so there is only one 
    instance for each MIME type. The name can either be passed as one part
    ('text/plain'), or as two ('text', 'plain').
    """
    def __new__(cls, media, subtype=None):
        if subtype is None and '/' in media:
            media, subtype = media.split('/', 1)
        assert '/' not in subtype
        media = media.lower()
        subtype = subtype.lower()
        
        try:
            return types[(media, subtype)]
        except KeyError:
            mtype = super(MIMEtype, cls).__new__(cls)
            mtype._init(media, subtype)
            types[(media, subtype)] = mtype
            return mtype

    # If this is done in __init__, it is automatically called again each time
    # the MIMEtype is returned by __new__, which we don't want. So we call it
    # explicitly only when we construct a new instance.
    def _init(self, media, subtype):
        self.media = media
        self.subtype = subtype
        self._comment = None

    def _load(self):
        "Loads comment for current language. Use get_comment() instead."
        resource = os.path.join('mime', self.media, self.subtype + '.xml')
        for path in BaseDirectory.load_data_paths(resource):
            doc = minidom.parse(path)
            if doc is None:
                continue
            for comment in doc.documentElement.getElementsByTagNameNS(FREE_NS, 'comment'):
                lang = comment.getAttributeNS(XML_NAMESPACE, 'lang') or 'en'
                goodness = 1 + (lang in xdg.Locale.langs)
                if goodness > self._comment[0]:
                    self._comment = (goodness, _get_node_data(comment))
                if goodness == 2: return

    # FIXME: add get_icon method
    def get_comment(self):
        """Returns comment for current language, loading it if needed."""
        # Should we ever reload?
        if self._comment is None:
            self._comment = (0, str(self))
            self._load()
        return self._comment[1]
    
    def canonical(self):
        """Returns the canonical MimeType object if this is an alias."""
        update_cache()
        s = str(self)
        if s in aliases:
            return lookup(aliases[s])
        return self
    
    def inherits_from(self):
        """Returns a set of Mime types which this inherits from."""
        update_cache()
        return set(lookup(t) for t in inheritance[str(self)])

    def __str__(self):
        return self.media + '/' + self.subtype

    def __repr__(self):
        return 'MIMEtype(%r, %r)' % (self.media, self.subtype)
    
    def __hash__(self):
        return hash(self.media) ^ hash(self.subtype)

class UnknownMagicRuleFormat(ValueError):
    pass

class DiscardMagicRules(Exception):
    "Raised when __NOMAGIC__ is found, and caught to discard previous rules."
    pass

class MagicRule:
    also = None
    
    def __init__(self, start, value, mask, word, range):
        self.start = start
        self.value = value
        self.mask = mask
        self.word = word
        self.range = range
    
    rule_ending_re = re.compile(br'(?:~(\d+))?(?:\+(\d+))?\n$')
    
    @classmethod
    def from_file(cls, f):
        """Read a rule from the binary magics file. Returns a 2-tuple of
        the nesting depth and the MagicRule."""
        line = f.readline()
        #print line
        
        # [indent] '>'
        nest_depth, line = line.split(b'>', 1)
        nest_depth = int(nest_depth) if nest_depth else 0

        # start-offset '='
        start, line = line.split(b'=', 1)
        start = int(start)
        
        if line == b'__NOMAGIC__\n':
            raise DiscardMagicRules
        
        # value length (2 bytes, big endian)
        if sys.version_info[0] >= 3:
            lenvalue = int.from_bytes(line[:2], byteorder='big')
        else:
            lenvalue = (ord(line[0])<<8)+ord(line[1])
        line = line[2:]
        
        # value
        #   This can contain newlines, so we may need to read more lines
        while len(line) <= lenvalue:
            line += f.readline()
        value, line = line[:lenvalue], line[lenvalue:]

        # ['&' mask]
        if line.startswith(b'&'):
            # This can contain newlines, so we may need to read more lines
            while len(line) <= lenvalue:
                line += f.readline()
            mask, line = line[1:lenvalue+1], line[lenvalue+1:]
        else:
            mask = None

        # ['~' word-size] ['+' range-length]
        ending = cls.rule_ending_re.match(line)
        if not ending:
            # Per the spec, this will be caught and ignored, to allow
            # for future extensions.
            raise UnknownMagicRuleFormat(repr(line))
        
        word, range = ending.groups()
        word = int(word) if (word is not None) else 1
        range = int(range) if (range is not None) else 1
        
        return nest_depth, cls(start, value, mask, word, range)

    def maxlen(self):
        l = self.start + len(self.value) + self.range
        if self.also:
            return max(l, self.also.maxlen())
        return l

    def match(self, buffer):
        if self.match0(buffer):
            if self.also:
                return self.also.match(buffer)
            return True

    def match0(self, buffer):
        l=len(buffer)
        lenvalue = len(self.value)
        for o in range(self.range):
            s=self.start+o
            e=s+lenvalue
            if l<e:
                return False
            if self.mask:
                test=''
                for i in range(lenvalue):
                    if PY3:
                        c = buffer[s+i] & self.mask[i]
                    else:
                        c = ord(buffer[s+i]) & ord(self.mask[i])
                    test += chr(c)
            else:
                test = buffer[s:e]

            if test==self.value:
                return True

    def __repr__(self):
        return 'MagicRule(start=%r, value=%r, mask=%r, word=%r, range=%r)' %(
                                  self.start,
                                  self.value,
                                  self.mask,
                                  self.word,
                                  self.range)


class MagicMatchAny(object):
    """Match any of a set of magic rules.
    
    This has a similar interface to MagicRule objects (i.e. its match() and
    maxlen() methods), to allow for duck typing.
    """
    def __init__(self, rules):
        self.rules = rules
    
    def match(self, buffer):
        return any(r.match(buffer) for r in self.rules)
    
    def maxlen(self):
        return max(r.maxlen() for r in self.rules)
    
    @classmethod
    def from_file(cls, f):
        """Read a set of rules from the binary magic file."""
        c=f.read(1)
        f.seek(-1, 1)
        depths_rules = []
        while c and c != b'[':
            try:
                depths_rules.append(MagicRule.from_file(f))
            except UnknownMagicRuleFormat:
                # Ignored to allow for extensions to the rule format.
                pass
            c=f.read(1)
            if c:
                f.seek(-1, 1)
        
        # Build the rule tree
        tree = []  # (rule, [(subrule,[subsubrule,...]), ...])
        insert_points = {0:tree}
        for depth, rule in depths_rules:
            subrules = []
            insert_points[depth].append((rule, subrules))
            insert_points[depth+1] = subrules
        
        return cls.from_rule_tree(tree)
    
    @classmethod
    def from_rule_tree(cls, tree):
        """From a nested list of (rule, subrules) pairs, build a MagicMatchAny
        instance, recursing down the tree.
        
        Where there's only one top-level rule, this is returned directly,
        to simplify the nested structure. Returns None if no rules were read.
        """
        rules = []
        for rule, subrules in tree:
            if subrules:
                rule.also = cls.from_rule_tree(subrules)
            rules.append(rule)
        
        if len(rules)==0:
            return None
        if len(rules)==1:
            return rules[0]
        return cls(rules)        
    
class MagicDB:
    def __init__(self):
        self.bytype   = defaultdict(list)  # mimetype -> [(priority, rule), ...] 

    def merge_file(self, fname):
        """Read a magic binary file, and add its rules to this MagicDB."""
        with open(fname, 'rb') as f:
            line = f.readline()
            if line != b'MIME-Magic\0\n':
                raise IOError('Not a MIME magic file')

            while True:
                shead = f.readline().decode('ascii')
                #print(shead)
                if not shead:
                    break
                if shead[0] != '[' or shead[-2:] != ']\n':
                    raise ValueError('Malformed section heading', shead)
                pri, tname = shead[1:-2].split(':')
                #print shead[1:-2]
                pri = int(pri)
                mtype = lookup(tname)
                try:
                    rule = MagicMatchAny.from_file(f)
                except DiscardMagicRules:
                    self.bytype.pop(mtype, None)
                    rule = MagicMatchAny.from_file(f)
                if rule is None:
                    continue
                #print rule

                self.bytype[mtype].append((pri, rule))

    def finalise(self):
        """Prepare the MagicDB for matching.
        
        This should be called after all rules have been merged into it.
        """
        maxlen = 0
        self.alltypes = []  # (priority, mimetype, rule)

        for mtype, rules in self.bytype.items():
            for pri, rule in rules:
                self.alltypes.append((pri, mtype, rule))
                maxlen = max(maxlen, rule.maxlen())

        self.maxlen = maxlen  # Number of bytes to read from files
        self.alltypes.sort(key=lambda x: x[0], reverse=True)

    def match_data(self, data, max_pri=100, min_pri=0, possible=None):
        """Do magic sniffing on some bytes.
        
        max_pri & min_pri can be used to specify the maximum & minimum priority
        rules to look for. possible can be a list of mimetypes to check, or None
        (the default) to check all mimetypes until one matches.
        
        Returns the MIMEtype found, or None if no entries match.
        """
        if possible is not None:
            types = []
            for mt in possible:
                for pri, rule in self.bytype[mt]:
                    types.append((pri, mt, rule))
            types.sort(key=lambda x: x[0])
        else:
            types = self.alltypes
        
        for priority, mimetype, rule in types:
            #print priority, max_pri, min_pri
            if priority > max_pri:
                continue
            if priority < min_pri:
                break
            
            if rule.match(data):
                return mimetype

    def match(self, path, max_pri=100, min_pri=0, possible=None):
        """Read data from the file and do magic sniffing on it.
        
        max_pri & min_pri can be used to specify the maximum & minimum priority
        rules to look for. possible can be a list of mimetypes to check, or None
        (the default) to check all mimetypes until one matches.
        
        Returns the MIMEtype found, or None if no entries match. Raises IOError
        if the file can't be opened.
        """
        with open(path, 'rb') as f:
            buf = f.read(self.maxlen)
        return self.match_data(buf, max_pri, min_pri, possible)
    
    def __repr__(self):
        return '<MagicDB (%d types)>' % len(self.alltypes)

class GlobDB(object):
    def __init__(self):
        """Prepare the GlobDB. It can't actually be used until .finalise() is
        called, but merge_file() can be used to add data before that.
        """
        # Maps mimetype to {(weight, glob, flags), ...}
        self.allglobs = defaultdict(set)

    def merge_file(self, path):
        """Loads name matching information from a globs2 file."""#
        allglobs = self.allglobs
        with open(path) as f:
            for line in f:
                if line.startswith('#'): continue   # Comment
                
                fields = line[:-1].split(':')
                weight, type_name, pattern = fields[:3]
                weight = int(weight)
                mtype = lookup(type_name)
                if len(fields) > 3:
                    flags = fields[3].split(',')
                else:
                    flags = ()
                    
                if pattern == '__NOGLOBS__':
                    # This signals to discard any previous globs
                    allglobs.pop(mtype, None)
                    continue
                
                allglobs[mtype].add((weight, pattern, tuple(flags)))
    
    def finalise(self):
        """Prepare the GlobDB for matching.
        
        This should be called after all files have been merged into it.
        """
        self.exts = defaultdict(list)  # Maps extensions to [(type, weight),...]
        self.cased_exts = defaultdict(list)
        self.globs = []                # List of (regex, type, weight) triplets
        self.literals = {}             # Maps literal names to (type, weight)
        self.cased_literals = {}
        
        for mtype, globs in self.allglobs.items():
          mtype = mtype.canonical()
          for weight, pattern, flags in globs:
        
            cased = 'cs' in flags

            if pattern.startswith('*.'):
                # *.foo -- extension pattern
                rest = pattern[2:]
                if not ('*' in rest or '[' in rest or '?' in rest):
                    if cased:
                        self.cased_exts[rest].append((mtype, weight))
                    else:
                        self.exts[rest.lower()].append((mtype, weight))
                    continue
            
            if ('*' in pattern or '[' in pattern or '?' in pattern):
                # Translate the glob pattern to a regex & compile it
                re_flags = 0 if cased else re.I
                pattern = re.compile(fnmatch.translate(pattern), flags=re_flags)
                self.globs.append((pattern, mtype, weight))
            else:
                # No wildcards - literal pattern
                if cased:
                    self.cased_literals[pattern] = (mtype, weight)
                else:
                    self.literals[pattern.lower()] = (mtype, weight)
        
        # Sort globs by weight & length
        self.globs.sort(reverse=True, key=lambda x: (x[2], len(x[0].pattern)) )
    
    def first_match(self, path):
        """Return the first match found for a given path, or None if no match
        is found."""
        try:
            return next(self._match_path(path))[0]
        except StopIteration:
            return None
    
    def all_matches(self, path):
        """Return a list of (MIMEtype, glob weight) pairs for the path."""
        return list(self._match_path(path))
    
    def _match_path(self, path):
        """Yields pairs of (mimetype, glob weight)."""
        leaf = os.path.basename(path)

        # Literals (no wildcards)
        if leaf in self.cased_literals:
            yield self.cased_literals[leaf]

        lleaf = leaf.lower()
        if lleaf in self.literals:
            yield self.literals[lleaf]

        # Extensions
        ext = leaf
        while 1:
            p = ext.find('.')
            if p < 0: break
            ext = ext[p + 1:]
            if ext in self.cased_exts:
                for res in self.cased_exts[ext]:
                    yield res
        ext = lleaf
        while 1:
            p = ext.find('.')
            if p < 0: break
            ext = ext[p+1:]
            if ext in self.exts:
                for res in self.exts[ext]:
                    yield res
        
        # Other globs
        for (regex, mime_type, weight) in self.globs:
            if regex.match(leaf):
                yield (mime_type, weight)

# Some well-known types
text = lookup('text', 'plain')
octet_stream = lookup('application', 'octet-stream')
inode_block = lookup('inode', 'blockdevice')
inode_char = lookup('inode', 'chardevice')
inode_dir = lookup('inode', 'directory')
inode_fifo = lookup('inode', 'fifo')
inode_socket = lookup('inode', 'socket')
inode_symlink = lookup('inode', 'symlink')
inode_door = lookup('inode', 'door')
app_exe = lookup('application', 'executable')

_cache_uptodate = False

def _cache_database():
    global globs, magic, aliases, inheritance, _cache_uptodate

    _cache_uptodate = True

    aliases = {}    # Maps alias Mime types to canonical names
    inheritance = defaultdict(set) # Maps to sets of parent mime types.
    
    # Load aliases
    for path in BaseDirectory.load_data_paths(os.path.join('mime', 'aliases')):
        with open(path, 'r') as f:
            for line in f:
                alias, canonical = line.strip().split(None, 1)
                aliases[alias] = canonical
    
    # Load filename patterns (globs)
    globs = GlobDB()
    for path in BaseDirectory.load_data_paths(os.path.join('mime', 'globs2')):
        globs.merge_file(path)
    globs.finalise()
    
    # Load magic sniffing data
    magic = MagicDB()    
    for path in BaseDirectory.load_data_paths(os.path.join('mime', 'magic')):
        magic.merge_file(path)
    magic.finalise()
    
    # Load subclasses
    for path in BaseDirectory.load_data_paths(os.path.join('mime', 'subclasses')):
        with open(path, 'r') as f:
            for line in f:
                sub, parent = line.strip().split(None, 1)
                inheritance[sub].add(parent)

def update_cache():
    if not _cache_uptodate:
        _cache_database()

def get_type_by_name(path):
    """Returns type of file by its name, or None if not known"""
    update_cache()
    return globs.first_match(path)

def get_type_by_contents(path, max_pri=100, min_pri=0):
    """Returns type of file by its contents, or None if not known"""
    update_cache()

    return magic.match(path, max_pri, min_pri)

def get_type_by_data(data, max_pri=100, min_pri=0):
    """Returns type of the data, which should be bytes."""
    update_cache()

    return magic.match_data(data, max_pri, min_pri)

def _get_type_by_stat(st_mode):
    """Match special filesystem objects to Mimetypes."""
    if stat.S_ISDIR(st_mode): return inode_dir
    elif stat.S_ISCHR(st_mode): return inode_char
    elif stat.S_ISBLK(st_mode): return inode_block
    elif stat.S_ISFIFO(st_mode): return inode_fifo
    elif stat.S_ISLNK(st_mode): return inode_symlink
    elif stat.S_ISSOCK(st_mode): return inode_socket
    return inode_door

def get_type(path, follow=True, name_pri=100):
    """Returns type of file indicated by path.
    
    This function is *deprecated* - :func:`get_type2` is more accurate.
    
    :param path: pathname to check (need not exist)
    :param follow: when reading file, follow symbolic links
    :param name_pri: Priority to do name matches. 100=override magic
    
    This tries to use the contents of the file, and falls back to the name. It
    can also handle special filesystem objects like directories and sockets.
    """
    update_cache()
    
    try:
        if follow:
            st = os.stat(path)
        else:
            st = os.lstat(path)
    except:
        t = get_type_by_name(path)
        return t or text

    if stat.S_ISREG(st.st_mode):
        # Regular file
        t = get_type_by_contents(path, min_pri=name_pri)
        if not t: t = get_type_by_name(path)
        if not t: t = get_type_by_contents(path, max_pri=name_pri)
        if t is None:
            if stat.S_IMODE(st.st_mode) & 0o111:
                return app_exe
            else:
                return text
        return t
    else:
        return _get_type_by_stat(st.st_mode)

def get_type2(path, follow=True):
    """Find the MIMEtype of a file using the XDG recommended checking order.
    
    This first checks the filename, then uses file contents if the name doesn't
    give an unambiguous MIMEtype. It can also handle special filesystem objects
    like directories and sockets.
    
    :param path: file path to examine (need not exist)
    :param follow: whether to follow symlinks
    
    :rtype: :class:`MIMEtype`
    
    .. versionadded:: 1.0
    """
    update_cache()
    
    try:
        st = os.stat(path) if follow else os.lstat(path)
    except OSError:
        return get_type_by_name(path) or octet_stream
    
    if not stat.S_ISREG(st.st_mode):
        # Special filesystem objects
        return _get_type_by_stat(st.st_mode)
    
    mtypes = sorted(globs.all_matches(path), key=(lambda x: x[1]), reverse=True)
    if mtypes:
        max_weight = mtypes[0][1]
        i = 1
        for mt, w in mtypes[1:]:
            if w < max_weight:
                break
            i += 1
        mtypes = mtypes[:i]
        if len(mtypes) == 1:
            return mtypes[0][0]
    
        possible = [mt for mt,w in mtypes]
    else:
        possible = None   # Try all magic matches
    
    try:
        t = magic.match(path, possible=possible)
    except IOError:
        t = None
    
    if t:
        return t
    elif mtypes:
        return mtypes[0][0]
    elif stat.S_IMODE(st.st_mode) & 0o111:
        return app_exe
    else:
        return text if is_text_file(path) else octet_stream

def is_text_file(path):
    """Guess whether a file contains text or binary data.
    
    Heuristic: binary if the first 32 bytes include ASCII control characters.
    This rule may change in future versions.
    
    .. versionadded:: 1.0
    """
    try:
        f = open(path, 'rb')
    except IOError:
        return False
    
    with f:
        return _is_text(f.read(32))

if PY3:
    def _is_text(data):
        return not any(b <= 0x8 or 0xe <= b < 0x20 or b == 0x7f for b in data)
else:
    def _is_text(data):
        return not any(b <= '\x08' or '\x0e' <= b < '\x20' or b == '\x7f' \
                            for b in data)

_mime2ext_cache = None
_mime2ext_cache_uptodate = False

def get_extensions(mimetype):
    """Retrieve the set of filename extensions matching a given MIMEtype.
    
    Extensions are returned without a leading dot, e.g. 'py'. If no extensions
    are registered for the MIMEtype, returns an empty set.
    
    The extensions are stored in a cache the first time this is called.
    
    .. versionadded:: 1.0
    """
    global _mime2ext_cache, _mime2ext_cache_uptodate
    update_cache()
    if not _mime2ext_cache_uptodate:
        _mime2ext_cache = defaultdict(set)
        for ext, mtypes in globs.exts.items():
            for mtype, prio in mtypes:
                _mime2ext_cache[mtype].add(ext)
        _mime2ext_cache_uptodate = True
    
    return _mime2ext_cache[mimetype]
        

def install_mime_info(application, package_file):
    """Copy 'package_file' as ``~/.local/share/mime/packages/<application>.xml.``
    If package_file is None, install ``<app_dir>/<application>.xml``.
    If already installed, does nothing. May overwrite an existing
    file with the same name (if the contents are different)"""
    application += '.xml'

    with open(package_file) as f:
        new_data = f.read()

    # See if the file is already installed
    package_dir = os.path.join('mime', 'packages')
    resource = os.path.join(package_dir, application)
    for x in BaseDirectory.load_data_paths(resource):
        try:
            with open(x) as f:
                old_data = f.read()
        except:
            continue
        if old_data == new_data:
            return  # Already installed

    global _cache_uptodate
    _cache_uptodate = False

    # Not already installed; add a new copy
    # Create the directory structure...
    new_file = os.path.join(BaseDirectory.save_data_path(package_dir), application)

    # Write the file...
    with open(new_file, 'w') as f:
        f.write(new_data)

    # Update the database...
    command = 'update-mime-database'
    if os.spawnlp(os.P_WAIT, command, command, BaseDirectory.save_data_path('mime')):
        os.unlink(new_file)
        raise Exception("The '%s' command returned an error code!\n" \
                  "Make sure you have the freedesktop.org shared MIME package:\n" \
                  "http://standards.freedesktop.org/shared-mime-info/" % command)
