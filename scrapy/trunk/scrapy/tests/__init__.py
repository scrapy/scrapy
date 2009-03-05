"""
scrapy.tests: this package contains all Scrapy unittests

To run all Scrapy unittests type: 

    python -m scrapy.tests

Keep in mind that some tests may be skipped if you don't have a MySQL database
up and configured appropriately.
"""

if __name__ == '__main__':
    import os
    from twisted.trial import runner, reporter

    os.environ['SCRAPY_SETTINGS_DISABLED'] = '1'
    loader = runner.TestLoader()
    runner = runner.TrialRunner(reporter.TreeReporter)
    suite = loader.loadByNames(['scrapy'], recurse=True)
    runner.run(suite)
