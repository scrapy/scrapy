# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for twisted.python._shellcomp
"""


import sys
from io import BytesIO
from typing import List, Optional

from twisted.python import _shellcomp, reflect, usage
from twisted.python.usage import CompleteFiles, CompleteList, Completer, Completions
from twisted.trial import unittest


class ZshScriptTestMeta(type):
    """
    Metaclass of ZshScriptTestMixin.
    """

    def __new__(cls, name, bases, attrs):
        def makeTest(cmdName, optionsFQPN):
            def runTest(self):
                return test_genZshFunction(self, cmdName, optionsFQPN)

            return runTest

        # add test_ methods to the class for each script
        # we are testing.
        if "generateFor" in attrs:
            for cmdName, optionsFQPN in attrs["generateFor"]:
                test = makeTest(cmdName, optionsFQPN)
                attrs["test_genZshFunction_" + cmdName] = test

        return type.__new__(cls, name, bases, attrs)


class ZshScriptTestMixin(metaclass=ZshScriptTestMeta):
    """
    Integration test helper to show that C{usage.Options} classes can have zsh
    completion functions generated for them without raising errors.

    In your subclasses set a class variable like so::

      #            | cmd name | Fully Qualified Python Name of Options class |
      #
      generateFor = [('conch',  'twisted.conch.scripts.conch.ClientOptions'),
                     ('twistd', 'twisted.scripts.twistd.ServerOptions'),
                     ]

    Each package that contains Twisted scripts should contain one TestCase
    subclass which also inherits from this mixin, and contains a C{generateFor}
    list appropriate for the scripts in that package.
    """


def test_genZshFunction(self, cmdName, optionsFQPN):
    """
    Generate completion functions for given twisted command - no errors
    should be raised

    @type cmdName: C{str}
    @param cmdName: The name of the command-line utility e.g. 'twistd'

    @type optionsFQPN: C{str}
    @param optionsFQPN: The Fully Qualified Python Name of the C{Options}
        class to be tested.
    """
    outputFile = BytesIO()
    self.patch(usage.Options, "_shellCompFile", outputFile)

    # some scripts won't import or instantiate because of missing
    # dependencies (pyOpenSSL, etc) so we have to skip them.
    try:
        o = reflect.namedAny(optionsFQPN)()
    except Exception as e:
        raise unittest.SkipTest(
            "Couldn't import or instantiate " "Options class: %s" % (e,)
        )

    try:
        o.parseOptions(["", "--_shell-completion", "zsh:2"])
    except ImportError as e:
        # this can happen for commands which don't have all
        # the necessary dependencies installed. skip test.
        # skip
        raise unittest.SkipTest("ImportError calling parseOptions(): %s", (e,))
    except SystemExit:
        pass  # expected
    else:
        self.fail("SystemExit not raised")
    outputFile.seek(0)
    # test that we got some output
    self.assertEqual(1, len(outputFile.read(1)))
    outputFile.seek(0)
    outputFile.truncate()

    # now, if it has sub commands, we have to test those too
    if hasattr(o, "subCommands"):
        for (cmd, short, parser, doc) in o.subCommands:
            try:
                o.parseOptions([cmd, "", "--_shell-completion", "zsh:3"])
            except ImportError as e:
                # this can happen for commands which don't have all
                # the necessary dependencies installed. skip test.
                raise unittest.SkipTest(
                    "ImportError calling parseOptions() " "on subcommand: %s", (e,)
                )
            except SystemExit:
                pass  # expected
            else:
                self.fail("SystemExit not raised")

            outputFile.seek(0)
            # test that we got some output
            self.assertEqual(1, len(outputFile.read(1)))
            outputFile.seek(0)
            outputFile.truncate()

    # flushed because we don't want DeprecationWarnings to be printed when
    # running these test cases.
    self.flushWarnings()


class ZshTests(unittest.TestCase):
    """
    Tests for zsh completion code
    """

    def test_accumulateMetadata(self):
        """
        Are `compData' attributes you can place on Options classes
        picked up correctly?
        """
        opts = FighterAceExtendedOptions()
        ag = _shellcomp.ZshArgumentsGenerator(opts, "ace", BytesIO())

        descriptions = FighterAceOptions.compData.descriptions.copy()
        descriptions.update(FighterAceExtendedOptions.compData.descriptions)

        self.assertEqual(ag.descriptions, descriptions)
        self.assertEqual(ag.multiUse, set(FighterAceOptions.compData.multiUse))
        self.assertEqual(
            ag.mutuallyExclusive, FighterAceOptions.compData.mutuallyExclusive
        )

        optActions = FighterAceOptions.compData.optActions.copy()
        optActions.update(FighterAceExtendedOptions.compData.optActions)
        self.assertEqual(ag.optActions, optActions)

        self.assertEqual(ag.extraActions, FighterAceOptions.compData.extraActions)

    def test_mutuallyExclusiveCornerCase(self):
        """
        Exercise a corner-case of ZshArgumentsGenerator.makeExcludesDict()
        where the long option name already exists in the `excludes` dict being
        built.
        """

        class OddFighterAceOptions(FighterAceExtendedOptions):
            # since "fokker", etc, are already defined as mutually-
            # exclusive on the super-class, defining them again here forces
            # the corner-case to be exercised.
            optFlags = [
                ["anatra", None, "Select the Anatra DS as your dogfighter aircraft"]
            ]
            compData = Completions(
                mutuallyExclusive=[["anatra", "fokker", "albatros", "spad", "bristol"]]
            )

        opts = OddFighterAceOptions()
        ag = _shellcomp.ZshArgumentsGenerator(opts, "ace", BytesIO())

        expected = {
            "albatros": {"anatra", "b", "bristol", "f", "fokker", "s", "spad"},
            "anatra": {"a", "albatros", "b", "bristol", "f", "fokker", "s", "spad"},
            "bristol": {"a", "albatros", "anatra", "f", "fokker", "s", "spad"},
            "fokker": {"a", "albatros", "anatra", "b", "bristol", "s", "spad"},
            "spad": {"a", "albatros", "anatra", "b", "bristol", "f", "fokker"},
        }

        self.assertEqual(ag.excludes, expected)

    def test_accumulateAdditionalOptions(self):
        """
        We pick up options that are only defined by having an
        appropriately named method on your Options class,
        e.g. def opt_foo(self, foo)
        """
        opts = FighterAceExtendedOptions()
        ag = _shellcomp.ZshArgumentsGenerator(opts, "ace", BytesIO())

        self.assertIn("nocrash", ag.flagNameToDefinition)
        self.assertIn("nocrash", ag.allOptionsNameToDefinition)

        self.assertIn("difficulty", ag.paramNameToDefinition)
        self.assertIn("difficulty", ag.allOptionsNameToDefinition)

    def test_verifyZshNames(self):
        """
        Using a parameter/flag name that doesn't exist
        will raise an error
        """

        class TmpOptions(FighterAceExtendedOptions):
            # Note typo of detail
            compData = Completions(optActions={"detaill": None})

        self.assertRaises(
            ValueError, _shellcomp.ZshArgumentsGenerator, TmpOptions(), "ace", BytesIO()
        )

        class TmpOptions2(FighterAceExtendedOptions):
            # Note that 'foo' and 'bar' are not real option
            # names defined in this class
            compData = Completions(mutuallyExclusive=[("foo", "bar")])

        self.assertRaises(
            ValueError,
            _shellcomp.ZshArgumentsGenerator,
            TmpOptions2(),
            "ace",
            BytesIO(),
        )

    def test_zshCode(self):
        """
        Generate a completion function, and test the textual output
        against a known correct output
        """
        outputFile = BytesIO()
        self.patch(usage.Options, "_shellCompFile", outputFile)
        self.patch(sys, "argv", ["silly", "", "--_shell-completion", "zsh:2"])
        opts = SimpleProgOptions()
        self.assertRaises(SystemExit, opts.parseOptions)
        self.assertEqual(testOutput1, outputFile.getvalue())

    def test_zshCodeWithSubs(self):
        """
        Generate a completion function with subcommands,
        and test the textual output against a known correct output
        """
        outputFile = BytesIO()
        self.patch(usage.Options, "_shellCompFile", outputFile)
        self.patch(sys, "argv", ["silly2", "", "--_shell-completion", "zsh:2"])
        opts = SimpleProgWithSubcommands()
        self.assertRaises(SystemExit, opts.parseOptions)
        self.assertEqual(testOutput2, outputFile.getvalue())

    def test_incompleteCommandLine(self):
        """
        Completion still happens even if a command-line is given
        that would normally throw UsageError.
        """
        outputFile = BytesIO()
        self.patch(usage.Options, "_shellCompFile", outputFile)
        opts = FighterAceOptions()

        self.assertRaises(
            SystemExit,
            opts.parseOptions,
            [
                "--fokker",
                "server",
                "--unknown-option",
                "--unknown-option2",
                "--_shell-completion",
                "zsh:5",
            ],
        )
        outputFile.seek(0)
        # test that we got some output
        self.assertEqual(1, len(outputFile.read(1)))

    def test_incompleteCommandLine_case2(self):
        """
        Completion still happens even if a command-line is given
        that would normally throw UsageError.

        The existence of --unknown-option prior to the subcommand
        will break subcommand detection... but we complete anyway
        """
        outputFile = BytesIO()
        self.patch(usage.Options, "_shellCompFile", outputFile)
        opts = FighterAceOptions()

        self.assertRaises(
            SystemExit,
            opts.parseOptions,
            [
                "--fokker",
                "--unknown-option",
                "server",
                "--list-server",
                "--_shell-completion",
                "zsh:5",
            ],
        )
        outputFile.seek(0)
        # test that we got some output
        self.assertEqual(1, len(outputFile.read(1)))

        outputFile.seek(0)
        outputFile.truncate()

    def test_incompleteCommandLine_case3(self):
        """
        Completion still happens even if a command-line is given
        that would normally throw UsageError.

        Break subcommand detection in a different way by providing
        an invalid subcommand name.
        """
        outputFile = BytesIO()
        self.patch(usage.Options, "_shellCompFile", outputFile)
        opts = FighterAceOptions()

        self.assertRaises(
            SystemExit,
            opts.parseOptions,
            [
                "--fokker",
                "unknown-subcommand",
                "--list-server",
                "--_shell-completion",
                "zsh:4",
            ],
        )
        outputFile.seek(0)
        # test that we got some output
        self.assertEqual(1, len(outputFile.read(1)))

    def test_skipSubcommandList(self):
        """
        Ensure the optimization which skips building the subcommand list
        under certain conditions isn't broken.
        """
        outputFile = BytesIO()
        self.patch(usage.Options, "_shellCompFile", outputFile)
        opts = FighterAceOptions()

        self.assertRaises(
            SystemExit, opts.parseOptions, ["--alba", "--_shell-completion", "zsh:2"]
        )
        outputFile.seek(0)
        # test that we got some output
        self.assertEqual(1, len(outputFile.read(1)))

    def test_poorlyDescribedOptMethod(self):
        """
        Test corner case fetching an option description from a method docstring
        """
        opts = FighterAceOptions()
        argGen = _shellcomp.ZshArgumentsGenerator(opts, "ace", None)

        descr = argGen.getDescription("silly")

        # docstring for opt_silly is useless so it should just use the
        # option name as the description
        self.assertEqual(descr, "silly")

    def test_brokenActions(self):
        """
        A C{Completer} with repeat=True may only be used as the
        last item in the extraActions list.
        """

        class BrokenActions(usage.Options):
            compData = usage.Completions(
                extraActions=[usage.Completer(repeat=True), usage.Completer()]
            )

        outputFile = BytesIO()
        opts = BrokenActions()
        self.patch(opts, "_shellCompFile", outputFile)
        self.assertRaises(
            ValueError, opts.parseOptions, ["", "--_shell-completion", "zsh:2"]
        )

    def test_optMethodsDontOverride(self):
        """
        opt_* methods on Options classes should not override the
        data provided in optFlags or optParameters.
        """

        class Options(usage.Options):
            optFlags = [["flag", "f", "A flag"]]
            optParameters = [["param", "p", None, "A param"]]

            def opt_flag(self):
                """junk description"""

            def opt_param(self, param):
                """junk description"""

        opts = Options()
        argGen = _shellcomp.ZshArgumentsGenerator(opts, "ace", None)

        self.assertEqual(argGen.getDescription("flag"), "A flag")
        self.assertEqual(argGen.getDescription("param"), "A param")


class EscapeTests(unittest.TestCase):
    def test_escape(self):
        """
        Verify _shellcomp.escape() function
        """
        esc = _shellcomp.escape

        test = "$"
        self.assertEqual(esc(test), "'$'")

        test = "A--'$\"\\`--B"
        self.assertEqual(esc(test), '"A--\'\\$\\"\\\\\\`--B"')


class CompleterNotImplementedTests(unittest.TestCase):
    """
    Test that using an unknown shell constant with SubcommandAction
    raises NotImplementedError

    The other Completer() subclasses are tested in test_usage.py
    """

    def test_unknownShell(self):
        """
        Using an unknown shellType should raise NotImplementedError
        """
        action = _shellcomp.SubcommandAction()

        self.assertRaises(
            NotImplementedError, action._shellCode, None, "bad_shell_type"
        )


class FighterAceServerOptions(usage.Options):
    """
    Options for FighterAce 'server' subcommand
    """

    optFlags = [
        ["list-server", None, "List this server with the online FighterAce network"]
    ]
    optParameters = [
        [
            "packets-per-second",
            None,
            "Number of update packets to send per second",
            "20",
        ]
    ]


class FighterAceOptions(usage.Options):
    """
    Command-line options for an imaginary `Fighter Ace` game
    """

    optFlags: List[List[Optional[str]]] = [
        ["fokker", "f", "Select the Fokker Dr.I as your dogfighter aircraft"],
        ["albatros", "a", "Select the Albatros D-III as your dogfighter aircraft"],
        ["spad", "s", "Select the SPAD S.VII as your dogfighter aircraft"],
        ["bristol", "b", "Select the Bristol Scout as your dogfighter aircraft"],
        ["physics", "p", "Enable secret Twisted physics engine"],
        ["jam", "j", "Enable a small chance that your machine guns will jam!"],
        ["verbose", "v", "Verbose logging (may be specified more than once)"],
    ]

    optParameters: List[List[Optional[str]]] = [
        ["pilot-name", None, "What's your name, Ace?", "Manfred von Richthofen"],
        ["detail", "d", "Select the level of rendering detail (1-5)", "3"],
    ]

    subCommands = [
        ["server", None, FighterAceServerOptions, "Start FighterAce game-server."],
    ]

    compData = Completions(
        descriptions={"physics": "Twisted-Physics", "detail": "Rendering detail level"},
        multiUse=["verbose"],
        mutuallyExclusive=[["fokker", "albatros", "spad", "bristol"]],
        optActions={"detail": CompleteList(["1" "2" "3" "4" "5"])},
        extraActions=[CompleteFiles(descr="saved game file to load")],
    )

    def opt_silly(self):
        # A silly option which nobody can explain
        """ """


class FighterAceExtendedOptions(FighterAceOptions):
    """
    Extend the options and zsh metadata provided by FighterAceOptions.
    _shellcomp must accumulate options and metadata from all classes in the
    hiearchy so this is important to test.
    """

    optFlags = [["no-stalls", None, "Turn off the ability to stall your aircraft"]]
    optParameters = [
        ["reality-level", None, "Select the level of physics reality (1-5)", "5"]
    ]

    compData = Completions(
        descriptions={"no-stalls": "Can't stall your plane"},
        optActions={"reality-level": Completer(descr="Physics reality level")},
    )

    def opt_nocrash(self):
        """
        Select that you can't crash your plane
        """

    def opt_difficulty(self, difficulty):
        """
        How tough are you? (1-10)
        """


def _accuracyAction():
    # add tick marks just to exercise quoting
    return CompleteList(["1", "2", "3"], descr="Accuracy'`?")


class SimpleProgOptions(usage.Options):
    """
    Command-line options for a `Silly` imaginary program
    """

    optFlags = [
        ["color", "c", "Turn on color output"],
        ["gray", "g", "Turn on gray-scale output"],
        ["verbose", "v", "Verbose logging (may be specified more than once)"],
    ]

    optParameters = [
        ["optimization", None, "5", "Select the level of optimization (1-5)"],
        ["accuracy", "a", "3", "Select the level of accuracy (1-3)"],
    ]

    compData = Completions(
        descriptions={"color": "Color on", "optimization": "Optimization level"},
        multiUse=["verbose"],
        mutuallyExclusive=[["color", "gray"]],
        optActions={
            "optimization": CompleteList(
                ["1", "2", "3", "4", "5"], descr="Optimization?"
            ),
            "accuracy": _accuracyAction,
        },
        extraActions=[CompleteFiles(descr="output file")],
    )

    def opt_X(self):
        """
        usage.Options does not recognize single-letter opt_ methods
        """


class SimpleProgSub1(usage.Options):
    optFlags = [["sub-opt", "s", "Sub Opt One"]]


class SimpleProgSub2(usage.Options):
    optFlags = [["sub-opt", "s", "Sub Opt Two"]]


class SimpleProgWithSubcommands(SimpleProgOptions):
    optFlags = [["some-option"], ["other-option", "o"]]

    optParameters = [
        ["some-param"],
        ["other-param", "p"],
        ["another-param", "P", "Yet Another Param"],
    ]

    subCommands = [
        ["sub1", None, SimpleProgSub1, "Sub Command 1"],
        ["sub2", None, SimpleProgSub2, "Sub Command 2"],
    ]


testOutput1 = b"""#compdef silly

_arguments -s -A "-*" \\
':output file (*):_files -g "*"' \\
"(--accuracy)-a[Select the level of accuracy (1-3)]:Accuracy'\\`?:(1 2 3)" \\
"(-a)--accuracy=[Select the level of accuracy (1-3)]:Accuracy'\\`?:(1 2 3)" \\
'(--color --gray -g)-c[Color on]' \\
'(--gray -c -g)--color[Color on]' \\
'(--color --gray -c)-g[Turn on gray-scale output]' \\
'(--color -c -g)--gray[Turn on gray-scale output]' \\
'--help[Display this help and exit.]' \\
'--optimization=[Optimization level]:Optimization?:(1 2 3 4 5)' \\
'*-v[Verbose logging (may be specified more than once)]' \\
'*--verbose[Verbose logging (may be specified more than once)]' \\
'--version[Display Twisted version and exit.]' \\
&& return 0
"""

# with sub-commands
testOutput2 = b"""#compdef silly2

_arguments -s -A "-*" \\
'*::subcmd:->subcmd' \\
':output file (*):_files -g "*"' \\
"(--accuracy)-a[Select the level of accuracy (1-3)]:Accuracy'\\`?:(1 2 3)" \\
"(-a)--accuracy=[Select the level of accuracy (1-3)]:Accuracy'\\`?:(1 2 3)" \\
'(--another-param)-P[another-param]:another-param:_files' \\
'(-P)--another-param=[another-param]:another-param:_files' \\
'(--color --gray -g)-c[Color on]' \\
'(--gray -c -g)--color[Color on]' \\
'(--color --gray -c)-g[Turn on gray-scale output]' \\
'(--color -c -g)--gray[Turn on gray-scale output]' \\
'--help[Display this help and exit.]' \\
'--optimization=[Optimization level]:Optimization?:(1 2 3 4 5)' \\
'(--other-option)-o[other-option]' \\
'(-o)--other-option[other-option]' \\
'(--other-param)-p[other-param]:other-param:_files' \\
'(-p)--other-param=[other-param]:other-param:_files' \\
'--some-option[some-option]' \\
'--some-param=[some-param]:some-param:_files' \\
'*-v[Verbose logging (may be specified more than once)]' \\
'*--verbose[Verbose logging (may be specified more than once)]' \\
'--version[Display Twisted version and exit.]' \\
&& return 0
local _zsh_subcmds_array
_zsh_subcmds_array=(
"sub1:Sub Command 1"
"sub2:Sub Command 2"
)

_describe "sub-command" _zsh_subcmds_array
"""
