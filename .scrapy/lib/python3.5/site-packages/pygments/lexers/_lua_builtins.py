# -*- coding: utf-8 -*-
"""
    pygments.lexers._lua_builtins
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This file contains the names and modules of lua functions
    It is able to re-generate itself, but for adding new functions you
    probably have to add some callbacks (see function module_callbacks).

    Do not edit the MODULES dict by hand.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from __future__ import print_function


MODULES = {'basic': ('_G',
           '_VERSION',
           'assert',
           'collectgarbage',
           'dofile',
           'error',
           'getfenv',
           'getmetatable',
           'ipairs',
           'load',
           'loadfile',
           'loadstring',
           'next',
           'pairs',
           'pcall',
           'print',
           'rawequal',
           'rawget',
           'rawset',
           'select',
           'setfenv',
           'setmetatable',
           'tonumber',
           'tostring',
           'type',
           'unpack',
           'xpcall'),
 'coroutine': ('coroutine.create',
               'coroutine.resume',
               'coroutine.running',
               'coroutine.status',
               'coroutine.wrap',
               'coroutine.yield'),
 'debug': ('debug.debug',
           'debug.getfenv',
           'debug.gethook',
           'debug.getinfo',
           'debug.getlocal',
           'debug.getmetatable',
           'debug.getregistry',
           'debug.getupvalue',
           'debug.setfenv',
           'debug.sethook',
           'debug.setlocal',
           'debug.setmetatable',
           'debug.setupvalue',
           'debug.traceback'),
 'io': ('io.close',
        'io.flush',
        'io.input',
        'io.lines',
        'io.open',
        'io.output',
        'io.popen',
        'io.read',
        'io.tmpfile',
        'io.type',
        'io.write'),
 'math': ('math.abs',
          'math.acos',
          'math.asin',
          'math.atan2',
          'math.atan',
          'math.ceil',
          'math.cosh',
          'math.cos',
          'math.deg',
          'math.exp',
          'math.floor',
          'math.fmod',
          'math.frexp',
          'math.huge',
          'math.ldexp',
          'math.log10',
          'math.log',
          'math.max',
          'math.min',
          'math.modf',
          'math.pi',
          'math.pow',
          'math.rad',
          'math.random',
          'math.randomseed',
          'math.sinh',
          'math.sin',
          'math.sqrt',
          'math.tanh',
          'math.tan'),
 'modules': ('module',
             'require',
             'package.cpath',
             'package.loaded',
             'package.loadlib',
             'package.path',
             'package.preload',
             'package.seeall'),
 'os': ('os.clock',
        'os.date',
        'os.difftime',
        'os.execute',
        'os.exit',
        'os.getenv',
        'os.remove',
        'os.rename',
        'os.setlocale',
        'os.time',
        'os.tmpname'),
 'string': ('string.byte',
            'string.char',
            'string.dump',
            'string.find',
            'string.format',
            'string.gmatch',
            'string.gsub',
            'string.len',
            'string.lower',
            'string.match',
            'string.rep',
            'string.reverse',
            'string.sub',
            'string.upper'),
 'table': ('table.concat',
           'table.insert',
           'table.maxn',
           'table.remove',
           'table.sort')}


if __name__ == '__main__':  # pragma: no cover
    import re
    try:
        from urllib import urlopen
    except ImportError:
        from urllib.request import urlopen
    import pprint

    # you can't generally find out what module a function belongs to if you
    # have only its name. Because of this, here are some callback functions
    # that recognize if a gioven function belongs to a specific module
    def module_callbacks():
        def is_in_coroutine_module(name):
            return name.startswith('coroutine.')

        def is_in_modules_module(name):
            if name in ['require', 'module'] or name.startswith('package'):
                return True
            else:
                return False

        def is_in_string_module(name):
            return name.startswith('string.')

        def is_in_table_module(name):
            return name.startswith('table.')

        def is_in_math_module(name):
            return name.startswith('math')

        def is_in_io_module(name):
            return name.startswith('io.')

        def is_in_os_module(name):
            return name.startswith('os.')

        def is_in_debug_module(name):
            return name.startswith('debug.')

        return {'coroutine': is_in_coroutine_module,
                'modules': is_in_modules_module,
                'string': is_in_string_module,
                'table': is_in_table_module,
                'math': is_in_math_module,
                'io': is_in_io_module,
                'os': is_in_os_module,
                'debug': is_in_debug_module}



    def get_newest_version():
        f = urlopen('http://www.lua.org/manual/')
        r = re.compile(r'^<A HREF="(\d\.\d)/">Lua \1</A>')
        for line in f:
            m = r.match(line)
            if m is not None:
                return m.groups()[0]

    def get_lua_functions(version):
        f = urlopen('http://www.lua.org/manual/%s/' % version)
        r = re.compile(r'^<A HREF="manual.html#pdf-(.+)">\1</A>')
        functions = []
        for line in f:
            m = r.match(line)
            if m is not None:
                functions.append(m.groups()[0])
        return functions

    def get_function_module(name):
        for mod, cb in module_callbacks().items():
            if cb(name):
                return mod
        if '.' in name:
            return name.split('.')[0]
        else:
            return 'basic'

    def regenerate(filename, modules):
        with open(filename) as fp:
            content = fp.read()

        header = content[:content.find('MODULES = {')]
        footer = content[content.find("if __name__ == '__main__':"):]


        with open(filename, 'w') as fp:
            fp.write(header)
            fp.write('MODULES = %s\n\n' % pprint.pformat(modules))
            fp.write(footer)

    def run():
        version = get_newest_version()
        print('> Downloading function index for Lua %s' % version)
        functions = get_lua_functions(version)
        print('> %d functions found:' % len(functions))

        modules = {}
        for full_function_name in functions:
            print('>> %s' % full_function_name)
            m = get_function_module(full_function_name)
            modules.setdefault(m, []).append(full_function_name)

        regenerate(__file__, modules)

    run()
