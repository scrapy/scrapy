# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Unit tests for the Trial unit-testing framework.
"""

from hypothesis import HealthCheck, settings


def _activateHypothesisProfile():
    """
    Load a Hypothesis profile appropriate for a Twisted test suite.
    """
    deterministic = settings(
        # Disable the deadline.  It is too hard to guarantee that a particular
        # piece of Python code will always run in less than some fixed amount
        # of time.  Hardware capabilities, the OS scheduler, the Python
        # garbage collector, and other factors all combine to make substantial
        # outliers possible.  Such failures are a distraction from development
        # and a hassle on continuous integration environments.
        deadline=None,
        suppress_health_check=[
            # With the same reasoning as above, disable the Hypothesis time
            # limit on data generation by example search strategies.
            HealthCheck.too_slow,
        ],
        # When a developer is working on one set of changes, or continuous
        # integration system is testing them, it is disruptive for Hypothesis
        # to discover a bug in pre-existing code.  This is just what
        # Hypothesis will do by default, by exploring a pseudo-randomly
        # different set of examples each time.  Such failures are a
        # distraction from development and a hassle in continuous integration
        # environments.
        derandomize=True,
    )

    settings.register_profile("twisted_trial_test_profile_deterministic", deterministic)
    settings.load_profile("twisted_trial_test_profile_deterministic")


_activateHypothesisProfile()
