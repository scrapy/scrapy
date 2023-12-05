from zope.interface import implementer

from twisted.plugin import IPlugin
from twisted.trial.itrial import IReporter


@implementer(IPlugin, IReporter)
class _Reporter:
    def __init__(self, name, module, description, longOpt, shortOpt, klass):
        self.name = name
        self.module = module
        self.description = description
        self.longOpt = longOpt
        self.shortOpt = shortOpt
        self.klass = klass

    @property
    def stream(self):
        # IReporter.stream
        pass

    @property
    def tbformat(self):
        # IReporter.tbformat
        pass

    @property
    def args(self):
        # IReporter.args
        pass

    @property
    def shouldStop(self):
        # IReporter.shouldStop
        pass

    @property
    def separator(self):
        # IReporter.separator
        pass

    @property
    def testsRun(self):
        # IReporter.testsRun
        pass

    def addError(self, test, error):
        # IReporter.addError
        pass

    def addExpectedFailure(self, test, failure, todo=None):
        # IReporter.addExpectedFailure
        pass

    def addFailure(self, test, failure):
        # IReporter.addFailure
        pass

    def addSkip(self, test, reason):
        # IReporter.addSkip
        pass

    def addSuccess(self, test):
        # IReporter.addSuccess
        pass

    def addUnexpectedSuccess(self, test, todo=None):
        # IReporter.addUnexpectedSuccess
        pass

    def cleanupErrors(self, errs):
        # IReporter.cleanupErrors
        pass

    def done(self):
        # IReporter.done
        pass

    def endSuite(self, name):
        # IReporter.endSuite
        pass

    def printErrors(self):
        # IReporter.printErrors
        pass

    def printSummary(self):
        # IReporter.printSummary
        pass

    def startSuite(self, name):
        # IReporter.startSuite
        pass

    def startTest(self, method):
        # IReporter.startTest
        pass

    def stopTest(self, method):
        # IReporter.stopTest
        pass

    def upDownError(self, userMeth, warn=True, printStatus=True):
        # IReporter.upDownError
        pass

    def wasSuccessful(self):
        # IReporter.wasSuccessful
        pass

    def write(self, string):
        # IReporter.write
        pass

    def writeln(self, string):
        # IReporter.writeln
        pass


Tree = _Reporter(
    "Tree Reporter",
    "twisted.trial.reporter",
    description="verbose color output (default reporter)",
    longOpt="verbose",
    shortOpt="v",
    klass="TreeReporter",
)

BlackAndWhite = _Reporter(
    "Black-And-White Reporter",
    "twisted.trial.reporter",
    description="Colorless verbose output",
    longOpt="bwverbose",
    shortOpt="o",
    klass="VerboseTextReporter",
)

Minimal = _Reporter(
    "Minimal Reporter",
    "twisted.trial.reporter",
    description="minimal summary output",
    longOpt="summary",
    shortOpt="s",
    klass="MinimalReporter",
)

Classic = _Reporter(
    "Classic Reporter",
    "twisted.trial.reporter",
    description="terse text output",
    longOpt="text",
    shortOpt="t",
    klass="TextReporter",
)

Timing = _Reporter(
    "Timing Reporter",
    "twisted.trial.reporter",
    description="Timing output",
    longOpt="timing",
    shortOpt=None,
    klass="TimingTextReporter",
)

Subunit = _Reporter(
    "Subunit Reporter",
    "twisted.trial.reporter",
    description="subunit output",
    longOpt="subunit",
    shortOpt=None,
    klass="SubunitReporter",
)
