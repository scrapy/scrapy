from __future__ import with_statement

import sys
import os
import optparse
import cProfile
import inspect

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.xlib import lsprofcalltree
from scrapy.conf import settings
from scrapy.command import ScrapyCommand
from scrapy.exceptions import UsageError, ScrapyDeprecationWarning
from scrapy.utils.misc import walk_modules
from scrapy.utils.project import inside_project

def _iter_command_classes(module_name):
    # TODO: add `name` attribute to commands and and merge this function with
    # scrapy.utils.spider.iter_spider_classes
    for module in walk_modules(module_name):
        for obj in vars(module).itervalues():
            if inspect.isclass(obj) and \
               issubclass(obj, ScrapyCommand) and \
               obj.__module__ == module.__name__:
                yield obj

def _get_commands_from_module(module, inproject):
    d = {}
    for cmd in _iter_command_classes(module):
        if inproject or not cmd.requires_project:
            cmdname = cmd.__module__.split('.')[-1]
            d[cmdname] = cmd()
    return d

def _get_commands_dict(inproject):
    cmds = _get_commands_from_module('scrapy.commands', inproject)
    cmds_module = settings['COMMANDS_MODULE']
    if cmds_module:
        cmds.update(_get_commands_from_module(cmds_module, inproject))
    return cmds

def _pop_command_name(argv):
    i = 0
    for arg in argv[1:]:
        if not arg.startswith('-'):
            del argv[i]
            return arg
        i += 1

def _print_header(inproject):
    if inproject:
        print "Scrapy %s - project: %s\n" % (scrapy.__version__, \
            settings['BOT_NAME'])
    else:
        print "Scrapy %s - no active project\n" % scrapy.__version__

def _print_commands(inproject):
    _print_header(inproject)
    print "Usage:"
    print "  scrapy <command> [options] [args]\n"
    print "Available commands:"
    cmds = _get_commands_dict(inproject)
    for cmdname, cmdclass in sorted(cmds.iteritems()):
        print "  %-13s %s" % (cmdname, cmdclass.short_desc())
    print
    print 'Use "scrapy <command> -h" to see more info about a command'

def _print_unknown_command(cmdname, inproject):
    _print_header(inproject)
    print "Unknown command: %s\n" % cmdname
    print 'Use "scrapy" to see available commands' 
    if not inproject:
        print
        print "More commands are available in project mode"

def _check_deprecated_scrapy_ctl(argv, inproject):
    """Check if Scrapy was called using the deprecated scrapy-ctl command and
    warn in that case, also creating a scrapy.cfg if it doesn't exist.
    """
    if not any('scrapy-ctl' in x for x in argv):
        return
    import warnings
    warnings.warn("`scrapy-ctl.py` command-line tool is deprecated and will be removed in Scrapy 0.11, use `scrapy` instead",
        ScrapyDeprecationWarning, stacklevel=3)
    if inproject:
        projpath = os.path.abspath(os.path.dirname(os.path.dirname(settings.settings_module.__file__)))
        cfg_path = os.path.join(projpath, 'scrapy.cfg')
        if not os.path.exists(cfg_path):
            with open(cfg_path, 'w') as f:
                f.write("# generated automatically - feel free to edit" + os.linesep)
                f.write("[settings]" + os.linesep)
                f.write("default = %s" % settings.settings_module.__name__ + os.linesep)

def _run_print_help(parser, func, *a, **kw):
    try:
        func(*a, **kw)
    except UsageError, e:
        if str(e):
            parser.error(str(e))
        if e.print_help:
            parser.print_help()
        sys.exit(2)

def execute(argv=None):
    if argv is None:
        argv = sys.argv
    crawler = CrawlerProcess(settings)
    crawler.install()
    inproject = inside_project()
    _check_deprecated_scrapy_ctl(argv, inproject) # TODO: remove for Scrapy 0.11
    cmds = _get_commands_dict(inproject)
    cmdname = _pop_command_name(argv)
    parser = optparse.OptionParser(formatter=optparse.TitledHelpFormatter(), \
        conflict_handler='resolve')
    if not cmdname:
        _print_commands(inproject)
        sys.exit(0)
    elif cmdname not in cmds:
        _print_unknown_command(cmdname, inproject)
        sys.exit(2)

    cmd = cmds[cmdname]
    parser.usage = "scrapy %s %s" % (cmdname, cmd.syntax())
    parser.description = cmd.long_desc()
    settings.defaults.update(cmd.default_settings)
    cmd.settings = settings
    cmd.add_options(parser)
    opts, args = parser.parse_args(args=argv[1:])
    _run_print_help(parser, cmd.process_options, args, opts)
    cmd.set_crawler(crawler)
    _run_print_help(parser, _run_command, cmd, args, opts)
    sys.exit(cmd.exitcode)

def _run_command(cmd, args, opts):
    if opts.profile or opts.lsprof:
        _run_command_profiled(cmd, args, opts)
    else:
        cmd.run(args, opts)

def _run_command_profiled(cmd, args, opts):
    if opts.profile:
        sys.stderr.write("scrapy: writing cProfile stats to %r\n" % opts.profile)
    if opts.lsprof:
        sys.stderr.write("scrapy: writing lsprof stats to %r\n" % opts.lsprof)
    loc = locals()
    p = cProfile.Profile()
    p.runctx('cmd.run(args, opts)', globals(), loc)
    if opts.profile:
        p.dump_stats(opts.profile)
    k = lsprofcalltree.KCacheGrind(p)
    if opts.lsprof:
        with open(opts.lsprof, 'w') as f:
            k.output(f)

if __name__ == '__main__':
    execute()
