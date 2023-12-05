"""
Functions to configure Basic Settings
"""

language = "C"
windowmanager = None
icon_theme = "hicolor"
icon_size = 48
cache_time = 5
root_mode = False

def setWindowManager(wm):
    global windowmanager
    windowmanager = wm

def setIconTheme(theme):
    global icon_theme
    icon_theme = theme
    import xdg.IconTheme
    xdg.IconTheme.themes = []

def setIconSize(size):
    global icon_size
    icon_size = size

def setCacheTime(time):
    global cache_time
    cache_time = time

def setLocale(lang):
    import locale
    lang = locale.normalize(lang)
    locale.setlocale(locale.LC_ALL, lang)
    import xdg.Locale
    xdg.Locale.update(lang)

def setRootMode(boolean):
    global root_mode
    root_mode = boolean
