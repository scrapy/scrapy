"""
Module to run Scrapy tests - see scrapy.tests docstring
"""

if __name__ == '__main__':
    import os
    from twisted.trial import runner, reporter

    os.environ['SCRAPY_SETTINGS_DISABLED'] = '1'
    loader = runner.TestLoader()
    runner = runner.TrialRunner(reporter.TreeReporter)
    suite = loader.loadByNames(['scrapy'], recurse=True)
    runner.run(suite)
