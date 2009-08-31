from __future__ import with_statement

import sys
import os
import optparse
import cProfile

import scrapy
from scrapy import log
from scrapy.spider import spiders
from scrapy.xlib import lsprofcalltree
from scrapy.conf import settings
from scrapy.command.models import ScrapyCommand

# This dict holds information about the executed command for later use
command_executed = {}

def _save_command_executed(cmdname, cmd, args, opts):
    """Save command executed info for later reference"""
    command_executed['name'] = cmdname
    command_executed['class'] = cmd
    command_executed['args'] = args[:]
    command_executed['opts'] = opts.__dict__.copy()

def _find_commands(dir):
    try:
        return [f[:-3] for f in os.listdir(dir) if not f.startswith('_') and \
            f.endswith('.py')]
    except OSError:
        return []

def _get_commands_from_module(module):
    d = {}
    mod = __import__(module, {}, {}, [''])
    for cmdname in _find_commands(mod.__path__[0]):
        modname = '%s.%s' % (module, cmdname)
        command = getattr(__import__(modname, {}, {}, [cmdname]), 'Command', None)
        if callable(command):
            d[cmdname] = command()
        else:
            print 'WARNING: Module %r does not define a Command class' % modname
    return d

def _get_commands_dict():
    cmds = _get_commands_from_module('scrapy.command.commands')
    cmds_module = settings['COMMANDS_MODULE']
    if cmds_module:
        cmds.update(_get_commands_from_module(cmds_module))
    return cmds

def _get_command_name(argv):
    for arg in argv[1:]:
        if not arg.startswith('-'):
            return arg

def _print_usage(inside_project):
    if inside_project:
        print "Scrapy %s - project: %s\n" % (scrapy.__version__, \
            settings['BOT_NAME'])
    else:
        print "Scrapy %s - no active project\n" % scrapy.__version__
    print "Usage"
    print "=====\n"
    print "To run a command:"
    print "  scrapy-ctl.py <command> [options] [args]\n"
    print "To get help:"
    print "  scrapy-ctl.py <command> -h\n"
    print "Available commands"
    print "==================\n"
    cmds = _get_commands_dict()
    for cmdname, cmdclass in sorted(cmds.iteritems()):
        if inside_project or not cmdclass.requires_project:
            print "%s %s" % (cmdname, cmdclass.syntax())
            print "  %s" % cmdclass.short_desc()
    print

def _update_default_settings(module, cmdname):
    if not module:
        return
    try:
        mod = __import__('%s.%s' % (module, cmdname), {}, {}, [''])
    except ImportError:
        return
    settingsdict = vars(mod)
    for k, v in settingsdict.iteritems():
        if not k.startswith("_"):
            settings.defaults[k] = v

def execute(argv=None):
    if argv is None:
        argv = sys.argv

    cmds = _get_commands_dict()

    cmdname = _get_command_name(argv)
    _update_default_settings('scrapy.conf.commands', cmdname)
    _update_default_settings(settings['COMMANDS_SETTINGS_MODULE'], cmdname)

    parser = optparse.OptionParser(formatter=optparse.TitledHelpFormatter(), \
        conflict_handler='resolve', add_help_option=False)

    if cmdname in cmds:
        cmd = cmds[cmdname]
        cmd.add_options(parser)
        opts, args = parser.parse_args(args=argv[1:])
        cmd.process_options(args, opts)
        parser.usage = "%%prog %s %s" % (cmdname, cmd.syntax())
        parser.description = cmd.long_desc()
        if cmd.requires_project and not settings.settings_module:
            print "Error running: scrapy-ctl.py %s\n" % cmdname
            print "Cannot find project settings module in python path: %s" % \
                settings.settings_module_path
            sys.exit(1)
        if opts.help:
            parser.print_help()
            sys.exit()
    elif not cmdname:
        cmd = ScrapyCommand()
        cmd.add_options(parser)
        opts, args = parser.parse_args(args=argv)
        cmd.process_options(args, opts)
        _print_usage(settings.settings_module)
        sys.exit(2)
    else:
        print "Unknown command: %s\n" % cmdname
        print 'Use "scrapy-ctl.py -h" for help' 
        sys.exit(2)

    del args[0]  # remove command name from args
    _save_command_executed(cmdname, cmd, args, opts)
    from scrapy.core.manager import scrapymanager
    scrapymanager.configure()
    ret = _run_command(cmd, args, opts)
    if ret is False:
        parser.print_help()

def _run_command(cmd, args, opts):
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
    return ret

if __name__ == '__main__':
    execute()
