# -*- test-case-name: twisted.python.test.test_shellcomp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
No public APIs are provided by this module. Internal use only.

This module implements dynamic tab-completion for any command that uses
twisted.python.usage. Currently, only zsh is supported. Bash support may
be added in the future.

Maintainer: Eric P. Mangold - twisted AT teratorn DOT org

In order for zsh completion to take place the shell must be able to find an
appropriate "stub" file ("completion function") that invokes this code and
displays the results to the user.

The stub used for Twisted commands is in the file C{twisted-completion.zsh},
which is also included in the official Zsh distribution at
C{Completion/Unix/Command/_twisted}. Use this file as a basis for completion
functions for your own commands. You should only need to change the first line
to something like C{#compdef mycommand}.

The main public documentation exists in the L{twisted.python.usage.Options}
docstring, the L{twisted.python.usage.Completions} docstring, and the
Options howto.
"""

import getopt
import inspect
import itertools
from types import MethodType
from typing import Dict, List, Set

from twisted.python import reflect, usage, util
from twisted.python.compat import ioType


def shellComplete(config, cmdName, words, shellCompFile):
    """
    Perform shell completion.

    A completion function (shell script) is generated for the requested
    shell and written to C{shellCompFile}, typically C{stdout}. The result
    is then eval'd by the shell to produce the desired completions.

    @type config: L{twisted.python.usage.Options}
    @param config: The L{twisted.python.usage.Options} instance to generate
        completions for.

    @type cmdName: C{str}
    @param cmdName: The name of the command we're generating completions for.
        In the case of zsh, this is used to print an appropriate
        "#compdef $CMD" line at the top of the output. This is
        not necessary for the functionality of the system, but it
        helps in debugging, since the output we produce is properly
        formed and may be saved in a file and used as a stand-alone
        completion function.

    @type words: C{list} of C{str}
    @param words: The raw command-line words passed to use by the shell
        stub function. argv[0] has already been stripped off.

    @type shellCompFile: C{file}
    @param shellCompFile: The file to write completion data to.
    """

    # If given a file with unicode semantics, such as sys.stdout on Python 3,
    # we must get at the the underlying buffer which has bytes semantics.
    if shellCompFile and ioType(shellCompFile) == str:
        shellCompFile = shellCompFile.buffer

    # shellName is provided for forward-compatibility. It is not used,
    # since we currently only support zsh.
    shellName, position = words[-1].split(":")
    position = int(position)
    # zsh gives the completion position ($CURRENT) as a 1-based index,
    # and argv[0] has already been stripped off, so we subtract 2 to
    # get the real 0-based index.
    position -= 2
    cWord = words[position]

    # since the user may hit TAB at any time, we may have been called with an
    # incomplete command-line that would generate getopt errors if parsed
    # verbatim. However, we must do *some* parsing in order to determine if
    # there is a specific subcommand that we need to provide completion for.
    # So, to make the command-line more sane we work backwards from the
    # current completion position and strip off all words until we find one
    # that "looks" like a subcommand. It may in fact be the argument to a
    # normal command-line option, but that won't matter for our purposes.
    while position >= 1:
        if words[position - 1].startswith("-"):
            position -= 1
        else:
            break
    words = words[:position]

    subCommands = getattr(config, "subCommands", None)
    if subCommands:
        # OK, this command supports sub-commands, so lets see if we have been
        # given one.

        # If the command-line arguments are not valid then we won't be able to
        # sanely detect the sub-command, so just generate completions as if no
        # sub-command was found.
        args = None
        try:
            opts, args = getopt.getopt(words, config.shortOpt, config.longOpt)
        except getopt.error:
            pass

        if args:
            # yes, we have a subcommand. Try to find it.
            for (cmd, short, parser, doc) in config.subCommands:
                if args[0] == cmd or args[0] == short:
                    subOptions = parser()
                    subOptions.parent = config

                    gen: ZshBuilder = ZshSubcommandBuilder(
                        subOptions, config, cmdName, shellCompFile
                    )
                    gen.write()
                    return

        # sub-command not given, or did not match any knowns sub-command names
        genSubs = True
        if cWord.startswith("-"):
            # optimization: if the current word being completed starts
            # with a hyphen then it can't be a sub-command, so skip
            # the expensive generation of the sub-command list
            genSubs = False
        gen = ZshBuilder(config, cmdName, shellCompFile)
        gen.write(genSubs=genSubs)
    else:
        gen = ZshBuilder(config, cmdName, shellCompFile)
        gen.write()


class SubcommandAction(usage.Completer):
    def _shellCode(self, optName, shellType):
        if shellType == usage._ZSH:
            return "*::subcmd:->subcmd"
        raise NotImplementedError(f"Unknown shellType {shellType!r}")


class ZshBuilder:
    """
    Constructs zsh code that will complete options for a given usage.Options
    instance, possibly including a list of subcommand names.

    Completions for options to subcommands won't be generated because this
    class will never be used if the user is completing options for a specific
    subcommand. (See L{ZshSubcommandBuilder} below)

    @type options: L{twisted.python.usage.Options}
    @ivar options: The L{twisted.python.usage.Options} instance defined for this
        command.

    @type cmdName: C{str}
    @ivar cmdName: The name of the command we're generating completions for.

    @type file: C{file}
    @ivar file: The C{file} to write the completion function to.  The C{file}
        must have L{bytes} I/O semantics.
    """

    def __init__(self, options, cmdName, file):
        self.options = options
        self.cmdName = cmdName
        self.file = file

    def write(self, genSubs=True):
        """
        Generate the completion function and write it to the output file
        @return: L{None}

        @type genSubs: C{bool}
        @param genSubs: Flag indicating whether or not completions for the list
            of subcommand should be generated. Only has an effect
            if the C{subCommands} attribute has been defined on the
            L{twisted.python.usage.Options} instance.
        """
        if genSubs and getattr(self.options, "subCommands", None) is not None:
            gen = ZshArgumentsGenerator(self.options, self.cmdName, self.file)
            gen.extraActions.insert(0, SubcommandAction())
            gen.write()
            self.file.write(b"local _zsh_subcmds_array\n_zsh_subcmds_array=(\n")
            for (cmd, short, parser, desc) in self.options.subCommands:
                self.file.write(
                    b'"' + cmd.encode("utf-8") + b":" + desc.encode("utf-8") + b'"\n'
                )
            self.file.write(b")\n\n")
            self.file.write(b'_describe "sub-command" _zsh_subcmds_array\n')
        else:
            gen = ZshArgumentsGenerator(self.options, self.cmdName, self.file)
            gen.write()


class ZshSubcommandBuilder(ZshBuilder):
    """
    Constructs zsh code that will complete options for a given usage.Options
    instance, and also for a single sub-command. This will only be used in
    the case where the user is completing options for a specific subcommand.

    @type subOptions: L{twisted.python.usage.Options}
    @ivar subOptions: The L{twisted.python.usage.Options} instance defined for
        the sub command.
    """

    def __init__(self, subOptions, *args):
        self.subOptions = subOptions
        ZshBuilder.__init__(self, *args)

    def write(self):
        """
        Generate the completion function and write it to the output file
        @return: L{None}
        """
        gen = ZshArgumentsGenerator(self.options, self.cmdName, self.file)
        gen.extraActions.insert(0, SubcommandAction())
        gen.write()

        gen = ZshArgumentsGenerator(self.subOptions, self.cmdName, self.file)
        gen.write()


class ZshArgumentsGenerator:
    """
    Generate a call to the zsh _arguments completion function
    based on data in a usage.Options instance

    The first three instance variables are populated based on constructor
    arguments. The remaining non-constructor variables are populated by this
    class with data gathered from the C{Options} instance passed in, and its
    base classes.

    @type options: L{twisted.python.usage.Options}
    @ivar options: The L{twisted.python.usage.Options} instance to generate for

    @type cmdName: C{str}
    @ivar cmdName: The name of the command we're generating completions for.

    @type file: C{file}
    @ivar file: The C{file} to write the completion function to.  The C{file}
        must have L{bytes} I/O semantics.

    @type descriptions: C{dict}
    @ivar descriptions: A dict mapping long option names to alternate
        descriptions. When this variable is defined, the descriptions
        contained here will override those descriptions provided in the
        optFlags and optParameters variables.

    @type multiUse: C{list}
    @ivar multiUse: An iterable containing those long option names which may
        appear on the command line more than once. By default, options will
        only be completed one time.

    @type mutuallyExclusive: C{list} of C{tuple}
    @ivar mutuallyExclusive: A sequence of sequences, with each sub-sequence
        containing those long option names that are mutually exclusive. That is,
        those options that cannot appear on the command line together.

    @type optActions: C{dict}
    @ivar optActions: A dict mapping long option names to shell "actions".
        These actions define what may be completed as the argument to the
        given option, and should be given as instances of
        L{twisted.python.usage.Completer}.

        Callables may instead be given for the values in this dict. The
        callable should accept no arguments, and return a C{Completer}
        instance used as the action.

    @type extraActions: C{list} of C{twisted.python.usage.Completer}
    @ivar extraActions: Extra arguments are those arguments typically
        appearing at the end of the command-line, which are not associated
        with any particular named option. That is, the arguments that are
        given to the parseArgs() method of your usage.Options subclass.
    """

    def __init__(self, options, cmdName, file):
        self.options = options
        self.cmdName = cmdName
        self.file = file

        self.descriptions = {}
        self.multiUse = set()
        self.mutuallyExclusive = []
        self.optActions = {}
        self.extraActions = []

        for cls in reversed(inspect.getmro(options.__class__)):
            data = getattr(cls, "compData", None)
            if data:
                self.descriptions.update(data.descriptions)
                self.optActions.update(data.optActions)
                self.multiUse.update(data.multiUse)

                self.mutuallyExclusive.extend(data.mutuallyExclusive)

                # I don't see any sane way to aggregate extraActions, so just
                # take the one at the top of the MRO (nearest the `options'
                # instance).
                if data.extraActions:
                    self.extraActions = data.extraActions

        aCL = reflect.accumulateClassList

        optFlags: List[List[object]] = []
        optParams: List[List[object]] = []

        aCL(options.__class__, "optFlags", optFlags)
        aCL(options.__class__, "optParameters", optParams)

        for i, optList in enumerate(optFlags):
            if len(optList) != 3:
                optFlags[i] = util.padTo(3, optList)

        for i, optList in enumerate(optParams):
            if len(optList) != 5:
                optParams[i] = util.padTo(5, optList)

        self.optFlags = optFlags
        self.optParams = optParams

        paramNameToDefinition = {}
        for optList in optParams:
            paramNameToDefinition[optList[0]] = optList[1:]
        self.paramNameToDefinition = paramNameToDefinition

        flagNameToDefinition = {}
        for optList in optFlags:
            flagNameToDefinition[optList[0]] = optList[1:]
        self.flagNameToDefinition = flagNameToDefinition

        allOptionsNameToDefinition = {}
        allOptionsNameToDefinition.update(paramNameToDefinition)
        allOptionsNameToDefinition.update(flagNameToDefinition)
        self.allOptionsNameToDefinition = allOptionsNameToDefinition

        self.addAdditionalOptions()

        # makes sure none of the Completions metadata references
        # option names that don't exist. (great for catching typos)
        self.verifyZshNames()

        self.excludes = self.makeExcludesDict()

    def write(self):
        """
        Write the zsh completion code to the file given to __init__
        @return: L{None}
        """
        self.writeHeader()
        self.writeExtras()
        self.writeOptions()
        self.writeFooter()

    def writeHeader(self):
        """
        This is the start of the code that calls _arguments
        @return: L{None}
        """
        self.file.write(
            b"#compdef " + self.cmdName.encode("utf-8") + b"\n\n"
            b'_arguments -s -A "-*" \\\n'
        )

    def writeOptions(self):
        """
        Write out zsh code for each option in this command
        @return: L{None}
        """
        optNames = list(self.allOptionsNameToDefinition.keys())
        optNames.sort()
        for longname in optNames:
            self.writeOpt(longname)

    def writeExtras(self):
        """
        Write out completion information for extra arguments appearing on the
        command-line. These are extra positional arguments not associated
        with a named option. That is, the stuff that gets passed to
        Options.parseArgs().

        @return: L{None}

        @raise ValueError: If C{Completer} with C{repeat=True} is found and
            is not the last item in the C{extraActions} list.
        """
        for i, action in enumerate(self.extraActions):
            # a repeatable action must be the last action in the list
            if action._repeat and i != len(self.extraActions) - 1:
                raise ValueError(
                    "Completer with repeat=True must be "
                    "last item in Options.extraActions"
                )
            self.file.write(escape(action._shellCode("", usage._ZSH)).encode("utf-8"))
            self.file.write(b" \\\n")

    def writeFooter(self):
        """
        Write the last bit of code that finishes the call to _arguments
        @return: L{None}
        """
        self.file.write(b"&& return 0\n")

    def verifyZshNames(self):
        """
        Ensure that none of the option names given in the metadata are typoed
        @return: L{None}
        @raise ValueError: If unknown option names have been found.
        """

        def err(name):
            raise ValueError(
                'Unknown option name "%s" found while\n'
                "examining Completions instances on %s" % (name, self.options)
            )

        for name in itertools.chain(self.descriptions, self.optActions, self.multiUse):
            if name not in self.allOptionsNameToDefinition:
                err(name)

        for seq in self.mutuallyExclusive:
            for name in seq:
                if name not in self.allOptionsNameToDefinition:
                    err(name)

    def excludeStr(self, longname, buildShort=False):
        """
        Generate an "exclusion string" for the given option

        @type longname: C{str}
        @param longname: The long option name (e.g. "verbose" instead of "v")

        @type buildShort: C{bool}
        @param buildShort: May be True to indicate we're building an excludes
            string for the short option that corresponds to the given long opt.

        @return: The generated C{str}
        """
        if longname in self.excludes:
            exclusions = self.excludes[longname].copy()
        else:
            exclusions = set()

        # if longname isn't a multiUse option (can't appear on the cmd line more
        # than once), then we have to exclude the short option if we're
        # building for the long option, and vice versa.
        if longname not in self.multiUse:
            if buildShort is False:
                short = self.getShortOption(longname)
                if short is not None:
                    exclusions.add(short)
            else:
                exclusions.add(longname)

        if not exclusions:
            return ""

        strings = []
        for optName in exclusions:
            if len(optName) == 1:
                # short option
                strings.append("-" + optName)
            else:
                strings.append("--" + optName)
        strings.sort()  # need deterministic order for reliable unit-tests
        return "(%s)" % " ".join(strings)

    def makeExcludesDict(self) -> Dict[str, Set[str]]:
        """
        @return: A C{dict} that maps each option name appearing in
            self.mutuallyExclusive to a set of those option names that is it
            mutually exclusive with (can't appear on the cmd line with).
        """

        # create a mapping of long option name -> single character name
        longToShort = {}
        for optList in itertools.chain(self.optParams, self.optFlags):
            if optList[1] != None:
                longToShort[optList[0]] = optList[1]

        excludes: Dict[str, Set[str]] = {}
        for lst in self.mutuallyExclusive:
            for i, longname in enumerate(lst):
                tmp = set(lst[:i] + lst[i + 1 :])
                for name in tmp.copy():
                    if name in longToShort:
                        tmp.add(longToShort[name])

                if longname in excludes:
                    excludes[longname] = excludes[longname].union(tmp)
                else:
                    excludes[longname] = tmp
        return excludes

    def writeOpt(self, longname):
        """
        Write out the zsh code for the given argument. This is just part of the
        one big call to _arguments

        @type longname: C{str}
        @param longname: The long option name (e.g. "verbose" instead of "v")

        @return: L{None}
        """
        if longname in self.flagNameToDefinition:
            # It's a flag option. Not one that takes a parameter.
            longField = "--%s" % longname
        else:
            longField = "--%s=" % longname

        short = self.getShortOption(longname)
        if short != None:
            shortField = "-" + short
        else:
            shortField = ""

        descr = self.getDescription(longname)
        descriptionField = descr.replace("[", r"\[")
        descriptionField = descriptionField.replace("]", r"\]")
        descriptionField = "[%s]" % descriptionField

        actionField = self.getAction(longname)
        if longname in self.multiUse:
            multiField = "*"
        else:
            multiField = ""

        longExclusionsField = self.excludeStr(longname)

        if short:
            # we have to write an extra line for the short option if we have one
            shortExclusionsField = self.excludeStr(longname, buildShort=True)
            self.file.write(
                escape(
                    "%s%s%s%s%s"
                    % (
                        shortExclusionsField,
                        multiField,
                        shortField,
                        descriptionField,
                        actionField,
                    )
                ).encode("utf-8")
            )
            self.file.write(b" \\\n")

        self.file.write(
            escape(
                "%s%s%s%s%s"
                % (
                    longExclusionsField,
                    multiField,
                    longField,
                    descriptionField,
                    actionField,
                )
            ).encode("utf-8")
        )
        self.file.write(b" \\\n")

    def getAction(self, longname):
        """
        Return a zsh "action" string for the given argument
        @return: C{str}
        """
        if longname in self.optActions:
            if callable(self.optActions[longname]):
                action = self.optActions[longname]()
            else:
                action = self.optActions[longname]
            return action._shellCode(longname, usage._ZSH)

        if longname in self.paramNameToDefinition:
            return f":{longname}:_files"
        return ""

    def getDescription(self, longname):
        """
        Return the description to be used for this argument
        @return: C{str}
        """
        # check if we have an alternate descr for this arg, and if so use it
        if longname in self.descriptions:
            return self.descriptions[longname]

        # otherwise we have to get it from the optFlags or optParams
        try:
            descr = self.flagNameToDefinition[longname][1]
        except KeyError:
            try:
                descr = self.paramNameToDefinition[longname][2]
            except KeyError:
                descr = None

        if descr is not None:
            return descr

        # let's try to get it from the opt_foo method doc string if there is one
        longMangled = longname.replace("-", "_")  # this is what t.p.usage does
        obj = getattr(self.options, "opt_%s" % longMangled, None)
        if obj is not None:
            descr = descrFromDoc(obj)
            if descr is not None:
                return descr

        return longname  # we really ought to have a good description to use

    def getShortOption(self, longname):
        """
        Return the short option letter or None
        @return: C{str} or L{None}
        """
        optList = self.allOptionsNameToDefinition[longname]
        return optList[0] or None

    def addAdditionalOptions(self) -> None:
        """
        Add additional options to the optFlags and optParams lists.
        These will be defined by 'opt_foo' methods of the Options subclass
        @return: L{None}
        """
        methodsDict: Dict[str, MethodType] = {}
        reflect.accumulateMethods(self.options, methodsDict, "opt_")
        methodToShort = {}
        for name in methodsDict.copy():
            if len(name) == 1:
                methodToShort[methodsDict[name]] = name
                del methodsDict[name]

        for methodName, methodObj in methodsDict.items():
            longname = methodName.replace("_", "-")  # t.p.usage does this
            # if this option is already defined by the optFlags or
            # optParameters then we don't want to override that data
            if longname in self.allOptionsNameToDefinition:
                continue

            descr = self.getDescription(longname)

            short = None
            if methodObj in methodToShort:
                short = methodToShort[methodObj]

            reqArgs = methodObj.__func__.__code__.co_argcount
            if reqArgs == 2:
                self.optParams.append([longname, short, None, descr])
                self.paramNameToDefinition[longname] = [short, None, descr]
                self.allOptionsNameToDefinition[longname] = [short, None, descr]
            else:
                # reqArgs must equal 1. self.options would have failed
                # to instantiate if it had opt_ methods with bad signatures.
                self.optFlags.append([longname, short, descr])
                self.flagNameToDefinition[longname] = [short, descr]
                self.allOptionsNameToDefinition[longname] = [short, None, descr]


def descrFromDoc(obj):
    """
    Generate an appropriate description from docstring of the given object
    """
    if obj.__doc__ is None or obj.__doc__.isspace():
        return None

    lines = [x.strip() for x in obj.__doc__.split("\n") if x and not x.isspace()]
    return " ".join(lines)


def escape(x):
    """
    Shell escape the given string

    Implementation borrowed from now-deprecated commands.mkarg() in the stdlib
    """
    if "'" not in x:
        return "'" + x + "'"
    s = '"'
    for c in x:
        if c in '\\$"`':
            s = s + "\\"
        s = s + c
    s = s + '"'
    return s
