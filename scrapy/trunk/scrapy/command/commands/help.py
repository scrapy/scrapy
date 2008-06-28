from scrapy.command import ScrapyCommand, cmdline

class Command(ScrapyCommand):
    def syntax(self):
        return "<command>"
    
    def short_desc(self):
        return "Provides extended help for the given command"

    def run(self, args, opts):
        if not args:
            return False

        commands = cmdline.builtin_commands_dict()
        commands.update(cmdline.custom_commands_dict())

        cmdname = args[0]
        if cmdname in commands:
            cmd = commands[cmdname]
            help = getattr(cmd, 'help', None) or getattr(cmd, 'long_desc', None)
            print "%s: %s" % (cmdname, cmd.short_desc())
            print "usage: %s %s" % (cmdname, cmd.syntax())
            print
            print help()
        else:
            print "Unknown command: %s" % cmdname
