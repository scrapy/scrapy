""" CLass to edit XDG Menus """
import os
try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

from xdg.Menu import Menu, MenuEntry, Layout, Separator, XMLMenuBuilder
from xdg.BaseDirectory import xdg_config_dirs, xdg_data_dirs
from xdg.Exceptions import ParsingError 
from xdg.Config import setRootMode

# XML-Cleanups: Move / Exclude
# FIXME: proper reverte/delete
# FIXME: pass AppDirs/DirectoryDirs around in the edit/move functions
# FIXME: catch Exceptions
# FIXME: copy functions
# FIXME: More Layout stuff
# FIXME: unod/redo function / remove menu...
# FIXME: Advanced MenuEditing Stuff: LegacyDir/MergeFile
#        Complex Rules/Deleted/OnlyAllocated/AppDirs/DirectoryDirs


class MenuEditor(object):

    def __init__(self, menu=None, filename=None, root=False):
        self.menu = None
        self.filename = None
        self.tree = None
        self.parser = XMLMenuBuilder()
        self.parse(menu, filename, root)

        # fix for creating two menus with the same name on the fly
        self.filenames = []

    def parse(self, menu=None, filename=None, root=False):
        if root:
            setRootMode(True)

        if isinstance(menu, Menu):
            self.menu = menu
        elif menu:
            self.menu = self.parser.parse(menu)
        else:
            self.menu = self.parser.parse()

        if root:
            self.filename = self.menu.Filename
        elif filename:
            self.filename = filename
        else:
            self.filename = os.path.join(xdg_config_dirs[0], "menus", os.path.split(self.menu.Filename)[1])

        try:
            self.tree = etree.parse(self.filename)
        except IOError:
            root = etree.fromstring("""
<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN" "http://standards.freedesktop.org/menu-spec/menu-1.0.dtd">
    <Menu>
        <Name>Applications</Name>
        <MergeFile type="parent">%s</MergeFile>
    </Menu>
""" % self.menu.Filename)
            self.tree = etree.ElementTree(root)
        except ParsingError:
            raise ParsingError('Not a valid .menu file', self.filename)

        #FIXME: is this needed with etree ?
        self.__remove_whitespace_nodes(self.tree)

    def save(self):
        self.__saveEntries(self.menu)
        self.__saveMenu()

    def createMenuEntry(self, parent, name, command=None, genericname=None, comment=None, icon=None, terminal=None, after=None, before=None):
        menuentry = MenuEntry(self.__getFileName(name, ".desktop"))
        menuentry = self.editMenuEntry(menuentry, name, genericname, comment, command, icon, terminal)

        self.__addEntry(parent, menuentry, after, before)

        self.menu.sort()

        return menuentry

    def createMenu(self, parent, name, genericname=None, comment=None, icon=None, after=None, before=None):
        menu = Menu()

        menu.Parent = parent
        menu.Depth = parent.Depth + 1
        menu.Layout = parent.DefaultLayout
        menu.DefaultLayout = parent.DefaultLayout

        menu = self.editMenu(menu, name, genericname, comment, icon)

        self.__addEntry(parent, menu, after, before)

        self.menu.sort()

        return menu

    def createSeparator(self, parent, after=None, before=None):
        separator = Separator(parent)

        self.__addEntry(parent, separator, after, before)

        self.menu.sort()

        return separator

    def moveMenuEntry(self, menuentry, oldparent, newparent, after=None, before=None):
        self.__deleteEntry(oldparent, menuentry, after, before)
        self.__addEntry(newparent, menuentry, after, before)

        self.menu.sort()

        return menuentry

    def moveMenu(self, menu, oldparent, newparent, after=None, before=None):
        self.__deleteEntry(oldparent, menu, after, before)
        self.__addEntry(newparent, menu, after, before)

        root_menu = self.__getXmlMenu(self.menu.Name)
        if oldparent.getPath(True) != newparent.getPath(True):
            self.__addXmlMove(root_menu, os.path.join(oldparent.getPath(True), menu.Name), os.path.join(newparent.getPath(True), menu.Name))

        self.menu.sort()

        return menu

    def moveSeparator(self, separator, parent, after=None, before=None):
        self.__deleteEntry(parent, separator, after, before)
        self.__addEntry(parent, separator, after, before)

        self.menu.sort()

        return separator

    def copyMenuEntry(self, menuentry, oldparent, newparent, after=None, before=None):
        self.__addEntry(newparent, menuentry, after, before)

        self.menu.sort()

        return menuentry

    def editMenuEntry(self, menuentry, name=None, genericname=None, comment=None, command=None, icon=None, terminal=None, nodisplay=None, hidden=None):
        deskentry = menuentry.DesktopEntry

        if name:
            if not deskentry.hasKey("Name"):
                deskentry.set("Name", name)
            deskentry.set("Name", name, locale=True)
        if comment:
            if not deskentry.hasKey("Comment"):
                deskentry.set("Comment", comment)
            deskentry.set("Comment", comment, locale=True)
        if genericname:
            if not deskentry.hasKey("GenericName"):
                deskentry.set("GenericName", genericname)
            deskentry.set("GenericName", genericname, locale=True)
        if command:
            deskentry.set("Exec", command)
        if icon:
            deskentry.set("Icon", icon)

        if terminal:
            deskentry.set("Terminal", "true")
        elif not terminal:
            deskentry.set("Terminal", "false")

        if nodisplay is True:
            deskentry.set("NoDisplay", "true")
        elif nodisplay is False:
            deskentry.set("NoDisplay", "false")

        if hidden is True:
            deskentry.set("Hidden", "true")
        elif hidden is False:
            deskentry.set("Hidden", "false")

        menuentry.updateAttributes()

        if len(menuentry.Parents) > 0:
            self.menu.sort()

        return menuentry

    def editMenu(self, menu, name=None, genericname=None, comment=None, icon=None, nodisplay=None, hidden=None):
        # Hack for legacy dirs
        if isinstance(menu.Directory, MenuEntry) and menu.Directory.Filename == ".directory":
            xml_menu = self.__getXmlMenu(menu.getPath(True, True))
            self.__addXmlTextElement(xml_menu, 'Directory', menu.Name + ".directory")
            menu.Directory.setAttributes(menu.Name + ".directory")
        # Hack for New Entries
        elif not isinstance(menu.Directory, MenuEntry):
            if not name:
                name = menu.Name
            filename = self.__getFileName(name, ".directory").replace("/", "")
            if not menu.Name:
                menu.Name = filename.replace(".directory", "")
            xml_menu = self.__getXmlMenu(menu.getPath(True, True))
            self.__addXmlTextElement(xml_menu, 'Directory', filename)
            menu.Directory = MenuEntry(filename)

        deskentry = menu.Directory.DesktopEntry

        if name:
            if not deskentry.hasKey("Name"):
                deskentry.set("Name", name)
            deskentry.set("Name", name, locale=True)
        if genericname:
            if not deskentry.hasKey("GenericName"):
                deskentry.set("GenericName", genericname)
            deskentry.set("GenericName", genericname, locale=True)
        if comment:
            if not deskentry.hasKey("Comment"):
                deskentry.set("Comment", comment)
            deskentry.set("Comment", comment, locale=True)
        if icon:
            deskentry.set("Icon", icon)

        if nodisplay is True:
            deskentry.set("NoDisplay", "true")
        elif nodisplay is False:
            deskentry.set("NoDisplay", "false")

        if hidden is True:
            deskentry.set("Hidden", "true")
        elif hidden is False:
            deskentry.set("Hidden", "false")

        menu.Directory.updateAttributes()

        if isinstance(menu.Parent, Menu):
            self.menu.sort()

        return menu

    def hideMenuEntry(self, menuentry):
        self.editMenuEntry(menuentry, nodisplay=True)

    def unhideMenuEntry(self, menuentry):
        self.editMenuEntry(menuentry, nodisplay=False, hidden=False)

    def hideMenu(self, menu):
        self.editMenu(menu, nodisplay=True)

    def unhideMenu(self, menu):
        self.editMenu(menu, nodisplay=False, hidden=False)
        xml_menu = self.__getXmlMenu(menu.getPath(True, True), False)
        deleted = xml_menu.findall('Deleted')
        not_deleted = xml_menu.findall('NotDeleted')
        for node in deleted + not_deleted:
            xml_menu.remove(node)

    def deleteMenuEntry(self, menuentry):
        if self.getAction(menuentry) == "delete":
            self.__deleteFile(menuentry.DesktopEntry.filename)
            for parent in menuentry.Parents:
                self.__deleteEntry(parent, menuentry)
            self.menu.sort()
        return menuentry

    def revertMenuEntry(self, menuentry):
        if self.getAction(menuentry) == "revert":
            self.__deleteFile(menuentry.DesktopEntry.filename)
            menuentry.Original.Parents = []
            for parent in menuentry.Parents:
                index = parent.Entries.index(menuentry)
                parent.Entries[index] = menuentry.Original
                index = parent.MenuEntries.index(menuentry)
                parent.MenuEntries[index] = menuentry.Original
                menuentry.Original.Parents.append(parent)
            self.menu.sort()
        return menuentry

    def deleteMenu(self, menu):
        if self.getAction(menu) == "delete":
            self.__deleteFile(menu.Directory.DesktopEntry.filename)
            self.__deleteEntry(menu.Parent, menu)
            xml_menu = self.__getXmlMenu(menu.getPath(True, True))
            parent = self.__get_parent_node(xml_menu)
            parent.remove(xml_menu)
            self.menu.sort()
        return menu

    def revertMenu(self, menu):
        if self.getAction(menu) == "revert":
            self.__deleteFile(menu.Directory.DesktopEntry.filename)
            menu.Directory = menu.Directory.Original
            self.menu.sort()
        return menu

    def deleteSeparator(self, separator):
        self.__deleteEntry(separator.Parent, separator, after=True)

        self.menu.sort()

        return separator

    """ Private Stuff """
    def getAction(self, entry):
        if isinstance(entry, Menu):
            if not isinstance(entry.Directory, MenuEntry):
                return "none"
            elif entry.Directory.getType() == "Both":
                return "revert"
            elif entry.Directory.getType() == "User" and (
                len(entry.Submenus) + len(entry.MenuEntries)
            ) == 0:
                return "delete"

        elif isinstance(entry, MenuEntry):
            if entry.getType() == "Both":
                return "revert"
            elif entry.getType() == "User":
                return "delete"
            else:
                return "none"

        return "none"

    def __saveEntries(self, menu):
        if not menu:
            menu = self.menu
        if isinstance(menu.Directory, MenuEntry):
            menu.Directory.save()
        for entry in menu.getEntries(hidden=True):
            if isinstance(entry, MenuEntry):
                entry.save()
            elif isinstance(entry, Menu):
                self.__saveEntries(entry)

    def __saveMenu(self):
        if not os.path.isdir(os.path.dirname(self.filename)):
            os.makedirs(os.path.dirname(self.filename))
        self.tree.write(self.filename, encoding='utf-8')

    def __getFileName(self, name, extension):
        postfix = 0
        while 1:
            if postfix == 0:
                filename = name + extension
            else:
                filename = name + "-" + str(postfix) + extension
            if extension == ".desktop":
                dir = "applications"
            elif extension == ".directory":
                dir = "desktop-directories"
            if not filename in self.filenames and not os.path.isfile(
                os.path.join(xdg_data_dirs[0], dir, filename)
            ):
                self.filenames.append(filename)
                break
            else:
                postfix += 1

        return filename

    def __getXmlMenu(self, path, create=True, element=None):
        # FIXME: we should also return the menu's parent,
        # to avoid looking for it later on
        # @see Element.getiterator()
        if not element:
            element = self.tree

        if "/" in path:
            (name, path) = path.split("/", 1)
        else:
            name = path
            path = ""

        found = None
        for node in element.findall("Menu"):
            name_node = node.find('Name')
            if name_node.text == name:
                if path:
                    found = self.__getXmlMenu(path, create, node)
                else:
                    found = node
            if found:
                break
        if not found and create:
            node = self.__addXmlMenuElement(element, name)
            if path:
                found = self.__getXmlMenu(path, create, node)
            else:
                found = node

        return found

    def __addXmlMenuElement(self, element, name):
        menu_node = etree.SubElement('Menu', element)
        name_node = etree.SubElement('Name', menu_node)
        name_node.text = name
        return menu_node

    def __addXmlTextElement(self, element, name, text):
        node = etree.SubElement(name, element)
        node.text = text
        return node

    def __addXmlFilename(self, element, filename, type_="Include"):
        # remove old filenames
        includes = element.findall('Include')
        excludes = element.findall('Exclude')
        rules = includes + excludes
        for rule in rules:
            #FIXME: this finds only Rules whose FIRST child is a Filename element
            if rule[0].tag == "Filename" and rule[0].text == filename:
                element.remove(rule)
            # shouldn't it remove all occurences, like the following:
            #filename_nodes = rule.findall('.//Filename'):
                #for fn in filename_nodes:
                    #if fn.text == filename:
                        ##element.remove(rule)
                        #parent = self.__get_parent_node(fn)
                        #parent.remove(fn)

        # add new filename
        node = etree.SubElement(type_, element)
        self.__addXmlTextElement(node, 'Filename', filename)
        return node

    def __addXmlMove(self, element, old, new):
        node = etree.SubElement("Move", element)
        self.__addXmlTextElement(node, 'Old', old)
        self.__addXmlTextElement(node, 'New', new)
        return node

    def __addXmlLayout(self, element, layout):
        # remove old layout
        for node in element.findall("Layout"):
            element.remove(node)

        # add new layout
        node = etree.SubElement("Layout", element)
        for order in layout.order:
            if order[0] == "Separator":
                child = etree.SubElement("Separator", node)
            elif order[0] == "Filename":
                child = self.__addXmlTextElement(node, "Filename", order[1])
            elif order[0] == "Menuname":
                child = self.__addXmlTextElement(node, "Menuname", order[1])
            elif order[0] == "Merge":
                child = etree.SubElement("Merge", node)
                child.attrib["type"] = order[1]
        return node

    def __addLayout(self, parent):
        layout = Layout()
        layout.order = []
        layout.show_empty = parent.Layout.show_empty
        layout.inline = parent.Layout.inline
        layout.inline_header = parent.Layout.inline_header
        layout.inline_alias = parent.Layout.inline_alias
        layout.inline_limit = parent.Layout.inline_limit

        layout.order.append(["Merge", "menus"])
        for entry in parent.Entries:
            if isinstance(entry, Menu):
                layout.parseMenuname(entry.Name)
            elif isinstance(entry, MenuEntry):
                layout.parseFilename(entry.DesktopFileID)
            elif isinstance(entry, Separator):
                layout.parseSeparator()
        layout.order.append(["Merge", "files"])

        parent.Layout = layout

        return layout

    def __addEntry(self, parent, entry, after=None, before=None):
        if after or before:
            if after:
                index = parent.Entries.index(after) + 1
            elif before:
                index = parent.Entries.index(before)
            parent.Entries.insert(index, entry)
        else:
            parent.Entries.append(entry)

        xml_parent = self.__getXmlMenu(parent.getPath(True, True))

        if isinstance(entry, MenuEntry):
            parent.MenuEntries.append(entry)
            entry.Parents.append(parent)
            self.__addXmlFilename(xml_parent, entry.DesktopFileID, "Include")
        elif isinstance(entry, Menu):
            parent.addSubmenu(entry)

        if after or before:
            self.__addLayout(parent)
            self.__addXmlLayout(xml_parent, parent.Layout)

    def __deleteEntry(self, parent, entry, after=None, before=None):
        parent.Entries.remove(entry)

        xml_parent = self.__getXmlMenu(parent.getPath(True, True))

        if isinstance(entry, MenuEntry):
            entry.Parents.remove(parent)
            parent.MenuEntries.remove(entry)
            self.__addXmlFilename(xml_parent, entry.DesktopFileID, "Exclude")
        elif isinstance(entry, Menu):
            parent.Submenus.remove(entry)

        if after or before:
            self.__addLayout(parent)
            self.__addXmlLayout(xml_parent, parent.Layout)

    def __deleteFile(self, filename):
        try:
            os.remove(filename)
        except OSError:
            pass
        try:
            self.filenames.remove(filename)
        except ValueError:
            pass

    def __remove_whitespace_nodes(self, node):
        for child in node:
            text = child.text.strip()
            if not text:
                child.text = ''
            tail = child.tail.strip()
            if not tail:
                child.tail = ''
            if len(child):
                self.__remove_whilespace_nodes(child)

    def __get_parent_node(self, node):
        # elements in ElementTree doesn't hold a reference to their parent
        for parent, child in self.__iter_parent():
            if child is node:
                return child

    def __iter_parent(self):
        for parent in self.tree.getiterator():
            for child in parent:
                yield parent, child
