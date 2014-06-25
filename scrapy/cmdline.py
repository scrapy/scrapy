from __future__ import print_function
import sys
import optparse
import cProfile
import inspect
import pkg_resources

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.xlib import lsprofcalltree
from scrapy.command import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.misc import walk_modules
from scrapy.utils.project import inside_project, get_project_settings
from scrapy.settings.deprecated import check_deprecated_settings

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

def _get_commands_from_entry_points(inproject, group='scrapy.commands'):
    cmds = {}
    for entry_point in pkg_resources.iter_entry_points(group):
        obj = entry_point.load()
        if inspect.isclass(obj):
            cmds[entry_point.name] = obj()
        else:
            raise Exception("Invalid entry point %s" % entry_point.name)
    return cmds

def _get_commands_dict(settings, inproject):
    cmds = _get_commands_from_module('scrapy.commands', inproject)
    cmds.update(_get_commands_from_entry_points(inproject))
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

def _print_header(settings, inproject):
    if inproject:
        print("Scrapy %s - project: %s\n" % (scrapy.__version__, \
            settings['BOT_NAME']))
    else:
        print("Scrapy %s - no active project\n" % scrapy.__version__)

def _print_commands(settings, inproject):
    _print_header(settings, inproject)
    print("Usage:")
    print("  scrapy <command> [options] [args]\n")
    print("Available commands:")
    cmds = _get_commands_dict(settings, inproject)
    for cmdname, cmdclass in sorted(cmds.iteritems()):
        print("  %-13s %s" % (cmdname, cmdclass.short_desc()))
    if not inproject:
        print()
        print("  [ more ]      More commands available when run from project directory")
    print()
    print('Use "scrapy <command> -h" to see more info about a command')

def _print_unknown_command(settings, cmdname, inproject):
    _print_header(settings, inproject)
    print("Unknown command: %s\n" % cmdname)
    print('Use "scrapy" to see available commands')

def _run_print_help(parser, func, *a, **kw):
    try:
        func(*a, **kw)
    except UsageError as e:
        if str(e):
            parser.error(str(e))
        if e.print_help:
            parser.print_help()
        sys.exit(2)

def execute(argv=None, settings=None):
    if argv is None:
        argv = sys.argv

    # --- backwards compatibility for scrapy.conf.settings singleton ---
    if settings is None and 'scrapy.conf' in sys.modules:
        from scrapy import conf
        if hasattr(conf, 'settings'):
            settings = conf.settings
    # ------------------------------------------------------------------

    if settings is None:
        settings = get_project_settings()
    check_deprecated_settings(settings)

    # --- backwards compatibility for scrapy.conf.settings singleton ---
    import warnings
    from scrapy.exceptions import ScrapyDeprecationWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ScrapyDeprecationWarning)
        from scrapy import conf
        conf.settings = settings
    # ------------------------------------------------------------------

    inproject = inside_project()
    cmds = _get_commands_dict(settings, inproject)
    cmdname = _pop_command_name(argv)
    parser = optparse.OptionParser(formatter=optparse.TitledHelpFormatter(), \
        conflict_handler='resolve')
    if not cmdname:
        _print_commands(settings, inproject)
        sys.exit(0)
    elif cmdname not in cmds:
        _print_unknown_command(settings, cmdname, inproject)
        sys.exit(2)

    cmd = cmds[cmdname]
    parser.usage = "scrapy %s %s" % (cmdname, cmd.syntax())
    parser.description = cmd.long_desc()
    settings.setdict(cmd.default_settings, priority='command')
    cmd.settings = settings
    cmd.add_options(parser)
    opts, args = parser.parse_args(args=argv[1:])
    _run_print_help(parser, cmd.process_options, args, opts)

    cmd.crawler_process = CrawlerProcess(settings)
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
