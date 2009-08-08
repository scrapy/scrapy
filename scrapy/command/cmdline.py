from __future__ import with_statement

import sys
import os
import optparse
import cProfile

import scrapy
from scrapy import log
from scrapy.spider import spiders
from scrapy.xlib import lsprofcalltree
from scrapy.conf import settings, SETTINGS_MODULE

def find_commands(dir):
    try:
        return [f[:-3] for f in os.listdir(dir) if not f.startswith('_') and f.endswith('.py')]
    except OSError:
        return []

def builtin_commands_dict():
    d = {}
    scrapy_dir = scrapy.__path__[0]
    commands_dir = os.path.join(scrapy_dir, 'command', 'commands')
    for cmdname in find_commands(commands_dir):
        modname = 'scrapy.command.commands.%s' % cmdname
        command = getattr(__import__(modname, {}, {}, [cmdname]), 'Command', None)
        if callable(command):
            d[cmdname] = command()
        else:
            print 'WARNING: Builtin command module %s exists but Command class not found' % modname
    return d

def custom_commands_dict():
    d = {}
    cmdsmod = settings['COMMANDS_MODULE']
    if cmdsmod:
        mod = __import__(cmdsmod, {}, {}, [''])
        for cmdname in find_commands(mod.__path__[0]):
            modname = '%s.%s' % (cmdsmod, cmdname)
            command = getattr(__import__(modname, {}, {}, [cmdname]), 'Command', None)
            if callable(command):
                d[cmdname] = command()
            else:
                print 'WARNING: Custom command module %s exists but Command class not found' % modname
    return d

def getcmdname(argv):
    for arg in argv[1:]:
        if not arg.startswith('-'):
            return arg

def usage(prog):
    s = "Usage\n"
    s += "=====\n"
    s += "%s <command> [options] [args]\n" % prog
    s += "  Run a command\n\n"
    s += "%s <command> -h\n" % prog
    s += "  Print command help and options\n\n"
    s += "Available commands\n"
    s += "===================\n"

    cmds = builtin_commands_dict()
    cmds.update(custom_commands_dict())

    for cmdname, cmdclass in sorted(cmds.iteritems()):
        s += "%s %s\n" % (cmdname, cmdclass.syntax())
        s += "  %s\n" % cmdclass.short_desc()

    return s


def update_defaults(defaults, module):
    settingsdict = vars(module)
    for k, v in settingsdict.iteritems():
        if not k.startswith("_"):
            defaults[k] = v

def command_settings(cmdname):
    try:
        module = __import__('%s.%s' % ('scrapy.conf.commands', cmdname), {}, {}, [''])
        update_defaults(settings.defaults, module)
    except ImportError:
        pass

    basepath = settings['COMMANDS_SETTINGS_MODULE']
    if basepath:
        try:
            module = __import__('%s.%s' % (basepath, cmdname), {}, {}, [''])
            update_defaults(settings.defaults, module)
        except ImportError:
            pass

# This dict holds information about the executed command for later use
command_executed = {}

def execute():
    if not settings.settings_module:
        print "Scrapy %s\n" % scrapy.__version__
        print "Error: Cannot find %r module in python path." % SETTINGS_MODULE
        sys.exit(1)
    execute_with_args(sys.argv)

def execute_with_args(argv):
    cmds = builtin_commands_dict()
    cmds.update(custom_commands_dict())

    cmdname = getcmdname(argv)
    command_settings(cmdname)

    if not cmdname:
        print "Scrapy %s\n" % scrapy.__version__
        print usage(argv[0])
        sys.exit(2)

    parser = optparse.OptionParser(formatter=optparse.TitledHelpFormatter(), \
        conflict_handler='resolve', add_help_option=False)

    if cmdname in cmds:
        cmd = cmds[cmdname]
        cmd.add_options(parser)
        parser.usage = "%%prog %s %s" % (cmdname, cmd.syntax())
        parser.description = cmd.long_desc()
    else:
        print "Scrapy %s\n" % scrapy.__version__
        print "Unknown command: %s\n" % cmdname
        print 'Type "%s -h" for help' % argv[0]
        sys.exit(2)

    (opts, args) = parser.parse_args(args=argv[1:])
    del args[0]  # args[0] is cmdname

    if opts.help:
        parser.print_help()
        sys.exit()

    # storing command executed info for later reference
    command_executed['name'] = cmdname
    command_executed['class'] = cmd
    command_executed['args'] = args[:]
    command_executed['opts'] = opts.__dict__.copy()

    cmd.process_options(args, opts)
    spiders.load()
    log.start()
    if opts.profile or opts.lsprof:
        if opts.profile:
            log.msg("writing cProfile stats to %r" % opts.profile)
        if opts.lsprof:
            log.msg("writing lsprof stats to %r" % opts.lsprof)
        loc = locals()
        p = cProfile.Profile()
        p.runctx('ret = cmd.run(args, opts)', globals(), loc)
        if opts.profile:
            p.dump_stats(opts.profile)
        k = lsprofcalltree.KCacheGrind(p)
        if opts.lsprof:
            with open(opts.lsprof, 'w') as f:
                k.output(f)
        ret = loc['ret']
    else:
        ret = cmd.run(args, opts)
    if ret is False:
        parser.print_help()
