"""
Exception Classes for the xdg package
"""

debug = False

class Error(Exception):
    """Base class for exceptions defined here."""
    def __init__(self, msg):
        self.msg = msg
        Exception.__init__(self, msg)
    def __str__(self):
        return self.msg

class ValidationError(Error):
    """Raised when a file fails to validate.
    
    The filename is the .file attribute.
    """
    def __init__(self, msg, file):
        self.msg = msg
        self.file = file
        Error.__init__(self, "ValidationError in file '%s': %s " % (file, msg))

class ParsingError(Error):
    """Raised when a file cannot be parsed.
    
    The filename is the .file attribute.
    """
    def __init__(self, msg, file):
        self.msg = msg
        self.file = file
        Error.__init__(self, "ParsingError in file '%s', %s" % (file, msg))

class NoKeyError(Error):
    """Raised when trying to access a nonexistant key in an INI-style file.
    
    Attributes are .key, .group and .file.
    """
    def __init__(self, key, group, file):
        Error.__init__(self, "No key '%s' in group %s of file %s" % (key, group, file))
        self.key = key
        self.group = group
        self.file = file

class DuplicateKeyError(Error):
    """Raised when the same key occurs twice in an INI-style file.
    
    Attributes are .key, .group and .file.
    """
    def __init__(self, key, group, file):
        Error.__init__(self, "Duplicate key '%s' in group %s of file %s" % (key, group, file))
        self.key = key
        self.group = group
        self.file = file

class NoGroupError(Error):
    """Raised when trying to access a nonexistant group in an INI-style file.
    
    Attributes are .group and .file.
    """
    def __init__(self, group, file):
        Error.__init__(self, "No group: %s in file %s" % (group, file))
        self.group = group
        self.file = file

class DuplicateGroupError(Error):
    """Raised when the same key occurs twice in an INI-style file.
    
    Attributes are .group and .file.
    """
    def __init__(self, group, file):
        Error.__init__(self, "Duplicate group: %s in file %s" % (group, file))
        self.group = group
        self.file = file

class NoThemeError(Error):
    """Raised when trying to access a nonexistant icon theme.
    
    The name of the theme is the .theme attribute.
    """
    def __init__(self, theme):
        Error.__init__(self, "No such icon-theme: %s" % theme)
        self.theme = theme
