# -*- test-case-name: twisted.test.test_usage -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
twisted.python.usage is a module for parsing/handling the
command line of your program.

For information on how to use it, see
U{http://twistedmatrix.com/projects/core/documentation/howto/options.html},
or doc/core/howto/options.xhtml in your Twisted directory.
"""


import getopt

# System Imports
import inspect
import os
import sys
import textwrap
from os import path
from typing import Optional, cast

# Sibling Imports
from twisted.python import reflect, util


class UsageError(Exception):
    pass


error = UsageError


class CoerceParameter:
    """
    Utility class that can corce a parameter before storing it.
    """

    def __init__(self, options, coerce):
        """
        @param options: parent Options object
        @param coerce: callable used to coerce the value.
        """
        self.options = options
        self.coerce = coerce
        self.doc = getattr(self.coerce, "coerceDoc", "")

    def dispatch(self, parameterName, value):
        """
        When called in dispatch, do the coerce for C{value} and save the
        returned value.
        """
        if value is None:
            raise UsageError(f"Parameter '{parameterName}' requires an argument.")
        try:
            value = self.coerce(value)
        except ValueError as e:
            raise UsageError(f"Parameter type enforcement failed: {e}")

        self.options.opts[parameterName] = value


class Options(dict):
    """
    An option list parser class

    C{optFlags} and C{optParameters} are lists of available parameters
    which your program can handle. The difference between the two
    is the 'flags' have an on(1) or off(0) state (off by default)
    whereas 'parameters' have an assigned value, with an optional
    default. (Compare '--verbose' and '--verbosity=2')

    optFlags is assigned a list of lists. Each list represents
    a flag parameter, as so::

       optFlags = [['verbose', 'v', 'Makes it tell you what it doing.'],
                   ['quiet', 'q', 'Be vewy vewy quiet.']]

    As you can see, the first item is the long option name
    (prefixed with '--' on the command line), followed by the
    short option name (prefixed with '-'), and the description.
    The description is used for the built-in handling of the
    --help switch, which prints a usage summary.

    C{optParameters} is much the same, except the list also contains
    a default value::

       optParameters = [['outfile', 'O', 'outfile.log', 'Description...']]

    A coerce function can also be specified as the last element: it will be
    called with the argument and should return the value that will be stored
    for the option. This function can have a C{coerceDoc} attribute which
    will be appended to the documentation of the option.

    subCommands is a list of 4-tuples of (command name, command shortcut,
    parser class, documentation).  If the first non-option argument found is
    one of the given command names, an instance of the given parser class is
    instantiated and given the remainder of the arguments to parse and
    self.opts[command] is set to the command name.  For example::

       subCommands = [
            ['inquisition', 'inquest', InquisitionOptions,
                 'Perform an inquisition'],
            ['holyquest', 'quest', HolyQuestOptions,
                 'Embark upon a holy quest']
        ]

    In this case, C{"<program> holyquest --horseback --for-grail"} will cause
    C{HolyQuestOptions} to be instantiated and asked to parse
    C{['--horseback', '--for-grail']}.  Currently, only the first sub-command
    is parsed, and all options following it are passed to its parser.  If a
    subcommand is found, the subCommand attribute is set to its name and the
    subOptions attribute is set to the Option instance that parses the
    remaining options. If a subcommand is not given to parseOptions,
    the subCommand attribute will be None. You can also mark one of
    the subCommands to be the default::

       defaultSubCommand = 'holyquest'

    In this case, the subCommand attribute will never be None, and
    the subOptions attribute will always be set.

    If you want to handle your own options, define a method named
    C{opt_paramname} that takes C{(self, option)} as arguments. C{option}
    will be whatever immediately follows the parameter on the
    command line. Options fully supports the mapping interface, so you
    can do things like C{'self["option"] = val'} in these methods.

    Shell tab-completion is supported by this class, for zsh only at present.
    Zsh ships with a stub file ("completion function") which, for Twisted
    commands, performs tab-completion on-the-fly using the support provided
    by this class. The stub file lives in our tree at
    C{twisted/python/twisted-completion.zsh}, and in the Zsh tree at
    C{Completion/Unix/Command/_twisted}.

    Tab-completion is based upon the contents of the optFlags and optParameters
    lists. And, optionally, additional metadata may be provided by assigning a
    special attribute, C{compData}, which should be an instance of
    C{Completions}. See that class for details of what can and should be
    included - and see the howto for additional help using these features -
    including how third-parties may take advantage of tab-completion for their
    own commands.

    Advanced functionality is covered in the howto documentation,
    available at
    U{http://twistedmatrix.com/projects/core/documentation/howto/options.html},
    or doc/core/howto/options.xhtml in your Twisted directory.
    """

    subCommand: Optional[str] = None
    defaultSubCommand: Optional[str] = None
    parent: "Optional[Options]" = None
    completionData = None
    _shellCompFile = sys.stdout  # file to use if shell completion is requested

    def __init__(self):
        super().__init__()

        self.opts = self
        self.defaults = {}

        # These are strings/lists we will pass to getopt
        self.longOpt = []
        self.shortOpt = ""
        self.docs = {}
        self.synonyms = {}
        self._dispatch = {}

        collectors = [
            self._gather_flags,
            self._gather_parameters,
            self._gather_handlers,
        ]

        for c in collectors:
            (longOpt, shortOpt, docs, settings, synonyms, dispatch) = c()
            self.longOpt.extend(longOpt)
            self.shortOpt = self.shortOpt + shortOpt
            self.docs.update(docs)

            self.opts.update(settings)
            self.defaults.update(settings)

            self.synonyms.update(synonyms)
            self._dispatch.update(dispatch)

    # class Options derives from dict, which defines __hash__ as None,
    # but we need to set __hash__ to object.__hash__ which is of type
    # Callable[[object], int].  So we need to ignore mypy error here.
    __hash__ = object.__hash__  # type: ignore[assignment]

    def opt_help(self):
        """
        Display this help and exit.
        """
        print(self.__str__())
        sys.exit(0)

    def opt_version(self):
        """
        Display Twisted version and exit.
        """
        from twisted import copyright

        print("Twisted version:", copyright.version)
        sys.exit(0)

    # opt_h = opt_help # this conflicted with existing 'host' options.

    def parseOptions(self, options=None):
        """
        The guts of the command-line parser.
        """

        if options is None:
            options = sys.argv[1:]

        # we really do need to place the shell completion check here, because
        # if we used an opt_shell_completion method then it would be possible
        # for other opt_* methods to be run first, and they could possibly
        # raise validation errors which would result in error output on the
        # terminal of the user performing shell completion. Validation errors
        # would occur quite frequently, in fact, because users often initiate
        # tab-completion while they are editing an unfinished command-line.
        if len(options) > 1 and options[-2] == "--_shell-completion":
            from twisted.python import _shellcomp

            cmdName = path.basename(sys.argv[0])
            _shellcomp.shellComplete(self, cmdName, options, self._shellCompFile)
            sys.exit(0)

        try:
            opts, args = getopt.getopt(options, self.shortOpt, self.longOpt)
        except getopt.error as e:
            raise UsageError(str(e))

        for opt, arg in opts:
            if opt[1] == "-":
                opt = opt[2:]
            else:
                opt = opt[1:]

            optMangled = opt
            if optMangled not in self.synonyms:
                optMangled = opt.replace("-", "_")
                if optMangled not in self.synonyms:
                    raise UsageError(f"No such option '{opt}'")

            optMangled = self.synonyms[optMangled]
            if isinstance(self._dispatch[optMangled], CoerceParameter):
                self._dispatch[optMangled].dispatch(optMangled, arg)
            else:
                self._dispatch[optMangled](optMangled, arg)

        if getattr(self, "subCommands", None) and (
            args or self.defaultSubCommand is not None
        ):
            if not args:
                args = [self.defaultSubCommand]
            sub, rest = args[0], args[1:]
            for (cmd, short, parser, doc) in self.subCommands:
                if sub == cmd or sub == short:
                    self.subCommand = cmd
                    self.subOptions = parser()
                    self.subOptions.parent = self
                    self.subOptions.parseOptions(rest)
                    break
            else:
                raise UsageError("Unknown command: %s" % sub)
        else:
            try:
                self.parseArgs(*args)
            except TypeError:
                raise UsageError("Wrong number of arguments.")

        self.postOptions()

    def postOptions(self):
        """
        I am called after the options are parsed.

        Override this method in your subclass to do something after
        the options have been parsed and assigned, like validate that
        all options are sane.
        """

    def parseArgs(self):
        """
        I am called with any leftover arguments which were not options.

        Override me to do something with the remaining arguments on
        the command line, those which were not flags or options. e.g.
        interpret them as a list of files to operate on.

        Note that if there more arguments on the command line
        than this method accepts, parseArgs will blow up with
        a getopt.error.  This means if you don't override me,
        parseArgs will blow up if I am passed any arguments at
        all!
        """

    def _generic_flag(self, flagName, value=None):
        if value not in ("", None):
            raise UsageError(
                "Flag '%s' takes no argument." ' Not even "%s".' % (flagName, value)
            )

        self.opts[flagName] = 1

    def _gather_flags(self):
        """
        Gather up boolean (flag) options.
        """

        longOpt, shortOpt = [], ""
        docs, settings, synonyms, dispatch = {}, {}, {}, {}

        flags = []
        reflect.accumulateClassList(self.__class__, "optFlags", flags)

        for flag in flags:
            long, short, doc = util.padTo(3, flag)
            if not long:
                raise ValueError("A flag cannot be without a name.")

            docs[long] = doc
            settings[long] = 0
            if short:
                shortOpt = shortOpt + short
                synonyms[short] = long
            longOpt.append(long)
            synonyms[long] = long
            dispatch[long] = self._generic_flag

        return longOpt, shortOpt, docs, settings, synonyms, dispatch

    def _gather_parameters(self):
        """
        Gather options which take a value.
        """
        longOpt, shortOpt = [], ""
        docs, settings, synonyms, dispatch = {}, {}, {}, {}

        parameters = []

        reflect.accumulateClassList(self.__class__, "optParameters", parameters)

        synonyms = {}

        for parameter in parameters:
            long, short, default, doc, paramType = util.padTo(5, parameter)
            if not long:
                raise ValueError("A parameter cannot be without a name.")

            docs[long] = doc
            settings[long] = default
            if short:
                shortOpt = shortOpt + short + ":"
                synonyms[short] = long
            longOpt.append(long + "=")
            synonyms[long] = long
            if paramType is not None:
                dispatch[long] = CoerceParameter(self, paramType)
            else:
                dispatch[long] = CoerceParameter(self, str)

        return longOpt, shortOpt, docs, settings, synonyms, dispatch

    def _gather_handlers(self):
        """
        Gather up options with their own handler methods.

        This returns a tuple of many values.  Amongst those values is a
        synonyms dictionary, mapping all of the possible aliases (C{str})
        for an option to the longest spelling of that option's name
        C({str}).

        Another element is a dispatch dictionary, mapping each user-facing
        option name (with - substituted for _) to a callable to handle that
        option.
        """

        longOpt, shortOpt = [], ""
        docs, settings, synonyms, dispatch = {}, {}, {}, {}

        dct = {}
        reflect.addMethodNamesToDict(self.__class__, dct, "opt_")

        for name in dct.keys():
            method = getattr(self, "opt_" + name)

            takesArg = not flagFunction(method, name)

            prettyName = name.replace("_", "-")
            doc = getattr(method, "__doc__", None)
            if doc:
                ## Only use the first line.
                # docs[name] = doc.split('\n')[0]
                docs[prettyName] = doc
            else:
                docs[prettyName] = self.docs.get(prettyName)

            synonyms[prettyName] = prettyName

            # A little slight-of-hand here makes dispatching much easier
            # in parseOptions, as it makes all option-methods have the
            # same signature.
            if takesArg:
                fn = lambda name, value, m=method: m(value)
            else:
                # XXX: This won't raise a TypeError if it's called
                # with a value when it shouldn't be.
                fn = lambda name, value=None, m=method: m()

            dispatch[prettyName] = fn

            if len(name) == 1:
                shortOpt = shortOpt + name
                if takesArg:
                    shortOpt = shortOpt + ":"
            else:
                if takesArg:
                    prettyName = prettyName + "="
                longOpt.append(prettyName)

        reverse_dct = {}
        # Map synonyms
        for name in dct.keys():
            method = getattr(self, "opt_" + name)
            if method not in reverse_dct:
                reverse_dct[method] = []
            reverse_dct[method].append(name.replace("_", "-"))

        for method, names in reverse_dct.items():
            if len(names) < 2:
                continue
            longest = max(names, key=len)
            for name in names:
                synonyms[name] = longest

        return longOpt, shortOpt, docs, settings, synonyms, dispatch

    def __str__(self) -> str:
        return self.getSynopsis() + "\n" + self.getUsage(width=None)

    def getSynopsis(self) -> str:
        """
        Returns a string containing a description of these options and how to
        pass them to the executed file.
        """
        executableName = reflect.filenameToModuleName(sys.argv[0])

        if executableName.endswith(".__main__"):
            executableName = "{} -m {}".format(
                os.path.basename(sys.executable),
                executableName.replace(".__main__", ""),
            )

        if self.parent is None:
            default = "Usage: {}{}".format(
                executableName,
                (self.longOpt and " [options]") or "",
            )
        else:
            default = "%s" % ((self.longOpt and "[options]") or "")
        synopsis = cast(str, getattr(self, "synopsis", default))

        synopsis = synopsis.rstrip()

        if self.parent is not None:
            assert self.parent.subCommand is not None
            synopsis = " ".join(
                (self.parent.getSynopsis(), self.parent.subCommand, synopsis)
            )
        return synopsis

    def getUsage(self, width: Optional[int] = None) -> str:
        # If subOptions exists by now, then there was probably an error while
        # parsing its options.
        if hasattr(self, "subOptions"):
            return cast(Options, self.subOptions).getUsage(width=width)

        if not width:
            width = int(os.environ.get("COLUMNS", "80"))

        if hasattr(self, "subCommands"):
            cmdDicts = []
            for (cmd, short, parser, desc) in self.subCommands:  # type: ignore[attr-defined]
                cmdDicts.append(
                    {
                        "long": cmd,
                        "short": short,
                        "doc": desc,
                        "optType": "command",
                        "default": None,
                    }
                )
            chunks = docMakeChunks(cmdDicts, width)
            commands = "Commands:\n" + "".join(chunks)
        else:
            commands = ""

        longToShort = {}
        for key, value in self.synonyms.items():
            longname = value
            if (key != longname) and (len(key) == 1):
                longToShort[longname] = key
            else:
                if longname not in longToShort:
                    longToShort[longname] = None
                else:
                    pass

        optDicts = []
        for opt in self.longOpt:
            if opt[-1] == "=":
                optType = "parameter"
                opt = opt[:-1]
            else:
                optType = "flag"

            optDicts.append(
                {
                    "long": opt,
                    "short": longToShort[opt],
                    "doc": self.docs[opt],
                    "optType": optType,
                    "default": self.defaults.get(opt, None),
                    "dispatch": self._dispatch.get(opt, None),
                }
            )

        if not (getattr(self, "longdesc", None) is None):
            longdesc = cast(str, self.longdesc)  # type: ignore[attr-defined]
        else:
            import __main__

            if getattr(__main__, "__doc__", None):
                longdesc = __main__.__doc__
            else:
                longdesc = ""

        if longdesc:
            longdesc = "\n" + "\n".join(textwrap.wrap(longdesc, width)).strip() + "\n"

        if optDicts:
            chunks = docMakeChunks(optDicts, width)
            s = "Options:\n%s" % ("".join(chunks))
        else:
            s = "Options: None\n"

        return s + longdesc + commands


_ZSH = "zsh"
_BASH = "bash"


class Completer:
    """
    A completion "action" - provides completion possibilities for a particular
    command-line option. For example we might provide the user a fixed list of
    choices, or files/dirs according to a glob.

    This class produces no completion matches itself - see the various
    subclasses for specific completion functionality.
    """

    _descr: Optional[str] = None

    def __init__(self, descr=None, repeat=False):
        """
        @type descr: C{str}
        @param descr: An optional descriptive string displayed above matches.

        @type repeat: C{bool}
        @param repeat: A flag, defaulting to False, indicating whether this
            C{Completer} should repeat - that is, be used to complete more
            than one command-line word. This may ONLY be set to True for
            actions in the C{extraActions} keyword argument to C{Completions}.
            And ONLY if it is the LAST (or only) action in the C{extraActions}
            list.
        """
        if descr is not None:
            self._descr = descr
        self._repeat = repeat

    @property
    def _repeatFlag(self):
        if self._repeat:
            return "*"
        else:
            return ""

    def _description(self, optName):
        if self._descr is not None:
            return self._descr
        else:
            return optName

    def _shellCode(self, optName, shellType):
        """
        Fetch a fragment of shell code representing this action which is
        suitable for use by the completion system in _shellcomp.py

        @type optName: C{str}
        @param optName: The long name of the option this action is being
            used for.

        @type shellType: C{str}
        @param shellType: One of the supported shell constants e.g.
            C{twisted.python.usage._ZSH}
        """
        if shellType == _ZSH:
            return f"{self._repeatFlag}:{self._description(optName)}:"
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteFiles(Completer):
    """
    Completes file names based on a glob pattern
    """

    def __init__(self, globPattern="*", **kw):
        Completer.__init__(self, **kw)
        self._globPattern = globPattern

    def _description(self, optName):
        if self._descr is not None:
            return f"{self._descr} ({self._globPattern})"
        else:
            return f"{optName} ({self._globPattern})"

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return '{}:{}:_files -g "{}"'.format(
                self._repeatFlag,
                self._description(optName),
                self._globPattern,
            )
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteDirs(Completer):
    """
    Completes directory names
    """

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return "{}:{}:_directories".format(
                self._repeatFlag, self._description(optName)
            )
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteList(Completer):
    """
    Completes based on a fixed list of words
    """

    def __init__(self, items, **kw):
        Completer.__init__(self, **kw)
        self._items = items

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return "{}:{}:({})".format(
                self._repeatFlag,
                self._description(optName),
                " ".join(
                    self._items,
                ),
            )
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteMultiList(Completer):
    """
    Completes multiple comma-separated items based on a fixed list of words
    """

    def __init__(self, items, **kw):
        Completer.__init__(self, **kw)
        self._items = items

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return "{}:{}:_values -s , '{}' {}".format(
                self._repeatFlag,
                self._description(optName),
                self._description(optName),
                " ".join(self._items),
            )
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteUsernames(Completer):
    """
    Complete usernames
    """

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return f"{self._repeatFlag}:{self._description(optName)}:_users"
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteGroups(Completer):
    """
    Complete system group names
    """

    _descr = "group"

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return f"{self._repeatFlag}:{self._description(optName)}:_groups"
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteHostnames(Completer):
    """
    Complete hostnames
    """

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return f"{self._repeatFlag}:{self._description(optName)}:_hosts"
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteUserAtHost(Completer):
    """
    A completion action which produces matches in any of these forms::
        <username>
        <hostname>
        <username>@<hostname>
    """

    _descr = "host | user@host"

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            # Yes this looks insane but it does work. For bonus points
            # add code to grep 'Hostname' lines from ~/.ssh/config
            return (
                '%s:%s:{_ssh;if compset -P "*@"; '
                'then _wanted hosts expl "remote host name" _ssh_hosts '
                '&& ret=0 elif compset -S "@*"; then _wanted users '
                'expl "login name" _ssh_users -S "" && ret=0 '
                "else if (( $+opt_args[-l] )); then tmp=() "
                'else tmp=( "users:login name:_ssh_users -qS@" ) fi; '
                '_alternative "hosts:remote host name:_ssh_hosts" "$tmp[@]"'
                " && ret=0 fi}" % (self._repeatFlag, self._description(optName))
            )
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class CompleteNetInterfaces(Completer):
    """
    Complete network interface names
    """

    def _shellCode(self, optName, shellType):
        if shellType == _ZSH:
            return "{}:{}:_net_interfaces".format(
                self._repeatFlag,
                self._description(optName),
            )
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class Completions:
    """
    Extra metadata for the shell tab-completion system.

    @type descriptions: C{dict}
    @ivar descriptions: ex. C{{"foo" : "use this description for foo instead"}}
        A dict mapping long option names to alternate descriptions.  When this
        variable is defined, the descriptions contained here will override
        those descriptions provided in the optFlags and optParameters
        variables.

    @type multiUse: C{list}
    @ivar multiUse: ex. C{ ["foo", "bar"] }
        An iterable containing those long option names which may appear on the
        command line more than once. By default, options will only be completed
        one time.

    @type mutuallyExclusive: C{list} of C{tuple}
    @ivar mutuallyExclusive: ex. C{ [("foo", "bar"), ("bar", "baz")] }
        A sequence of sequences, with each sub-sequence containing those long
        option names that are mutually exclusive. That is, those options that
        cannot appear on the command line together.

    @type optActions: C{dict}
    @ivar optActions: A dict mapping long option names to shell "actions".
        These actions define what may be completed as the argument to the
        given option. By default, all files/dirs will be completed if no
        action is given. For example::

            {"foo"    : CompleteFiles("*.py", descr="python files"),
             "bar"    : CompleteList(["one", "two", "three"]),
             "colors" : CompleteMultiList(["red", "green", "blue"])}

        Callables may instead be given for the values in this dict. The
        callable should accept no arguments, and return a C{Completer}
        instance used as the action in the same way as the literal actions in
        the example above.

        As you can see in the example above. The "foo" option will have files
        that end in .py completed when the user presses Tab. The "bar"
        option will have either of the strings "one", "two", or "three"
        completed when the user presses Tab.

        "colors" will allow multiple arguments to be completed, separated by
        commas. The possible arguments are red, green, and blue. Examples::

            my_command --foo some-file.foo --colors=red,green
            my_command --colors=green
            my_command --colors=green,blue

        Descriptions for the actions may be given with the optional C{descr}
        keyword argument. This is separate from the description of the option
        itself.

        Normally Zsh does not show these descriptions unless you have
        "verbose" completion turned on. Turn on verbosity with this in your
        ~/.zshrc::

            zstyle ':completion:*' verbose yes
            zstyle ':completion:*:descriptions' format '%B%d%b'

    @type extraActions: C{list}
    @ivar extraActions: Extra arguments are those arguments typically
        appearing at the end of the command-line, which are not associated
        with any particular named option. That is, the arguments that are
        given to the parseArgs() method of your usage.Options subclass. For
        example::
            [CompleteFiles(descr="file to read from"),
             Completer(descr="book title")]

        In the example above, the 1st non-option argument will be described as
        "file to read from" and all file/dir names will be completed (*). The
        2nd non-option argument will be described as "book title", but no
        actual completion matches will be produced.

        See the various C{Completer} subclasses for other types of things which
        may be tab-completed (users, groups, network interfaces, etc).

        Also note the C{repeat=True} flag which may be passed to any of the
        C{Completer} classes. This is set to allow the C{Completer} instance
        to be re-used for subsequent command-line words. See the C{Completer}
        docstring for details.
    """

    def __init__(
        self,
        descriptions={},
        multiUse=[],
        mutuallyExclusive=[],
        optActions={},
        extraActions=[],
    ):
        self.descriptions = descriptions
        self.multiUse = multiUse
        self.mutuallyExclusive = mutuallyExclusive
        self.optActions = optActions
        self.extraActions = extraActions


def docMakeChunks(optList, width=80):
    """
    Makes doc chunks for option declarations.

    Takes a list of dictionaries, each of which may have one or more
    of the keys 'long', 'short', 'doc', 'default', 'optType'.

    Returns a list of strings.
    The strings may be multiple lines,
    all of them end with a newline.
    """

    # XXX: sanity check to make sure we have a sane combination of keys.

    # Sort the options so they always appear in the same order
    optList.sort(key=lambda o: o.get("short", None) or o.get("long", None))

    maxOptLen = 0
    for opt in optList:
        optLen = len(opt.get("long", ""))
        if optLen:
            if opt.get("optType", None) == "parameter":
                # these take up an extra character
                optLen = optLen + 1
            maxOptLen = max(optLen, maxOptLen)

    colWidth1 = maxOptLen + len("  -s, --  ")
    colWidth2 = width - colWidth1
    # XXX - impose some sane minimum limit.
    # Then if we don't have enough room for the option and the doc
    # to share one line, they can take turns on alternating lines.

    colFiller1 = " " * colWidth1

    optChunks = []
    seen = {}
    for opt in optList:
        if opt.get("short", None) in seen or opt.get("long", None) in seen:
            continue
        for x in opt.get("short", None), opt.get("long", None):
            if x is not None:
                seen[x] = 1

        optLines = []
        comma = " "
        if opt.get("short", None):
            short = "-%c" % (opt["short"],)
        else:
            short = ""

        if opt.get("long", None):
            long = opt["long"]
            if opt.get("optType", None) == "parameter":
                long = long + "="

            long = "%-*s" % (maxOptLen, long)
            if short:
                comma = ","
        else:
            long = " " * (maxOptLen + len("--"))

        if opt.get("optType", None) == "command":
            column1 = "    %s      " % long
        else:
            column1 = "  %2s%c --%s  " % (short, comma, long)

        if opt.get("doc", ""):
            doc = opt["doc"].strip()
        else:
            doc = ""

        if (opt.get("optType", None) == "parameter") and not (
            opt.get("default", None) is None
        ):
            doc = "{} [default: {}]".format(doc, opt["default"])

        if (opt.get("optType", None) == "parameter") and opt.get(
            "dispatch", None
        ) is not None:
            d = opt["dispatch"]
            if isinstance(d, CoerceParameter) and d.doc:
                doc = f"{doc}. {d.doc}"

        if doc:
            column2_l = textwrap.wrap(doc, colWidth2)
        else:
            column2_l = [""]

        optLines.append(f"{column1}{column2_l.pop(0)}\n")

        for line in column2_l:
            optLines.append(f"{colFiller1}{line}\n")

        optChunks.append("".join(optLines))

    return optChunks


def flagFunction(method, name=None):
    """
    Determine whether a function is an optional handler for a I{flag} or an
    I{option}.

    A I{flag} handler takes no additional arguments.  It is used to handle
    command-line arguments like I{--nodaemon}.

    An I{option} handler takes one argument.  It is used to handle command-line
    arguments like I{--path=/foo/bar}.

    @param method: The bound method object to inspect.

    @param name: The name of the option for which the function is a handle.
    @type name: L{str}

    @raise UsageError: If the method takes more than one argument.

    @return: If the method is a flag handler, return C{True}.  Otherwise return
        C{False}.
    """
    reqArgs = len(inspect.signature(method).parameters)
    if reqArgs > 1:
        raise UsageError("Invalid Option function for %s" % (name or method.__name__))
    if reqArgs == 1:
        return False
    return True


def portCoerce(value):
    """
    Coerce a string value to an int port number, and checks the validity.
    """
    value = int(value)
    if value < 0 or value > 65535:
        raise ValueError(f"Port number not in range: {value}")
    return value


portCoerce.coerceDoc = "Must be an int between 0 and 65535."  # type: ignore[attr-defined]
