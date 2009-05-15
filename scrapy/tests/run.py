"""
Module to run Scrapy tests - see scrapy.tests docstring
"""

if __name__ == '__main__':
    import os, sys
    from twisted.trial import runner, reporter

    tests_to_run = sys.argv[1:] or ['scrapy']

    os.environ['SCRAPY_SETTINGS_DISABLED'] = '1'
    loader = runner.TestLoader()
    runner = runner.TrialRunner(reporter.TreeReporter)
    suite = loader.loadByNames(tests_to_run, recurse=True)
    runner.run(suite)
