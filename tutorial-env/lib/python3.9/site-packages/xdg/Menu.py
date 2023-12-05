"""
Implementation of the XDG Menu Specification
http://standards.freedesktop.org/menu-spec/

Example code:

from xdg.Menu import parse, Menu, MenuEntry

def print_menu(menu, tab=0):
  for submenu in menu.Entries:
    if isinstance(submenu, Menu):
      print ("\t" * tab) + unicode(submenu)
      print_menu(submenu, tab+1)
    elif isinstance(submenu, MenuEntry):
      print ("\t" * tab) + unicode(submenu.DesktopEntry)

print_menu(parse())
"""

import os
import locale
import subprocess
import ast
import sys
try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

from xdg.BaseDirectory import xdg_data_dirs, xdg_config_dirs
from xdg.DesktopEntry import DesktopEntry
from xdg.Exceptions import ParsingError
from xdg.util import PY3

import xdg.Locale
import xdg.Config


def _ast_const(name):
    if sys.version_info >= (3, 4):
        name = ast.literal_eval(name)
        if sys.version_info >= (3, 8):
            return ast.Constant(name)
        else:
            return ast.NameConstant(name)
    else:
        return ast.Name(id=name, ctx=ast.Load())


def _strxfrm(s):
    """Wrapper around locale.strxfrm that accepts unicode strings on Python 2.

    See Python bug #2481.
    """
    if (not PY3) and isinstance(s, unicode):
        s = s.encode('utf-8')
    return locale.strxfrm(s)


DELETED = "Deleted"
NO_DISPLAY = "NoDisplay"
HIDDEN = "Hidden"
EMPTY = "Empty"
NOT_SHOW_IN = "NotShowIn"
NO_EXEC = "NoExec"


class Menu:
    """Menu containing sub menus under menu.Entries

    Contains both Menu and MenuEntry items.
    """
    def __init__(self):
        # Public stuff
        self.Name = ""
        self.Directory = None
        self.Entries = []
        self.Doc = ""
        self.Filename = ""
        self.Depth = 0
        self.Parent = None
        self.NotInXml = False

        # Can be True, False, DELETED, NO_DISPLAY, HIDDEN, EMPTY or NOT_SHOW_IN
        self.Show = True
        self.Visible = 0

        # Private stuff, only needed for parsing
        self.AppDirs = []
        self.DefaultLayout = None
        self.Deleted = None
        self.Directories = []
        self.DirectoryDirs = []
        self.Layout = None
        self.MenuEntries = []
        self.Moves = []
        self.OnlyUnallocated = None
        self.Rules = []
        self.Submenus = []

    def __str__(self):
        return self.Name

    def __add__(self, other):
        for dir in other.AppDirs:
            self.AppDirs.append(dir)

        for dir in other.DirectoryDirs:
            self.DirectoryDirs.append(dir)

        for directory in other.Directories:
            self.Directories.append(directory)

        if other.Deleted is not None:
            self.Deleted = other.Deleted

        if other.OnlyUnallocated is not None:
            self.OnlyUnallocated = other.OnlyUnallocated

        if other.Layout:
            self.Layout = other.Layout

        if other.DefaultLayout:
            self.DefaultLayout = other.DefaultLayout

        for rule in other.Rules:
            self.Rules.append(rule)

        for move in other.Moves:
            self.Moves.append(move)

        for submenu in other.Submenus:
            self.addSubmenu(submenu)

        return self

    # FIXME: Performance: cache getName()
    def __cmp__(self, other):
        return locale.strcoll(self.getName(), other.getName())

    def _key(self):
        """Key function for locale-aware sorting."""
        return _strxfrm(self.getName())

    def __lt__(self, other):
        try:
            other = other._key()
        except AttributeError:
            pass
        return self._key() < other

    def __eq__(self, other):
        try:
            return self.Name == unicode(other)
        except NameError:  # unicode() becomes str() in Python 3
            return self.Name == str(other)

    """ PUBLIC STUFF """
    def getEntries(self, show_hidden=False):
        """Interator for a list of Entries visible to the user."""
        for entry in self.Entries:
            if show_hidden:
                yield entry
            elif entry.Show is True:
                yield entry

    # FIXME: Add searchEntry/seaqrchMenu function
    # search for name/comment/genericname/desktopfileid
    # return multiple items

    def getMenuEntry(self, desktopfileid, deep=False):
        """Searches for a MenuEntry with a given DesktopFileID."""
        for menuentry in self.MenuEntries:
            if menuentry.DesktopFileID == desktopfileid:
                return menuentry
        if deep:
            for submenu in self.Submenus:
                submenu.getMenuEntry(desktopfileid, deep)

    def getMenu(self, path):
        """Searches for a Menu with a given path."""
        array = path.split("/", 1)
        for submenu in self.Submenus:
            if submenu.Name == array[0]:
                if len(array) > 1:
                    return submenu.getMenu(array[1])
                else:
                    return submenu

    def getPath(self, org=False, toplevel=False):
        """Returns this menu's path in the menu structure."""
        parent = self
        names = []
        while 1:
            if org:
                names.append(parent.Name)
            else:
                names.append(parent.getName())
            if parent.Depth > 0:
                parent = parent.Parent
            else:
                break
        names.reverse()
        path = ""
        if not toplevel:
            names.pop(0)
        for name in names:
            path = os.path.join(path, name)
        return path

    def getName(self):
        """Returns the menu's localised name."""
        try:
            return self.Directory.DesktopEntry.getName()
        except AttributeError:
            return self.Name

    def getGenericName(self):
        """Returns the menu's generic name."""
        try:
            return self.Directory.DesktopEntry.getGenericName()
        except AttributeError:
            return ""

    def getComment(self):
        """Returns the menu's comment text."""
        try:
            return self.Directory.DesktopEntry.getComment()
        except AttributeError:
            return ""

    def getIcon(self):
        """Returns the menu's icon, filename or simple name"""
        try:
            return self.Directory.DesktopEntry.getIcon()
        except AttributeError:
            return ""

    def sort(self):
        self.Entries = []
        self.Visible = 0

        for submenu in self.Submenus:
            submenu.sort()

        _submenus = set()
        _entries = set()

        for order in self.Layout.order:
            if order[0] == "Filename":
                _entries.add(order[1])
            elif order[0] == "Menuname":
                _submenus.add(order[1])

        for order in self.Layout.order:
            if order[0] == "Separator":
                separator = Separator(self)
                if len(self.Entries) > 0 and isinstance(self.Entries[-1], Separator):
                    separator.Show = False
                self.Entries.append(separator)
            elif order[0] == "Filename":
                menuentry = self.getMenuEntry(order[1])
                if menuentry:
                    self.Entries.append(menuentry)
            elif order[0] == "Menuname":
                submenu = self.getMenu(order[1])
                if submenu:
                    if submenu.Layout.inline:
                        self.merge_inline(submenu)
                    else:
                        self.Entries.append(submenu)
            elif order[0] == "Merge":
                if order[1] == "files" or order[1] == "all":
                    self.MenuEntries.sort()
                    for menuentry in self.MenuEntries:
                        if menuentry.DesktopFileID not in _entries:
                            self.Entries.append(menuentry)
                elif order[1] == "menus" or order[1] == "all":
                    self.Submenus.sort()
                    for submenu in self.Submenus:
                        if submenu.Name not in _submenus:
                            if submenu.Layout.inline:
                                self.merge_inline(submenu)
                            else:
                                self.Entries.append(submenu)

        # getHidden / NoDisplay / OnlyShowIn / NotOnlyShowIn / Deleted / NoExec
        for entry in self.Entries:
            entry.Show = True
            self.Visible += 1
            if isinstance(entry, Menu):
                if entry.Deleted is True:
                    entry.Show = DELETED
                    self.Visible -= 1
                elif isinstance(entry.Directory, MenuEntry):
                    if entry.Directory.DesktopEntry.getNoDisplay():
                        entry.Show = NO_DISPLAY
                        self.Visible -= 1
                    elif entry.Directory.DesktopEntry.getHidden():
                        entry.Show = HIDDEN
                        self.Visible -= 1
            elif isinstance(entry, MenuEntry):
                if entry.DesktopEntry.getNoDisplay():
                    entry.Show = NO_DISPLAY
                    self.Visible -= 1
                elif entry.DesktopEntry.getHidden():
                    entry.Show = HIDDEN
                    self.Visible -= 1
                elif entry.DesktopEntry.getTryExec() and not entry.DesktopEntry.findTryExec():
                    entry.Show = NO_EXEC
                    self.Visible -= 1
                elif xdg.Config.windowmanager:
                    if (entry.DesktopEntry.getOnlyShowIn() != [] and (
                            xdg.Config.windowmanager not in entry.DesktopEntry.getOnlyShowIn()
                        )
                    ) or (
                        xdg.Config.windowmanager in entry.DesktopEntry.getNotShowIn()
                    ):
                        entry.Show = NOT_SHOW_IN
                        self.Visible -= 1
            elif isinstance(entry, Separator):
                self.Visible -= 1
        # remove separators at the beginning and at the end
        if len(self.Entries) > 0:
            if isinstance(self.Entries[0], Separator):
                self.Entries[0].Show = False
        if len(self.Entries) > 1:
            if isinstance(self.Entries[-1], Separator):
                self.Entries[-1].Show = False

        # show_empty tag
        for entry in self.Entries[:]:
            if isinstance(entry, Menu) and not entry.Layout.show_empty and entry.Visible == 0:
                entry.Show = EMPTY
                self.Visible -= 1
                if entry.NotInXml is True:
                    self.Entries.remove(entry)

    """ PRIVATE STUFF """
    def addSubmenu(self, newmenu):
        for submenu in self.Submenus:
            if submenu == newmenu:
                submenu += newmenu
                break
        else:
            self.Submenus.append(newmenu)
            newmenu.Parent = self
            newmenu.Depth = self.Depth + 1

    # inline tags
    def merge_inline(self, submenu):
        """Appends a submenu's entries to this menu
        See the <Menuname> section of the spec about the "inline" attribute
        """
        if len(submenu.Entries) == 1 and submenu.Layout.inline_alias:
            menuentry = submenu.Entries[0]
            menuentry.DesktopEntry.set("Name", submenu.getName(), locale=True)
            menuentry.DesktopEntry.set("GenericName", submenu.getGenericName(), locale=True)
            menuentry.DesktopEntry.set("Comment", submenu.getComment(), locale=True)
            self.Entries.append(menuentry)
        elif len(submenu.Entries) <= submenu.Layout.inline_limit or submenu.Layout.inline_limit == 0:
            if submenu.Layout.inline_header:
                header = Header(submenu.getName(), submenu.getGenericName(), submenu.getComment())
                self.Entries.append(header)
            for entry in submenu.Entries:
                self.Entries.append(entry)
        else:
            self.Entries.append(submenu)


class Move:
    "A move operation"
    def __init__(self, old="", new=""):
        self.Old = old
        self.New = new

    def __cmp__(self, other):
        return cmp(self.Old, other.Old)


class Layout:
    "Menu Layout class"
    def __init__(self, show_empty=False, inline=False, inline_limit=4,
                 inline_header=True, inline_alias=False):
        self.show_empty = show_empty
        self.inline = inline
        self.inline_limit = inline_limit
        self.inline_header = inline_header
        self.inline_alias = inline_alias
        self._order = []
        self._default_order = [
            ['Merge', 'menus'],
            ['Merge', 'files']
        ]

    @property
    def order(self):
        return self._order if self._order else self._default_order

    @order.setter
    def order(self, order):
        self._order = order


class Rule:
    """Include / Exclude Rules Class"""

    TYPE_INCLUDE, TYPE_EXCLUDE = 0, 1

    @classmethod
    def fromFilename(cls, type, filename):
        tree = ast.Expression(
            body=ast.Compare(
                left=ast.Str(filename),
                ops=[ast.Eq()],
                comparators=[ast.Attribute(
                    value=ast.Name(id='menuentry', ctx=ast.Load()),
                    attr='DesktopFileID',
                    ctx=ast.Load()
                )]
            ),
            lineno=1, col_offset=0
        )
        ast.fix_missing_locations(tree)
        rule = Rule(type, tree)
        return rule

    def __init__(self, type, expression):
        # Type is TYPE_INCLUDE or TYPE_EXCLUDE
        self.Type = type
        # expression is ast.Expression
        self.expression = expression
        self.code = compile(self.expression, '<compiled-menu-rule>', 'eval')

    def __str__(self):
        return ast.dump(self.expression)

    def apply(self, menuentries, run):
        for menuentry in menuentries:
            if run == 2 and (menuentry.MatchedInclude is True or
                             menuentry.Allocated is True):
                continue
            if eval(self.code):
                if self.Type is Rule.TYPE_INCLUDE:
                    menuentry.Add = True
                    menuentry.MatchedInclude = True
                else:
                    menuentry.Add = False
        return menuentries


class MenuEntry:
    "Wrapper for 'Menu Style' Desktop Entries"

    TYPE_USER = "User"
    TYPE_SYSTEM = "System"
    TYPE_BOTH = "Both"

    def __init__(self, filename, dir="", prefix=""):
        # Create entry
        self.DesktopEntry = DesktopEntry(os.path.join(dir, filename))
        self.setAttributes(filename, dir, prefix)

        # Can True, False DELETED, HIDDEN, EMPTY, NOT_SHOW_IN or NO_EXEC
        self.Show = True

        # Semi-Private
        self.Original = None
        self.Parents = []

        # Private Stuff
        self.Allocated = False
        self.Add = False
        self.MatchedInclude = False

        # Caching
        self.Categories = self.DesktopEntry.getCategories()

    def save(self):
        """Save any changes to the desktop entry."""
        if self.DesktopEntry.tainted:
            self.DesktopEntry.write()

    def getDir(self):
        """Return the directory containing the desktop entry file."""
        return self.DesktopEntry.filename.replace(self.Filename, '')

    def getType(self):
        """Return the type of MenuEntry, System/User/Both"""
        if not xdg.Config.root_mode:
            if self.Original:
                return self.TYPE_BOTH
            elif xdg_data_dirs[0] in self.DesktopEntry.filename:
                return self.TYPE_USER
            else:
                return self.TYPE_SYSTEM
        else:
            return self.TYPE_USER

    def setAttributes(self, filename, dir="", prefix=""):
        self.Filename = filename
        self.Prefix = prefix
        self.DesktopFileID = os.path.join(prefix, filename).replace("/", "-")

        if not os.path.isabs(self.DesktopEntry.filename):
            self.__setFilename()

    def updateAttributes(self):
        if self.getType() == self.TYPE_SYSTEM:
            self.Original = MenuEntry(self.Filename, self.getDir(), self.Prefix)
            self.__setFilename()

    def __setFilename(self):
        if not xdg.Config.root_mode:
            path = xdg_data_dirs[0]
        else:
            path = xdg_data_dirs[1]

        if self.DesktopEntry.getType() == "Application":
            dir_ = os.path.join(path, "applications")
        else:
            dir_ = os.path.join(path, "desktop-directories")

        self.DesktopEntry.filename = os.path.join(dir_, self.Filename)

    def __cmp__(self, other):
        return locale.strcoll(self.DesktopEntry.getName(), other.DesktopEntry.getName())

    def _key(self):
        """Key function for locale-aware sorting."""
        return _strxfrm(self.DesktopEntry.getName())

    def __lt__(self, other):
        try:
            other = other._key()
        except AttributeError:
            pass
        return self._key() < other

    def __eq__(self, other):
        if self.DesktopFileID == str(other):
            return True
        else:
            return False

    def __repr__(self):
        return self.DesktopFileID


class Separator:
    "Just a dummy class for Separators"
    def __init__(self, parent):
        self.Parent = parent
        self.Show = True


class Header:
    "Class for Inline Headers"
    def __init__(self, name, generic_name, comment):
        self.Name = name
        self.GenericName = generic_name
        self.Comment = comment

    def __str__(self):
        return self.Name


TYPE_DIR, TYPE_FILE = 0, 1


def _check_file_path(value, filename, type):
    path = os.path.dirname(filename)
    if not os.path.isabs(value):
        value = os.path.join(path, value)
    value = os.path.abspath(value)
    if not os.path.exists(value):
        return False
    if type == TYPE_DIR and os.path.isdir(value):
        return value
    if type == TYPE_FILE and os.path.isfile(value):
        return value
    return False


def _get_menu_file_path(filename):
    dirs = list(xdg_config_dirs)
    if xdg.Config.root_mode is True:
        dirs.pop(0)
    for d in dirs:
        menuname = os.path.join(d, "menus", filename)
        if os.path.isfile(menuname):
            return menuname


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return value.lower() == "true"


# remove duplicate entries from a list
def _dedupe(_list):
    _set = {}
    _list.reverse()
    _list = [_set.setdefault(e, e) for e in _list if e not in _set]
    _list.reverse()
    return _list


class XMLMenuBuilder(object):

    def __init__(self, debug=False):
        self.debug = debug

    def parse(self, filename=None):
        """Load an applications.menu file.

        filename : str, optional
          The default is ``$XDG_CONFIG_DIRS/menus/${XDG_MENU_PREFIX}applications.menu``.
        """
        # convert to absolute path
        if filename and not os.path.isabs(filename):
            filename = _get_menu_file_path(filename)
        # use default if no filename given
        if not filename:
            candidate = os.environ.get('XDG_MENU_PREFIX', '') + "applications.menu"
            filename = _get_menu_file_path(candidate)
        if not filename:
            raise ParsingError('File not found', "/etc/xdg/menus/%s" % candidate)
        # check if it is a .menu file
        if not filename.endswith(".menu"):
            raise ParsingError('Not a .menu file', filename)
        # create xml parser
        try:
            tree = etree.parse(filename)
        except:
            raise ParsingError('Not a valid .menu file', filename)

        # parse menufile
        self._merged_files = set()
        self._directory_dirs = set()
        self.cache = MenuEntryCache()

        menu = self.parse_menu(tree.getroot(), filename)
        menu.tree = tree
        menu.filename = filename

        self.handle_moves(menu)
        self.post_parse(menu)

        # generate the menu
        self.generate_not_only_allocated(menu)
        self.generate_only_allocated(menu)

        # and finally sort
        menu.sort()

        return menu

    def parse_menu(self, node, filename):
        menu = Menu()
        self.parse_node(node, filename, menu)
        return menu

    def parse_node(self, node, filename, parent=None):
        num_children = len(node)
        for child in node:
            tag, text = child.tag, child.text
            text = text.strip() if text else None
            if tag == 'Menu':
                menu = self.parse_menu(child, filename)
                parent.addSubmenu(menu)
            elif tag == 'AppDir' and text:
                self.parse_app_dir(text, filename, parent)
            elif tag == 'DefaultAppDirs':
                self.parse_default_app_dir(filename, parent)
            elif tag == 'DirectoryDir' and text:
                self.parse_directory_dir(text, filename, parent)
            elif tag == 'DefaultDirectoryDirs':
                self.parse_default_directory_dir(filename, parent)
            elif tag == 'Name' and text:
                parent.Name = text
            elif tag == 'Directory' and text:
                parent.Directories.append(text)
            elif tag == 'OnlyUnallocated':
                parent.OnlyUnallocated = True
            elif tag == 'NotOnlyUnallocated':
                parent.OnlyUnallocated = False
            elif tag == 'Deleted':
                parent.Deleted = True
            elif tag == 'NotDeleted':
                parent.Deleted = False
            elif tag == 'Include' or tag == 'Exclude':
                parent.Rules.append(self.parse_rule(child))
            elif tag == 'MergeFile':
                if child.attrib.get("type", None) == "parent":
                    self.parse_merge_file("applications.menu", child, filename, parent)
                elif text:
                    self.parse_merge_file(text, child, filename, parent)
            elif tag == 'MergeDir' and text:
                self.parse_merge_dir(text, child, filename, parent)
            elif tag == 'DefaultMergeDirs':
                self.parse_default_merge_dirs(child, filename, parent)
            elif tag == 'Move':
                parent.Moves.append(self.parse_move(child))
            elif tag == 'Layout':
                if num_children > 1:
                    parent.Layout = self.parse_layout(child)
            elif tag == 'DefaultLayout':
                if num_children > 1:
                    parent.DefaultLayout = self.parse_layout(child)
            elif tag == 'LegacyDir' and text:
                self.parse_legacy_dir(text, child.attrib.get("prefix", ""), filename, parent)
            elif tag == 'KDELegacyDirs':
                self.parse_kde_legacy_dirs(filename, parent)

    def parse_layout(self, node):
        layout = Layout(
            show_empty=_to_bool(node.attrib.get("show_empty", False)),
            inline=_to_bool(node.attrib.get("inline", False)),
            inline_limit=int(node.attrib.get("inline_limit", 4)),
            inline_header=_to_bool(node.attrib.get("inline_header", True)),
            inline_alias=_to_bool(node.attrib.get("inline_alias", False))
        )
        order = []
        for child in node:
            tag, text = child.tag, child.text
            text = text.strip() if text else None
            if tag == "Menuname" and text:
                order.append([
                    "Menuname",
                    text,
                    _to_bool(child.attrib.get("show_empty", False)),
                    _to_bool(child.attrib.get("inline", False)),
                    int(child.attrib.get("inline_limit", 4)),
                    _to_bool(child.attrib.get("inline_header", True)),
                    _to_bool(child.attrib.get("inline_alias", False))
                ])
            elif tag == "Separator":
                order.append(['Separator'])
            elif tag == "Filename" and text:
                order.append(["Filename", text])
            elif tag == "Merge":
                order.append([
                    "Merge",
                    child.attrib.get("type", "all")
                ])
        layout.order = order
        return layout

    def parse_move(self, node):
        old, new = "", ""
        for child in node:
            tag, text = child.tag, child.text
            text = text.strip() if text else None
            if tag == "Old" and text:
                old = text
            elif tag == "New" and text:
                new = text
        return Move(old, new)

    # ---------- <Rule> parsing

    def parse_rule(self, node):
        type = Rule.TYPE_INCLUDE if node.tag == 'Include' else Rule.TYPE_EXCLUDE
        tree = ast.Expression(lineno=1, col_offset=0)
        expr = self.parse_bool_op(node, ast.Or())
        if expr:
            tree.body = expr
        else:
            tree.body = _ast_const('False')
        ast.fix_missing_locations(tree)
        return Rule(type, tree)

    def parse_bool_op(self, node, operator):
        values = []
        for child in node:
            rule = self.parse_rule_node(child)
            if rule:
                values.append(rule)
        num_values = len(values)
        if num_values > 1:
            return ast.BoolOp(operator, values)
        elif num_values == 1:
            return values[0]
        return None

    def parse_rule_node(self, node):
        tag = node.tag
        if tag == 'Or':
            return self.parse_bool_op(node, ast.Or())
        elif tag == 'And':
            return self.parse_bool_op(node, ast.And())
        elif tag == 'Not':
            expr = self.parse_bool_op(node, ast.Or())
            return ast.UnaryOp(ast.Not(), expr) if expr else None
        elif tag == 'All':
            return _ast_const('True')
        elif tag == 'Category':
            category = node.text
            return ast.Compare(
                left=ast.Str(category),
                ops=[ast.In()],
                comparators=[ast.Attribute(
                    value=ast.Name(id='menuentry', ctx=ast.Load()),
                    attr='Categories',
                    ctx=ast.Load()
                )]
            )
        elif tag == 'Filename':
            filename = node.text
            return ast.Compare(
                left=ast.Str(filename),
                ops=[ast.Eq()],
                comparators=[ast.Attribute(
                    value=ast.Name(id='menuentry', ctx=ast.Load()),
                    attr='DesktopFileID',
                    ctx=ast.Load()
                )]
            )

    # ---------- App/Directory Dir Stuff

    def parse_app_dir(self, value, filename, parent):
        value = _check_file_path(value, filename, TYPE_DIR)
        if value:
            parent.AppDirs.append(value)

    def parse_default_app_dir(self, filename, parent):
        for d in reversed(xdg_data_dirs):
            self.parse_app_dir(os.path.join(d, "applications"), filename, parent)

    def parse_directory_dir(self, value, filename, parent):
        value = _check_file_path(value, filename, TYPE_DIR)
        if value:
            parent.DirectoryDirs.append(value)

    def parse_default_directory_dir(self, filename, parent):
        for d in reversed(xdg_data_dirs):
            self.parse_directory_dir(os.path.join(d, "desktop-directories"), filename, parent)

    # ---------- Merge Stuff

    def parse_merge_file(self, value, child, filename, parent):
        if child.attrib.get("type", None) == "parent":
            for d in xdg_config_dirs:
                rel_file = filename.replace(d, "").strip("/")
                if rel_file != filename:
                    for p in xdg_config_dirs:
                        if d == p:
                            continue
                        if os.path.isfile(os.path.join(p, rel_file)):
                            self.merge_file(os.path.join(p, rel_file), child, parent)
                            break
        else:
            value = _check_file_path(value, filename, TYPE_FILE)
            if value:
                self.merge_file(value, child, parent)

    def parse_merge_dir(self, value, child, filename, parent):
        value = _check_file_path(value, filename, TYPE_DIR)
        if value:
            for item in os.listdir(value):
                try:
                    if item.endswith(".menu"):
                        self.merge_file(os.path.join(value, item), child, parent)
                except UnicodeDecodeError:
                    continue

    def parse_default_merge_dirs(self, child, filename, parent):
        basename = os.path.splitext(os.path.basename(filename))[0]
        for d in reversed(xdg_config_dirs):
            self.parse_merge_dir(os.path.join(d, "menus", basename + "-merged"), child, filename, parent)

    def merge_file(self, filename, child, parent):
        # check for infinite loops
        if filename in self._merged_files:
            if self.debug:
                raise ParsingError('Infinite MergeFile loop detected', filename)
            else:
                return
        self._merged_files.add(filename)
        # load file
        try:
            tree = etree.parse(filename)
        except IOError:
            if self.debug:
                raise ParsingError('File not found', filename)
            else:
                return
        except:
            if self.debug:
                raise ParsingError('Not a valid .menu file', filename)
            else:
                return
        root = tree.getroot()
        self.parse_node(root, filename, parent)

    # ---------- Legacy Dir Stuff

    def parse_legacy_dir(self, dir_, prefix, filename, parent):
        m = self.merge_legacy_dir(dir_, prefix, filename, parent)
        if m:
            parent += m

    def merge_legacy_dir(self, dir_, prefix, filename, parent):
        dir_ = _check_file_path(dir_, filename, TYPE_DIR)
        if dir_ and dir_ not in self._directory_dirs:
            self._directory_dirs.add(dir_)
            m = Menu()
            m.AppDirs.append(dir_)
            m.DirectoryDirs.append(dir_)
            m.Name = os.path.basename(dir_)
            m.NotInXml = True

            for item in os.listdir(dir_):
                try:
                    if item == ".directory":
                        m.Directories.append(item)
                    elif os.path.isdir(os.path.join(dir_, item)):
                        m.addSubmenu(self.merge_legacy_dir(
                            os.path.join(dir_, item),
                            prefix,
                            filename,
                            parent
                        ))
                except UnicodeDecodeError:
                    continue

            self.cache.add_menu_entries([dir_], prefix, True)
            menuentries = self.cache.get_menu_entries([dir_], False)

            for menuentry in menuentries:
                categories = menuentry.Categories
                if len(categories) == 0:
                    r = Rule.fromFilename(Rule.TYPE_INCLUDE, menuentry.DesktopFileID)
                    m.Rules.append(r)
                if not dir_ in parent.AppDirs:
                    categories.append("Legacy")
                    menuentry.Categories = categories

            return m

    def parse_kde_legacy_dirs(self, filename, parent):
        try:
            proc = subprocess.Popen(
                ['kde-config', '--path', 'apps'],
                stdout=subprocess.PIPE,
                universal_newlines=True
            )
            output = proc.communicate()[0].splitlines()
        except OSError:
            # If kde-config doesn't exist, ignore this.
            return
        try:
            for dir_ in output[0].split(":"):
                self.parse_legacy_dir(dir_, "kde", filename, parent)
        except IndexError:
            pass

    def post_parse(self, menu):
        # unallocated / deleted
        if menu.Deleted is None:
            menu.Deleted = False
        if menu.OnlyUnallocated is None:
            menu.OnlyUnallocated = False

        # Layout Tags
        if not menu.Layout or not menu.DefaultLayout:
            if menu.DefaultLayout:
                menu.Layout = menu.DefaultLayout
            elif menu.Layout:
                if menu.Depth > 0:
                    menu.DefaultLayout = menu.Parent.DefaultLayout
                else:
                    menu.DefaultLayout = Layout()
            else:
                if menu.Depth > 0:
                    menu.Layout = menu.Parent.DefaultLayout
                    menu.DefaultLayout = menu.Parent.DefaultLayout
                else:
                    menu.Layout = Layout()
                    menu.DefaultLayout = Layout()

        # add parent's app/directory dirs
        if menu.Depth > 0:
            menu.AppDirs = menu.Parent.AppDirs + menu.AppDirs
            menu.DirectoryDirs = menu.Parent.DirectoryDirs + menu.DirectoryDirs

        # remove duplicates
        menu.Directories = _dedupe(menu.Directories)
        menu.DirectoryDirs = _dedupe(menu.DirectoryDirs)
        menu.AppDirs = _dedupe(menu.AppDirs)

        # go recursive through all menus
        for submenu in menu.Submenus:
            self.post_parse(submenu)

        # reverse so handling is easier
        menu.Directories.reverse()
        menu.DirectoryDirs.reverse()
        menu.AppDirs.reverse()

        # get the valid .directory file out of the list
        for directory in menu.Directories:
            for dir in menu.DirectoryDirs:
                if os.path.isfile(os.path.join(dir, directory)):
                    menuentry = MenuEntry(directory, dir)
                    if not menu.Directory:
                        menu.Directory = menuentry
                    elif menuentry.getType() == MenuEntry.TYPE_SYSTEM:
                        if menu.Directory.getType() == MenuEntry.TYPE_USER:
                            menu.Directory.Original = menuentry
            if menu.Directory:
                break

    # Finally generate the menu
    def generate_not_only_allocated(self, menu):
        for submenu in menu.Submenus:
            self.generate_not_only_allocated(submenu)

        if menu.OnlyUnallocated is False:
            self.cache.add_menu_entries(menu.AppDirs)
            menuentries = []
            for rule in menu.Rules:
                menuentries = rule.apply(self.cache.get_menu_entries(menu.AppDirs), 1)

            for menuentry in menuentries:
                if menuentry.Add is True:
                    menuentry.Parents.append(menu)
                    menuentry.Add = False
                    menuentry.Allocated = True
                    menu.MenuEntries.append(menuentry)

    def generate_only_allocated(self, menu):
        for submenu in menu.Submenus:
            self.generate_only_allocated(submenu)

        if menu.OnlyUnallocated is True:
            self.cache.add_menu_entries(menu.AppDirs)
            menuentries = []
            for rule in menu.Rules:
                menuentries = rule.apply(self.cache.get_menu_entries(menu.AppDirs), 2)
            for menuentry in menuentries:
                if menuentry.Add is True:
                    menuentry.Parents.append(menu)
                #   menuentry.Add = False
                #   menuentry.Allocated = True
                    menu.MenuEntries.append(menuentry)

    def handle_moves(self, menu):
        for submenu in menu.Submenus:
            self.handle_moves(submenu)
        # parse move operations
        for move in menu.Moves:
            move_from_menu = menu.getMenu(move.Old)
            if move_from_menu:
                # FIXME: this is assigned, but never used...
                move_to_menu = menu.getMenu(move.New)

                menus = move.New.split("/")
                oldparent = None
                while len(menus) > 0:
                    if not oldparent:
                        oldparent = menu
                    newmenu = oldparent.getMenu(menus[0])
                    if not newmenu:
                        newmenu = Menu()
                        newmenu.Name = menus[0]
                        if len(menus) > 1:
                            newmenu.NotInXml = True
                        oldparent.addSubmenu(newmenu)
                    oldparent = newmenu
                    menus.pop(0)

                newmenu += move_from_menu
                move_from_menu.Parent.Submenus.remove(move_from_menu)


class MenuEntryCache:
    "Class to cache Desktop Entries"
    def __init__(self):
        self.cacheEntries = {}
        self.cacheEntries['legacy'] = []
        self.cache = {}

    def add_menu_entries(self, dirs, prefix="", legacy=False):
        for dir_ in dirs:
            if not dir_ in self.cacheEntries:
                self.cacheEntries[dir_] = []
                self.__addFiles(dir_, "", prefix, legacy)

    def __addFiles(self, dir_, subdir, prefix, legacy):
        for item in os.listdir(os.path.join(dir_, subdir)):
            if item.endswith(".desktop"):
                try:
                    menuentry = MenuEntry(os.path.join(subdir, item), dir_, prefix)
                except ParsingError:
                    continue

                self.cacheEntries[dir_].append(menuentry)
                if legacy:
                    self.cacheEntries['legacy'].append(menuentry)
            elif os.path.isdir(os.path.join(dir_, subdir, item)) and not legacy:
                self.__addFiles(dir_, os.path.join(subdir, item), prefix, legacy)

    def get_menu_entries(self, dirs, legacy=True):
        entries = []
        ids = set()
        # handle legacy items
        appdirs = dirs[:]
        if legacy:
            appdirs.append("legacy")
        # cache the results again
        key = "".join(appdirs)
        try:
            return self.cache[key]
        except KeyError:
            pass
        for dir_ in appdirs:
            for menuentry in self.cacheEntries[dir_]:
                try:
                    if menuentry.DesktopFileID not in ids:
                        ids.add(menuentry.DesktopFileID)
                        entries.append(menuentry)
                    elif menuentry.getType() == MenuEntry.TYPE_SYSTEM:
                        # FIXME: This is only 99% correct, but still...
                        idx = entries.index(menuentry)
                        entry = entries[idx]
                        if entry.getType() == MenuEntry.TYPE_USER:
                            entry.Original = menuentry
                except UnicodeDecodeError:
                    continue
        self.cache[key] = entries
        return entries


def parse(filename=None, debug=False):
    """Helper function.
    Equivalent to calling xdg.Menu.XMLMenuBuilder().parse(filename)
    """
    return XMLMenuBuilder(debug).parse(filename)
