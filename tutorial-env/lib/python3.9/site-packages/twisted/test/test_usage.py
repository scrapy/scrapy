# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.usage}, a command line option parsing library.
"""


from twisted.python import usage
from twisted.trial import unittest


class WellBehaved(usage.Options):
    optParameters = [
        ["long", "w", "default", "and a docstring"],
        ["another", "n", "no docstring"],
        ["longonly", None, "noshort"],
        ["shortless", None, "except", "this one got docstring"],
    ]
    optFlags = [
        [
            "aflag",
            "f",
            """

                 flagallicious docstringness for this here

                 """,
        ],
        ["flout", "o"],
    ]

    def opt_myflag(self):
        self.opts["myflag"] = "PONY!"

    def opt_myparam(self, value):
        self.opts["myparam"] = f"{value} WITH A PONY!"


class ParseCorrectnessTests(unittest.TestCase):
    """
    Test L{usage.Options.parseOptions} for correct values under
    good conditions.
    """

    def setUp(self):
        """
        Instantiate and parseOptions a well-behaved Options class.
        """

        self.niceArgV = (
            "--long Alpha -n Beta " "--shortless Gamma -f --myflag " "--myparam Tofu"
        ).split()

        self.nice = WellBehaved()

        self.nice.parseOptions(self.niceArgV)

    def test_checkParameters(self):
        """
        Parameters have correct values.
        """
        self.assertEqual(self.nice.opts["long"], "Alpha")
        self.assertEqual(self.nice.opts["another"], "Beta")
        self.assertEqual(self.nice.opts["longonly"], "noshort")
        self.assertEqual(self.nice.opts["shortless"], "Gamma")

    def test_checkFlags(self):
        """
        Flags have correct values.
        """
        self.assertEqual(self.nice.opts["aflag"], 1)
        self.assertEqual(self.nice.opts["flout"], 0)

    def test_checkCustoms(self):
        """
        Custom flags and parameters have correct values.
        """
        self.assertEqual(self.nice.opts["myflag"], "PONY!")
        self.assertEqual(self.nice.opts["myparam"], "Tofu WITH A PONY!")


class TypedOptions(usage.Options):
    optParameters = [
        ["fooint", None, 392, "Foo int", int],
        ["foofloat", None, 4.23, "Foo float", float],
        ["eggint", None, None, "Egg int without default", int],
        ["eggfloat", None, None, "Egg float without default", float],
    ]

    def opt_under_score(self, value):
        """
        This option has an underscore in its name to exercise the _ to -
        translation.
        """
        self.underscoreValue = value

    opt_u = opt_under_score


class TypedTests(unittest.TestCase):
    """
    Test L{usage.Options.parseOptions} for options with forced types.
    """

    def setUp(self):
        self.usage = TypedOptions()

    def test_defaultValues(self):
        """
        Default values are parsed.
        """
        argV = []
        self.usage.parseOptions(argV)
        self.assertEqual(self.usage.opts["fooint"], 392)
        self.assertIsInstance(self.usage.opts["fooint"], int)
        self.assertEqual(self.usage.opts["foofloat"], 4.23)
        self.assertIsInstance(self.usage.opts["foofloat"], float)
        self.assertIsNone(self.usage.opts["eggint"])
        self.assertIsNone(self.usage.opts["eggfloat"])

    def test_parsingValues(self):
        """
        int and float values are parsed.
        """
        argV = ("--fooint 912 --foofloat -823.1 " "--eggint 32 --eggfloat 21").split()
        self.usage.parseOptions(argV)
        self.assertEqual(self.usage.opts["fooint"], 912)
        self.assertIsInstance(self.usage.opts["fooint"], int)
        self.assertEqual(self.usage.opts["foofloat"], -823.1)
        self.assertIsInstance(self.usage.opts["foofloat"], float)
        self.assertEqual(self.usage.opts["eggint"], 32)
        self.assertIsInstance(self.usage.opts["eggint"], int)
        self.assertEqual(self.usage.opts["eggfloat"], 21.0)
        self.assertIsInstance(self.usage.opts["eggfloat"], float)

    def test_underscoreOption(self):
        """
        A dash in an option name is translated to an underscore before being
        dispatched to a handler.
        """
        self.usage.parseOptions(["--under-score", "foo"])
        self.assertEqual(self.usage.underscoreValue, "foo")

    def test_underscoreOptionAlias(self):
        """
        An option name with a dash in it can have an alias.
        """
        self.usage.parseOptions(["-u", "bar"])
        self.assertEqual(self.usage.underscoreValue, "bar")

    def test_invalidValues(self):
        """
        Passing wrong values raises an error.
        """
        argV = "--fooint egg".split()
        self.assertRaises(usage.UsageError, self.usage.parseOptions, argV)


class WrongTypedOptions(usage.Options):
    optParameters = [["barwrong", None, None, "Bar with wrong coerce", "he"]]


class WeirdCallableOptions(usage.Options):
    def _bar(value):
        raise RuntimeError("Ouch")

    def _foo(value):
        raise ValueError("Yay")

    optParameters = [
        ["barwrong", None, None, "Bar with strange callable", _bar],
        ["foowrong", None, None, "Foo with strange callable", _foo],
    ]


class WrongTypedTests(unittest.TestCase):
    """
    Test L{usage.Options.parseOptions} for wrong coerce options.
    """

    def test_nonCallable(self):
        """
        Using a non-callable type fails.
        """
        us = WrongTypedOptions()
        argV = "--barwrong egg".split()
        self.assertRaises(TypeError, us.parseOptions, argV)

    def test_notCalledInDefault(self):
        """
        The coerce functions are not called if no values are provided.
        """
        us = WeirdCallableOptions()
        argV = []
        us.parseOptions(argV)

    def test_weirdCallable(self):
        """
        Errors raised by coerce functions are handled properly.
        """
        us = WeirdCallableOptions()
        argV = "--foowrong blah".split()
        # ValueError is swallowed as UsageError
        e = self.assertRaises(usage.UsageError, us.parseOptions, argV)
        self.assertEqual(str(e), "Parameter type enforcement failed: Yay")

        us = WeirdCallableOptions()
        argV = "--barwrong blah".split()
        # RuntimeError is not swallowed
        self.assertRaises(RuntimeError, us.parseOptions, argV)


class OutputTests(unittest.TestCase):
    def test_uppercasing(self):
        """
        Error output case adjustment does not mangle options
        """
        opt = WellBehaved()
        e = self.assertRaises(usage.UsageError, opt.parseOptions, ["-Z"])
        self.assertEqual(str(e), "option -Z not recognized")


class InquisitionOptions(usage.Options):
    optFlags = [
        ("expect", "e"),
    ]
    optParameters = [
        ("torture-device", "t", "comfy-chair", "set preferred torture device"),
    ]


class HolyQuestOptions(usage.Options):
    optFlags = [
        ("horseback", "h", "use a horse"),
        ("for-grail", "g"),
    ]


class SubCommandOptions(usage.Options):
    optFlags = [
        ("europian-swallow", None, "set default swallow type to Europian"),
    ]
    subCommands = [
        ("inquisition", "inquest", InquisitionOptions, "Perform an inquisition"),
        ("holyquest", "quest", HolyQuestOptions, "Embark upon a holy quest"),
    ]


class SubCommandTests(unittest.TestCase):
    """
    Test L{usage.Options.parseOptions} for options with subcommands.
    """

    def test_simpleSubcommand(self):
        """
        A subcommand is recognized.
        """
        o = SubCommandOptions()
        o.parseOptions(["--europian-swallow", "inquisition"])
        self.assertTrue(o["europian-swallow"])
        self.assertEqual(o.subCommand, "inquisition")
        self.assertIsInstance(o.subOptions, InquisitionOptions)
        self.assertFalse(o.subOptions["expect"])
        self.assertEqual(o.subOptions["torture-device"], "comfy-chair")

    def test_subcommandWithFlagsAndOptions(self):
        """
        Flags and options of a subcommand are assigned.
        """
        o = SubCommandOptions()
        o.parseOptions(["inquisition", "--expect", "--torture-device=feather"])
        self.assertFalse(o["europian-swallow"])
        self.assertEqual(o.subCommand, "inquisition")
        self.assertIsInstance(o.subOptions, InquisitionOptions)
        self.assertTrue(o.subOptions["expect"])
        self.assertEqual(o.subOptions["torture-device"], "feather")

    def test_subcommandAliasWithFlagsAndOptions(self):
        """
        Flags and options of a subcommand alias are assigned.
        """
        o = SubCommandOptions()
        o.parseOptions(["inquest", "--expect", "--torture-device=feather"])
        self.assertFalse(o["europian-swallow"])
        self.assertEqual(o.subCommand, "inquisition")
        self.assertIsInstance(o.subOptions, InquisitionOptions)
        self.assertTrue(o.subOptions["expect"])
        self.assertEqual(o.subOptions["torture-device"], "feather")

    def test_anotherSubcommandWithFlagsAndOptions(self):
        """
        Flags and options of another subcommand are assigned.
        """
        o = SubCommandOptions()
        o.parseOptions(["holyquest", "--for-grail"])
        self.assertFalse(o["europian-swallow"])
        self.assertEqual(o.subCommand, "holyquest")
        self.assertIsInstance(o.subOptions, HolyQuestOptions)
        self.assertFalse(o.subOptions["horseback"])
        self.assertTrue(o.subOptions["for-grail"])

    def test_noSubcommand(self):
        """
        If no subcommand is specified and no default subcommand is assigned,
        a subcommand will not be implied.
        """
        o = SubCommandOptions()
        o.parseOptions(["--europian-swallow"])
        self.assertTrue(o["europian-swallow"])
        self.assertIsNone(o.subCommand)
        self.assertFalse(hasattr(o, "subOptions"))

    def test_defaultSubcommand(self):
        """
        Flags and options in the default subcommand are assigned.
        """
        o = SubCommandOptions()
        o.defaultSubCommand = "inquest"
        o.parseOptions(["--europian-swallow"])
        self.assertTrue(o["europian-swallow"])
        self.assertEqual(o.subCommand, "inquisition")
        self.assertIsInstance(o.subOptions, InquisitionOptions)
        self.assertFalse(o.subOptions["expect"])
        self.assertEqual(o.subOptions["torture-device"], "comfy-chair")

    def test_subCommandParseOptionsHasParent(self):
        """
        The parseOptions method from the Options object specified for the
        given subcommand is called.
        """

        class SubOpt(usage.Options):
            def parseOptions(self, *a, **kw):
                self.sawParent = self.parent
                usage.Options.parseOptions(self, *a, **kw)

        class Opt(usage.Options):
            subCommands = [
                ("foo", "f", SubOpt, "bar"),
            ]

        o = Opt()
        o.parseOptions(["foo"])
        self.assertTrue(hasattr(o.subOptions, "sawParent"))
        self.assertEqual(o.subOptions.sawParent, o)

    def test_subCommandInTwoPlaces(self):
        """
        The .parent pointer is correct even when the same Options class is
        used twice.
        """

        class SubOpt(usage.Options):
            pass

        class OptFoo(usage.Options):
            subCommands = [
                ("foo", "f", SubOpt, "quux"),
            ]

        class OptBar(usage.Options):
            subCommands = [
                ("bar", "b", SubOpt, "quux"),
            ]

        oFoo = OptFoo()
        oFoo.parseOptions(["foo"])
        oBar = OptBar()
        oBar.parseOptions(["bar"])
        self.assertTrue(hasattr(oFoo.subOptions, "parent"))
        self.assertTrue(hasattr(oBar.subOptions, "parent"))
        self.failUnlessIdentical(oFoo.subOptions.parent, oFoo)
        self.failUnlessIdentical(oBar.subOptions.parent, oBar)


class HelpStringTests(unittest.TestCase):
    """
    Test generated help strings.
    """

    def setUp(self):
        """
        Instantiate a well-behaved Options class.
        """

        self.niceArgV = (
            "--long Alpha -n Beta " "--shortless Gamma -f --myflag " "--myparam Tofu"
        ).split()

        self.nice = WellBehaved()

    def test_noGoBoom(self):
        """
        __str__ shouldn't go boom.
        """
        try:
            self.nice.__str__()
        except Exception as e:
            self.fail(e)

    def test_whitespaceStripFlagsAndParameters(self):
        """
        Extra whitespace in flag and parameters docs is stripped.
        """
        # We test this by making sure aflag and it's help string are on the
        # same line.
        lines = [s for s in str(self.nice).splitlines() if s.find("aflag") >= 0]
        self.assertTrue(len(lines) > 0)
        self.assertTrue(lines[0].find("flagallicious") >= 0)


class PortCoerceTests(unittest.TestCase):
    """
    Test the behavior of L{usage.portCoerce}.
    """

    def test_validCoerce(self):
        """
        Test the answers with valid input.
        """
        self.assertEqual(0, usage.portCoerce("0"))
        self.assertEqual(3210, usage.portCoerce("3210"))
        self.assertEqual(65535, usage.portCoerce("65535"))

    def test_errorCoerce(self):
        """
        Test error path.
        """
        self.assertRaises(ValueError, usage.portCoerce, "")
        self.assertRaises(ValueError, usage.portCoerce, "-21")
        self.assertRaises(ValueError, usage.portCoerce, "212189")
        self.assertRaises(ValueError, usage.portCoerce, "foo")


class ZshCompleterTests(unittest.TestCase):
    """
    Test the behavior of the various L{twisted.usage.Completer} classes
    for producing output usable by zsh tab-completion system.
    """

    def test_completer(self):
        """
        Completer produces zsh shell-code that produces no completion matches.
        """
        c = usage.Completer()
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ":some-option:")

        c = usage.Completer(descr="some action", repeat=True)
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, "*:some action:")

    def test_files(self):
        """
        CompleteFiles produces zsh shell-code that completes file names
        according to a glob.
        """
        c = usage.CompleteFiles()
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ':some-option (*):_files -g "*"')

        c = usage.CompleteFiles("*.py")
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ':some-option (*.py):_files -g "*.py"')

        c = usage.CompleteFiles("*.py", descr="some action", repeat=True)
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, '*:some action (*.py):_files -g "*.py"')

    def test_dirs(self):
        """
        CompleteDirs produces zsh shell-code that completes directory names.
        """
        c = usage.CompleteDirs()
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ":some-option:_directories")

        c = usage.CompleteDirs(descr="some action", repeat=True)
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, "*:some action:_directories")

    def test_list(self):
        """
        CompleteList produces zsh shell-code that completes words from a fixed
        list of possibilities.
        """
        c = usage.CompleteList("ABC")
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ":some-option:(A B C)")

        c = usage.CompleteList(["1", "2", "3"])
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ":some-option:(1 2 3)")

        c = usage.CompleteList(["1", "2", "3"], descr="some action", repeat=True)
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, "*:some action:(1 2 3)")

    def test_multiList(self):
        """
        CompleteMultiList produces zsh shell-code that completes multiple
        comma-separated words from a fixed list of possibilities.
        """
        c = usage.CompleteMultiList("ABC")
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ":some-option:_values -s , 'some-option' A B C")

        c = usage.CompleteMultiList(["1", "2", "3"])
        got = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(got, ":some-option:_values -s , 'some-option' 1 2 3")

        c = usage.CompleteMultiList(["1", "2", "3"], descr="some action", repeat=True)
        got = c._shellCode("some-option", usage._ZSH)
        expected = "*:some action:_values -s , 'some action' 1 2 3"
        self.assertEqual(got, expected)

    def test_usernames(self):
        """
        CompleteUsernames produces zsh shell-code that completes system
        usernames.
        """
        c = usage.CompleteUsernames()
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, ":some-option:_users")

        c = usage.CompleteUsernames(descr="some action", repeat=True)
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, "*:some action:_users")

    def test_groups(self):
        """
        CompleteGroups produces zsh shell-code that completes system group
        names.
        """
        c = usage.CompleteGroups()
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, ":group:_groups")

        c = usage.CompleteGroups(descr="some action", repeat=True)
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, "*:some action:_groups")

    def test_hostnames(self):
        """
        CompleteHostnames produces zsh shell-code that completes hostnames.
        """
        c = usage.CompleteHostnames()
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, ":some-option:_hosts")

        c = usage.CompleteHostnames(descr="some action", repeat=True)
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, "*:some action:_hosts")

    def test_userAtHost(self):
        """
        CompleteUserAtHost produces zsh shell-code that completes hostnames or
        a word of the form <username>@<hostname>.
        """
        c = usage.CompleteUserAtHost()
        out = c._shellCode("some-option", usage._ZSH)
        self.assertTrue(out.startswith(":host | user@host:"))

        c = usage.CompleteUserAtHost(descr="some action", repeat=True)
        out = c._shellCode("some-option", usage._ZSH)
        self.assertTrue(out.startswith("*:some action:"))

    def test_netInterfaces(self):
        """
        CompleteNetInterfaces produces zsh shell-code that completes system
        network interface names.
        """
        c = usage.CompleteNetInterfaces()
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, ":some-option:_net_interfaces")

        c = usage.CompleteNetInterfaces(descr="some action", repeat=True)
        out = c._shellCode("some-option", usage._ZSH)
        self.assertEqual(out, "*:some action:_net_interfaces")


class CompleterNotImplementedTests(unittest.TestCase):
    """
    Using an unknown shell constant with the various Completer() classes
    should raise NotImplementedError
    """

    def test_unknownShell(self):
        """
        Using an unknown shellType should raise NotImplementedError
        """
        classes = [
            usage.Completer,
            usage.CompleteFiles,
            usage.CompleteDirs,
            usage.CompleteList,
            usage.CompleteMultiList,
            usage.CompleteUsernames,
            usage.CompleteGroups,
            usage.CompleteHostnames,
            usage.CompleteUserAtHost,
            usage.CompleteNetInterfaces,
        ]

        for cls in classes:
            try:
                action = cls()
            except BaseException:
                action = cls(None)
            self.assertRaises(
                NotImplementedError, action._shellCode, None, "bad_shell_type"
            )


class FlagFunctionTests(unittest.TestCase):
    """
    Tests for L{usage.flagFunction}.
    """

    class SomeClass:
        """
        Dummy class for L{usage.flagFunction} tests.
        """

        def oneArg(self, a):
            """
            A one argument method to be tested by L{usage.flagFunction}.

            @param a: a useless argument to satisfy the function's signature.
            """

        def noArg(self):
            """
            A no argument method to be tested by L{usage.flagFunction}.
            """

        def manyArgs(self, a, b, c):
            """
            A multiple arguments method to be tested by L{usage.flagFunction}.

            @param a: a useless argument to satisfy the function's signature.
            @param b: a useless argument to satisfy the function's signature.
            @param c: a useless argument to satisfy the function's signature.
            """

    def test_hasArg(self):
        """
        L{usage.flagFunction} returns C{False} if the method checked allows
        exactly one argument.
        """
        self.assertIs(False, usage.flagFunction(self.SomeClass().oneArg))

    def test_noArg(self):
        """
        L{usage.flagFunction} returns C{True} if the method checked allows
        exactly no argument.
        """
        self.assertIs(True, usage.flagFunction(self.SomeClass().noArg))

    def test_tooManyArguments(self):
        """
        L{usage.flagFunction} raises L{usage.UsageError} if the method checked
        allows more than one argument.
        """
        exc = self.assertRaises(
            usage.UsageError, usage.flagFunction, self.SomeClass().manyArgs
        )
        self.assertEqual("Invalid Option function for manyArgs", str(exc))

    def test_tooManyArgumentsAndSpecificErrorMessage(self):
        """
        L{usage.flagFunction} uses the given method name in the error message
        raised when the method allows too many arguments.
        """
        exc = self.assertRaises(
            usage.UsageError, usage.flagFunction, self.SomeClass().manyArgs, "flubuduf"
        )
        self.assertEqual("Invalid Option function for flubuduf", str(exc))


class OptionsInternalTests(unittest.TestCase):
    """
    Tests internal behavior of C{usage.Options}.
    """

    def test_optionsAliasesOrder(self):
        """
        Options which are synonyms to another option are aliases towards the
        longest option name.
        """

        class Opts(usage.Options):
            def opt_very_very_long(self):
                """
                This is an option method with a very long name, that is going to
                be aliased.
                """

            opt_short = opt_very_very_long
            opt_s = opt_very_very_long

        opts = Opts()

        self.assertEqual(
            dict.fromkeys(["s", "short", "very-very-long"], "very-very-long"),
            {
                "s": opts.synonyms["s"],
                "short": opts.synonyms["short"],
                "very-very-long": opts.synonyms["very-very-long"],
            },
        )
