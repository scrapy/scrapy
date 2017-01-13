from __future__ import division, absolute_import

from zope.interface import implementer

from twisted.trial.itrial import IReporter
from twisted.plugin import IPlugin



@implementer(IPlugin, IReporter)
class _Reporter(object):

    def __init__(self, name, module, description, longOpt, shortOpt, klass):
        self.name = name
        self.module = module
        self.description = description
        self.longOpt = longOpt
        self.shortOpt = shortOpt
        self.klass = klass


Tree = _Reporter("Tree Reporter",
                 "twisted.trial.reporter",
                 description="verbose color output (default reporter)",
                 longOpt="verbose",
                 shortOpt="v",
                 klass="TreeReporter")

BlackAndWhite = _Reporter("Black-And-White Reporter",
                          "twisted.trial.reporter",
                          description="Colorless verbose output",
                          longOpt="bwverbose",
                          shortOpt="o",
                          klass="VerboseTextReporter")

Minimal = _Reporter("Minimal Reporter",
                    "twisted.trial.reporter",
                    description="minimal summary output",
                    longOpt="summary",
                    shortOpt="s",
                    klass="MinimalReporter")

Classic = _Reporter("Classic Reporter",
                    "twisted.trial.reporter",
                    description="terse text output",
                    longOpt="text",
                    shortOpt="t",
                    klass="TextReporter")

Timing = _Reporter("Timing Reporter",
                   "twisted.trial.reporter",
                   description="Timing output",
                   longOpt="timing",
                   shortOpt=None,
                   klass="TimingTextReporter")

Subunit = _Reporter("Subunit Reporter",
                    "twisted.trial.reporter",
                    description="subunit output",
                    longOpt="subunit",
                    shortOpt=None,
                    klass="SubunitReporter")
