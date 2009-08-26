import textwrap

from scrapy.command import ScrapyCommand, cmdline

class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "<command>"
    
    def short_desc(self):
        return "Provides extended help for the given command"

    def run(self, args, opts):
        if not args:
            return False

        commands = cmdline.get_commands_dict()

        cmdname = args[0]
        if cmdname in commands:
            cmd = commands[cmdname]
            help = getattr(cmd, 'help', None) or getattr(cmd, 'long_desc', None)
            title = "%s command" % cmdname
            print title
            print "-" * len(title)
            print
            print cmd.short_desc()
            print
            print "usage: %s %s" % (cmdname, cmd.syntax())
            print
            print "\n".join(textwrap.wrap(help()))
            print
            print "For a list of supported arguments use:"
            print
            print "   scrapy-ctl.py %s -h" % cmdname
            print
        else:
            print "Unknown command: %s" % cmdname
