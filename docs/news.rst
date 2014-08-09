.. _news:

Release notes
=============

0.24.4 (2014-08-09)
-------------------

- pem file is used by mockserver and required by scrapy bench (:commit:`5eddc68`)
- scrapy bench needs scrapy.tests* (:commit:`d6cb999`)

0.24.3 (2014-08-09)
-------------------

- no need to waste travis-ci time on py3 for 0.24 (:commit:`8e080c1`)
- Update installation docs (:commit:`1d0c096`)
- There is a trove classifier for Scrapy framework! (:commit:`4c701d7`)
- update other places where w3lib version is mentioned (:commit:`d109c13`)
- Update w3lib requirement to 1.8.0 (:commit:`39d2ce5`)
- Use w3lib.html.replace_entities() (remove_entities() is deprecated) (:commit:`180d3ad`)
- set zip_safe=False (:commit:`a51ee8b`)
- do not ship tests package (:commit:`ee3b371`)
- scrapy.bat is not needed anymore (:commit:`c3861cf`)
- Modernize setup.py (:commit:`362e322`)
- headers can not handle non-string values (:commit:`94a5c65`)
- fix ftp test cases (:commit:`a274a7f`)
- The sum up of travis-ci builds are taking like 50min to complete (:commit:`ae1e2cc`)
- Update shell.rst typo (:commit:`e49c96a`)
- removes weird indentation in the shell results (:commit:`1ca489d`)
- improved explanations, clarified blog post as source, added link for XPath string functions in the spec (:commit:`65c8f05`)
- renamed UserTimeoutError and ServerTimeouterror #583 (:commit:`037f6ab`)
- adding some xpath tips to selectors docs (:commit:`2d103e0`)
- fix tests to account for https://github.com/scrapy/w3lib/pull/23 (:commit:`f8d366a`)
- get_func_args maximum recursion fix #728 (:commit:`81344ea`)
- Updated input/ouput processor example according to #560. (:commit:`f7c4ea8`)
- Fixed Python syntax in tutorial. (:commit:`db59ed9`)
- Add test case for tunneling proxy (:commit:`f090260`)
- Bugfix for leaking Proxy-Authorization header to remote host when using tunneling (:commit:`d8793af`)
- Extract links from XHTML documents with MIME-Type "application/xml" (:commit:`ed1f376`)
- Merge pull request #793 from roysc/patch-1 (:commit:`91a1106`)
- Fix typo in commands.rst (:commit:`743e1e2`)
- better testcase for settings.overrides.setdefault (:commit:`e22daaf`)
- Using CRLF as line marker according to http 1.1 definition (:commit:`5ec430b`)

0.24.2 (2014-07-08)
-------------------

- Use a mutable mapping to proxy deprecated settings.overrides and settings.defaults attribute (:commit:`e5e8133`)
- there is not support for python3 yet (:commit:`3cd6146`)
- Update python compatible version set to debian packages (:commit:`fa5d76b`)
- DOC fix formatting in release notes (:commit:`c6a9e20`)

0.24.1 (2014-06-27)
-------------------

- Fix deprecated CrawlerSettings and increase backwards compatibility with
  .defaults attribute (:commit:`8e3f20a`)


0.24.0 (2014-06-26)
-------------------

Enhancements
~~~~~~~~~~~~

- Improve Scrapy top-level namespace (:issue:`494`, :issue:`684`)
- Add selector shortcuts to responses (:issue:`554`, :issue:`690`)
- Add new lxml based LinkExtractor to replace unmantained SgmlLinkExtractor
  (:issue:`559`, :issue:`761`, :issue:`763`)
- Cleanup settings API - part of per-spider settings **GSoC project** (:issue:`737`)
- Add UTF8 encoding header to templates (:issue:`688`, :issue:`762`)
- Telnet console now binds to 127.0.0.1 by default (:issue:`699`)
- Update debian/ubuntu install instructions (:issue:`509`, :issue:`549`)
- Disable smart strings in lxml XPath evaluations (:issue:`535`)
- Restore filesystem based cache as default for http
  cache middleware (:issue:`541`, :issue:`500`, :issue:`571`)
- Expose current crawler in Scrapy shell (:issue:`557`)
- Improve testsuite comparing CSV and XML exporters (:issue:`570`)
- New `offsite/filtered` and `offsite/domains` stats (:issue:`566`)
- Support process_links as generator in CrawlSpider (:issue:`555`)
- Verbose logging and new stats counters for DupeFilter (:issue:`553`)
- Add a mimetype parameter to `MailSender.send()` (:issue:`602`)
- Generalize file pipeline log messages (:issue:`622`)
- Replace unencodeable codepoints with html entities in SGMLLinkExtractor (:issue:`565`)
- Converted SEP documents to rst format (:issue:`629`, :issue:`630`,
  :issue:`638`, :issue:`632`, :issue:`636`, :issue:`640`, :issue:`635`,
  :issue:`634`, :issue:`639`, :issue:`637`, :issue:`631`, :issue:`633`,
  :issue:`641`, :issue:`642`)
- Tests and docs for clickdata's nr index in FormRequest (:issue:`646`, :issue:`645`)
- Allow to disable a downloader handler just like any other component (:issue:`650`)
- Log when a request is discarded after too many redirections (:issue:`654`)
- Log error responses if they are not handled by spider callbacks
  (:issue:`612`, :issue:`656`)
- Add content-type check to http compression mw (:issue:`193`, :issue:`660`)
- Run pypy tests using latest pypi from ppa (:issue:`674`)
- Run test suite using pytest instead of trial (:issue:`679`)
- Build docs and check for dead links in tox environment (:issue:`687`)
- Make scrapy.version_info a tuple of integers (:issue:`681`, :issue:`692`)
- Infer exporter's output format from filename extensions
  (:issue:`546`, :issue:`659`, :issue:`760`)
- Support case-insensitive domains in `url_is_from_any_domain()` (:issue:`693`)
- Remove pep8 warnings in project and spider templates (:issue:`698`)
- Tests and docs for `request_fingerprint` function (:issue:`597`)
- Update SEP-19 for GSoC project `per-spider settings` (:issue:`705`)
- Set exit code to non-zero when contracts fails (:issue:`727`)
- Add a setting to control what class is instanciated as Downloader component
  (:issue:`738`)
- Pass response in `item_dropped` signal (:issue:`724`)
- Improve `scrapy check` contracts command (:issue:`733`, :issue:`752`)
- Document `spider.closed()` shortcut (:issue:`719`)
- Document `request_scheduled` signal (:issue:`746`)
- Add a note about reporting security issues (:issue:`697`)
- Add LevelDB http cache storage backend (:issue:`626`, :issue:`500`)
- Sort spider list output of `scrapy list` command (:issue:`742`) 
- Multiple documentation enhancemens and fixes
  (:issue:`575`, :issue:`587`, :issue:`590`, :issue:`596`, :issue:`610`,
  :issue:`617`, :issue:`618`, :issue:`627`, :issue:`613`, :issue:`643`,
  :issue:`654`, :issue:`675`, :issue:`663`, :issue:`711`, :issue:`714`)

Bugfixes
~~~~~~~~

- Encode unicode URL value when creating Links in RegexLinkExtractor (:issue:`561`)
- Ignore None values in ItemLoader processors (:issue:`556`)
- Fix link text when there is an inner tag in SGMLLinkExtractor and
  HtmlParserLinkExtractor (:issue:`485`, :issue:`574`)
- Fix wrong checks on subclassing of deprecated classes
  (:issue:`581`, :issue:`584`)
- Handle errors caused by inspect.stack() failures (:issue:`582`)
- Fix a reference to unexistent engine attribute (:issue:`593`, :issue:`594`)
- Fix dynamic itemclass example usage of type() (:issue:`603`)
- Use lucasdemarchi/codespell to fix typos (:issue:`628`)
- Fix default value of attrs argument in SgmlLinkExtractor to be tuple (:issue:`661`)
- Fix XXE flaw in sitemap reader (:issue:`676`)
- Fix engine to support filtered start requests (:issue:`707`)
- Fix offsite middleware case on urls with no hostnames (:issue:`745`)
- Testsuite doesn't require PIL anymore (:issue:`585`)


0.22.2 (released 2014-02-14)
----------------------------

- fix a reference to unexistent engine.slots. closes #593 (:commit:`13c099a`)
- downloaderMW doc typo (spiderMW doc copy remnant) (:commit:`8ae11bf`)
- Correct typos (:commit:`1346037`)

0.22.1 (released 2014-02-08)
----------------------------

- localhost666 can resolve under certain circumstances (:commit:`2ec2279`)
- test inspect.stack failure (:commit:`cc3eda3`)
- Handle cases when inspect.stack() fails (:commit:`8cb44f9`)
- Fix wrong checks on subclassing of deprecated classes. closes #581 (:commit:`46d98d6`)
- Docs: 4-space indent for final spider example (:commit:`13846de`)
- Fix HtmlParserLinkExtractor and tests after #485 merge (:commit:`368a946`)
- BaseSgmlLinkExtractor: Fixed the missing space when the link has an inner tag (:commit:`b566388`)
- BaseSgmlLinkExtractor: Added unit test of a link with an inner tag (:commit:`c1cb418`)
- BaseSgmlLinkExtractor: Fixed unknown_endtag() so that it only set current_link=None when the end tag match the opening tag (:commit:`7e4d627`)
- Fix tests for Travis-CI build (:commit:`76c7e20`)
- replace unencodeable codepoints with html entities. fixes #562 and #285 (:commit:`5f87b17`)
- RegexLinkExtractor: encode URL unicode value when creating Links (:commit:`d0ee545`)
- Updated the tutorial crawl output with latest output. (:commit:`8da65de`)
- Updated shell docs with the crawler reference and fixed the actual shell output. (:commit:`875b9ab`)
- PEP8 minor edits. (:commit:`f89efaf`)
- Expose current crawler in the scrapy shell. (:commit:`5349cec`)
- Unused re import and PEP8 minor edits. (:commit:`387f414`)
- Ignore None's values when using the ItemLoader. (:commit:`0632546`)
- DOC Fixed HTTPCACHE_STORAGE typo in the default value which is now Filesystem instead Dbm. (:commit:`cde9a8c`)
- show ubuntu setup instructions as literal code (:commit:`fb5c9c5`)
- Update Ubuntu installation instructions (:commit:`70fb105`)
- Merge pull request #550 from stray-leone/patch-1 (:commit:`6f70b6a`)
- modify the version of scrapy ubuntu package (:commit:`725900d`)
- fix 0.22.0 release date (:commit:`af0219a`)
- fix typos in news.rst and remove (not released yet) header (:commit:`b7f58f4`)

0.22.0 (released 2014-01-17)
----------------------------

Enhancements
~~~~~~~~~~~~

- [**Backwards incompatible**] Switched HTTPCacheMiddleware backend to filesystem (:issue:`541`)
  To restore old backend set `HTTPCACHE_STORAGE` to `scrapy.contrib.httpcache.DbmCacheStorage`
- Proxy \https:// urls using CONNECT method (:issue:`392`, :issue:`397`)
- Add a middleware to crawl ajax crawleable pages as defined by google (:issue:`343`)
- Rename scrapy.spider.BaseSpider to scrapy.spider.Spider (:issue:`510`, :issue:`519`)
- Selectors register EXSLT namespaces by default (:issue:`472`)
- Unify item loaders similar to selectors renaming (:issue:`461`)
- Make `RFPDupeFilter` class easily subclassable (:issue:`533`)
- Improve test coverage and forthcoming Python 3 support (:issue:`525`)
- Promote startup info on settings and middleware to INFO level (:issue:`520`)
- Support partials in `get_func_args` util (:issue:`506`, issue:`504`)
- Allow running indiviual tests via tox (:issue:`503`)
- Update extensions ignored by link extractors (:issue:`498`)
- Add middleware methods to get files/images/thumbs paths (:issue:`490`)
- Improve offsite middleware tests (:issue:`478`)
- Add a way to skip default Referer header set by RefererMiddleware (:issue:`475`)
- Do not send `x-gzip` in default `Accept-Encoding` header (:issue:`469`)
- Support defining http error handling using settings (:issue:`466`)
- Use modern python idioms wherever you find legacies (:issue:`497`)
- Improve and correct documentation
  (:issue:`527`, :issue:`524`, :issue:`521`, :issue:`517`, :issue:`512`, :issue:`505`,
  :issue:`502`, :issue:`489`, :issue:`465`, :issue:`460`, :issue:`425`, :issue:`536`)

Fixes
~~~~~

- Update Selector class imports in CrawlSpider template (:issue:`484`)
- Fix unexistent reference to `engine.slots` (:issue:`464`)
- Do not try to call `body_as_unicode()` on a non-TextResponse instance (:issue:`462`)
- Warn when subclassing XPathItemLoader, previously it only warned on
  instantiation. (:issue:`523`)
- Warn when subclassing XPathSelector, previously it only warned on
  instantiation. (:issue:`537`)
- Multiple fixes to memory stats (:issue:`531`, :issue:`530`, :issue:`529`)
- Fix overriding url in `FormRequest.from_response()` (:issue:`507`)
- Fix tests runner under pip 1.5 (:issue:`513`)
- Fix logging error when spider name is unicode (:issue:`479`)

0.20.2 (released 2013-12-09)
----------------------------

- Update CrawlSpider Template with Selector changes (:commit:`6d1457d`)
- fix method name in tutorial. closes GH-480 (:commit:`b4fc359`

0.20.1 (released 2013-11-28)
----------------------------

- include_package_data is required to build wheels from published sources (:commit:`5ba1ad5`)
- process_parallel was leaking the failures on its internal deferreds.  closes #458 (:commit:`419a780`)

0.20.0 (released 2013-11-08)
----------------------------

Enhancements
~~~~~~~~~~~~

- New Selector's API including CSS selectors (:issue:`395` and :issue:`426`),
- Request/Response url/body attributes are now immutable
  (modifying them had been deprecated for a long time)
- :setting:`ITEM_PIPELINES` is now defined as a dict (instead of a list)
- Sitemap spider can fetch alternate URLs (:issue:`360`)
- `Selector.remove_namespaces()` now remove namespaces from element's attributes. (:issue:`416`)
- Paved the road for Python 3.3+ (:issue:`435`, :issue:`436`, :issue:`431`, :issue:`452`)
- New item exporter using native python types with nesting support (:issue:`366`)
- Tune HTTP1.1 pool size so it matches concurrency defined by settings (:commit:`b43b5f575`)
- scrapy.mail.MailSender now can connect over TLS or upgrade using STARTTLS (:issue:`327`)
- New FilesPipeline with functionality factored out from ImagesPipeline (:issue:`370`, :issue:`409`)
- Recommend Pillow instead of PIL for image handling (:issue:`317`)
- Added debian packages for Ubuntu quantal and raring (:commit:`86230c0`)
- Mock server (used for tests) can listen for HTTPS requests (:issue:`410`)
- Remove multi spider support from multiple core components
  (:issue:`422`, :issue:`421`, :issue:`420`, :issue:`419`, :issue:`423`, :issue:`418`)
- Travis-CI now tests Scrapy changes against development versions of `w3lib` and `queuelib` python packages.
- Add pypy 2.1 to continuous integration tests (:commit:`ecfa7431`)
- Pylinted, pep8 and removed old-style exceptions from source (:issue:`430`, :issue:`432`)
- Use importlib for parametric imports (:issue:`445`)
- Handle a regression introduced in Python 2.7.5 that affects XmlItemExporter (:issue:`372`)
- Bugfix crawling shutdown on SIGINT (:issue:`450`)
- Do not submit `reset` type inputs in FormRequest.from_response (:commit:`b326b87`)
- Do not silence download errors when request errback raises an exception (:commit:`684cfc0`)

Bugfixes
~~~~~~~~

- Fix tests under Django 1.6 (:commit:`b6bed44c`)
- Lot of bugfixes to retry middleware under disconnections using HTTP 1.1 download handler
- Fix inconsistencies among Twisted releases (:issue:`406`)
- Fix scrapy shell bugs (:issue:`418`, :issue:`407`)
- Fix invalid variable name in setup.py (:issue:`429`)
- Fix tutorial references (:issue:`387`)
- Improve request-response docs (:issue:`391`)
- Improve best practices docs (:issue:`399`, :issue:`400`, :issue:`401`, :issue:`402`)
- Improve django integration docs (:issue:`404`)
- Document `bindaddress` request meta (:commit:`37c24e01d7`)
- Improve `Request` class documentation (:issue:`226`)

Other
~~~~~

- Dropped Python 2.6 support (:issue:`448`)
- Add `cssselect`_ python package as install dependency
- Drop libxml2 and multi selector's backend support, `lxml`_ is required from now on.
- Minimum Twisted version increased to 10.0.0, dropped Twisted 8.0 support.
- Running test suite now requires `mock` python library (:issue:`390`)


Thanks
~~~~~~

Thanks to everyone who contribute to this release!

List of contributors sorted by number of commits::

     69 Daniel Graña <dangra@...>
     37 Pablo Hoffman <pablo@...>
     13 Mikhail Korobov <kmike84@...>
      9 Alex Cepoi <alex.cepoi@...>
      9 alexanderlukanin13 <alexander.lukanin.13@...>
      8 Rolando Espinoza La fuente <darkrho@...>
      8 Lukasz Biedrycki <lukasz.biedrycki@...>
      6 Nicolas Ramirez <nramirez.uy@...>
      3 Paul Tremberth <paul.tremberth@...>
      2 Martin Olveyra <molveyra@...>
      2 Stefan <misc@...>
      2 Rolando Espinoza <darkrho@...>
      2 Loren Davie <loren@...>
      2 irgmedeiros <irgmedeiros@...>
      1 Stefan Koch <taikano@...>
      1 Stefan <cct@...>
      1 scraperdragon <dragon@...>
      1 Kumara Tharmalingam <ktharmal@...>
      1 Francesco Piccinno <stack.box@...>
      1 Marcos Campal <duendex@...>
      1 Dragon Dave <dragon@...>
      1 Capi Etheriel <barraponto@...>
      1 cacovsky <amarquesferraz@...>
      1 Berend Iwema <berend@...>

0.18.4 (released 2013-10-10)
----------------------------

- IPython refuses to update the namespace. fix #396 (:commit:`3d32c4f`)
- Fix AlreadyCalledError replacing a request in shell command. closes #407 (:commit:`b1d8919`)
- Fix start_requests laziness and early hangs (:commit:`89faf52`)

0.18.3 (released 2013-10-03)
----------------------------

- fix regression on lazy evaluation of start requests (:commit:`12693a5`)
- forms: do not submit reset inputs (:commit:`e429f63`)
- increase unittest timeouts to decrease travis false positive failures (:commit:`912202e`)
- backport master fixes to json exporter (:commit:`cfc2d46`)
- Fix permission and set umask before generating sdist tarball (:commit:`06149e0`)

0.18.2 (released 2013-09-03)
----------------------------

- Backport `scrapy check` command fixes and backward compatible multi
  crawler process(:issue:`339`)

0.18.1 (released 2013-08-27)
----------------------------

- remove extra import added by cherry picked changes (:commit:`d20304e`)
- fix crawling tests under twisted pre 11.0.0 (:commit:`1994f38`)
- py26 can not format zero length fields {} (:commit:`abf756f`)
- test PotentiaDataLoss errors on unbound responses (:commit:`b15470d`)
- Treat responses without content-length or Transfer-Encoding as good responses (:commit:`c4bf324`)
- do no include ResponseFailed if http11 handler is not enabled (:commit:`6cbe684`)
- New HTTP client wraps connection losts in ResponseFailed exception. fix #373 (:commit:`1a20bba`)
- limit travis-ci build matrix (:commit:`3b01bb8`)
- Merge pull request #375 from peterarenot/patch-1 (:commit:`fa766d7`)
- Fixed so it refers to the correct folder (:commit:`3283809`)
- added quantal & raring to support ubuntu releases (:commit:`1411923`)
- fix retry middleware which didn't retry certain connection errors after the upgrade to http1 client, closes GH-373 (:commit:`bb35ed0`)
- fix XmlItemExporter in Python 2.7.4 and 2.7.5 (:commit:`de3e451`)
- minor updates to 0.18 release notes (:commit:`c45e5f1`)
- fix contributters list format (:commit:`0b60031`)

0.18.0 (released 2013-08-09)
----------------------------

- Lot of improvements to testsuite run using Tox, including a way to test on pypi
- Handle GET parameters for AJAX crawleable urls (:commit:`3fe2a32`)
- Use lxml recover option to parse sitemaps (:issue:`347`)
- Bugfix cookie merging by hostname and not by netloc (:issue:`352`)
- Support disabling `HttpCompressionMiddleware` using a flag setting (:issue:`359`)
- Support xml namespaces using `iternodes` parser in `XMLFeedSpider` (:issue:`12`)
- Support `dont_cache` request meta flag (:issue:`19`)
- Bugfix `scrapy.utils.gz.gunzip` broken by changes in python 2.7.4 (:commit:`4dc76e`)
- Bugfix url encoding on `SgmlLinkExtractor` (:issue:`24`)
- Bugfix `TakeFirst` processor shouldn't discard zero (0) value (:issue:`59`)
- Support nested items in xml exporter (:issue:`66`)
- Improve cookies handling performance (:issue:`77`)
- Log dupe filtered requests once (:issue:`105`)
- Split redirection middleware into status and meta based middlewares (:issue:`78`)
- Use HTTP1.1 as default downloader handler (:issue:`109` and :issue:`318`)
- Support xpath form selection on `FormRequest.from_response` (:issue:`185`)
- Bugfix unicode decoding error on `SgmlLinkExtractor` (:issue:`199`)
- Bugfix signal dispatching on pypi interpreter (:issue:`205`)
- Improve request delay and concurrency handling (:issue:`206`)
- Add RFC2616 cache policy to `HttpCacheMiddleware` (:issue:`212`)
- Allow customization of messages logged by engine (:issue:`214`)
- Multiples improvements to `DjangoItem` (:issue:`217`, :issue:`218`, :issue:`221`)
- Extend Scrapy commands using setuptools entry points (:issue:`260`)
- Allow spider `allowed_domains` value to be set/tuple (:issue:`261`)
- Support `settings.getdict` (:issue:`269`)
- Simplify internal `scrapy.core.scraper` slot handling (:issue:`271`)
- Added `Item.copy` (:issue:`290`)
- Collect idle downloader slots (:issue:`297`)
- Add `ftp://` scheme downloader handler (:issue:`329`)
- Added downloader benchmark webserver and spider tools :ref:`benchmarking`
- Moved persistent (on disk) queues to a separate project (queuelib_) which scrapy now depends on
- Add scrapy commands using external libraries (:issue:`260`)
- Added ``--pdb`` option to ``scrapy`` command line tool
- Added :meth:`XPathSelector.remove_namespaces` which allows to remove all namespaces from XML documents for convenience (to work with namespace-less XPaths). Documented in :ref:`topics-selectors`.
- Several improvements to spider contracts
- New default middleware named MetaRefreshMiddldeware that handles meta-refresh html tag redirections,
- MetaRefreshMiddldeware and RedirectMiddleware have different priorities to address #62
- added from_crawler method to spiders
- added system tests with mock server
- more improvements to Mac OS compatibility (thanks Alex Cepoi)
- several more cleanups to singletons and multi-spider support (thanks Nicolas Ramirez)
- support custom download slots
- added --spider option to "shell" command.
- log overridden settings when scrapy starts

Thanks to everyone who contribute to this release. Here is a list of
contributors sorted by number of commits::

    130 Pablo Hoffman <pablo@...>
     97 Daniel Graña <dangra@...>
     20 Nicolás Ramírez <nramirez.uy@...>
     13 Mikhail Korobov <kmike84@...>
     12 Pedro Faustino <pedrobandim@...>
     11 Steven Almeroth <sroth77@...>
      5 Rolando Espinoza La fuente <darkrho@...>
      4 Michal Danilak <mimino.coder@...>
      4 Alex Cepoi <alex.cepoi@...>
      4 Alexandr N Zamaraev (aka tonal) <tonal@...>
      3 paul <paul.tremberth@...>
      3 Martin Olveyra <molveyra@...>
      3 Jordi Llonch <llonchj@...>
      3 arijitchakraborty <myself.arijit@...>
      2 Shane Evans <shane.evans@...>
      2 joehillen <joehillen@...>
      2 Hart <HartSimha@...>
      2 Dan <ellisd23@...>
      1 Zuhao Wan <wanzuhao@...>
      1 whodatninja <blake@...>
      1 vkrest <v.krestiannykov@...>
      1 tpeng <pengtaoo@...>
      1 Tom Mortimer-Jones <tom@...>
      1 Rocio Aramberri <roschegel@...>
      1 Pedro <pedro@...>
      1 notsobad <wangxiaohugg@...>
      1 Natan L <kuyanatan.nlao@...>
      1 Mark Grey <mark.grey@...>
      1 Luan <luanpab@...>
      1 Libor Nenadál <libor.nenadal@...>
      1 Juan M Uys <opyate@...>
      1 Jonas Brunsgaard <jonas.brunsgaard@...>
      1 Ilya Baryshev <baryshev@...>
      1 Hasnain Lakhani <m.hasnain.lakhani@...>
      1 Emanuel Schorsch <emschorsch@...>
      1 Chris Tilden <chris.tilden@...>
      1 Capi Etheriel <barraponto@...>
      1 cacovsky <amarquesferraz@...>
      1 Berend Iwema <berend@...>


0.16.5 (released 2013-05-30)
----------------------------

- obey request method when scrapy deploy is redirected to a new endpoint (:commit:`8c4fcee`)
- fix inaccurate downloader middleware documentation. refs #280 (:commit:`40667cb`)
- doc: remove links to diveintopython.org, which is no longer available. closes #246 (:commit:`bd58bfa`)
- Find form nodes in invalid html5 documents (:commit:`e3d6945`)
- Fix typo labeling attrs type bool instead of list (:commit:`a274276`)

0.16.4 (released 2013-01-23)
----------------------------

- fixes spelling errors in documentation (:commit:`6d2b3aa`)
- add doc about disabling an extension. refs #132 (:commit:`c90de33`)
- Fixed error message formatting. log.err() doesn't support cool formatting and when error occurred, the message was:    "ERROR: Error processing %(item)s" (:commit:`c16150c`)
- lint and improve images pipeline error logging (:commit:`56b45fc`)
- fixed doc typos (:commit:`243be84`)
- add documentation topics: Broad Crawls & Common Practies (:commit:`1fbb715`)
- fix bug in scrapy parse command when spider is not specified explicitly. closes #209 (:commit:`c72e682`)
- Update docs/topics/commands.rst (:commit:`28eac7a`)

0.16.3 (released 2012-12-07)
----------------------------

- Remove concurrency limitation when using download delays and still ensure inter-request delays are enforced (:commit:`487b9b5`)
- add error details when image pipeline fails (:commit:`8232569`)
- improve mac os compatibility (:commit:`8dcf8aa`)
- setup.py: use README.rst to populate long_description (:commit:`7b5310d`)
- doc: removed obsolete references to ClientForm (:commit:`80f9bb6`)
- correct docs for default storage backend (:commit:`2aa491b`)
- doc: removed broken proxyhub link from FAQ (:commit:`bdf61c4`)
- Fixed docs typo in SpiderOpenCloseLogging example (:commit:`7184094`)


0.16.2 (released 2012-11-09)
----------------------------

- scrapy contracts: python2.6 compat (:commit:`a4a9199`)
- scrapy contracts verbose option (:commit:`ec41673`)
- proper unittest-like output for scrapy contracts (:commit:`86635e4`)
- added open_in_browser to debugging doc (:commit:`c9b690d`)
- removed reference to global scrapy stats from settings doc (:commit:`dd55067`)
- Fix SpiderState bug in Windows platforms (:commit:`58998f4`)


0.16.1 (released 2012-10-26)
----------------------------

- fixed LogStats extension, which got broken after a wrong merge before the 0.16 release (:commit:`8c780fd`)
- better backwards compatibility for scrapy.conf.settings (:commit:`3403089`)
- extended documentation on how to access crawler stats from extensions (:commit:`c4da0b5`)
- removed .hgtags (no longer needed now that scrapy uses git) (:commit:`d52c188`)
- fix dashes under rst headers (:commit:`fa4f7f9`)
- set release date for 0.16.0 in news (:commit:`e292246`)


0.16.0 (released 2012-10-18)
----------------------------

Scrapy changes:

- added :ref:`topics-contracts`, a mechanism for testing spiders in a formal/reproducible way
- added options ``-o`` and ``-t`` to the :command:`runspider` command
- documented :doc:`topics/autothrottle` and added to extensions installed by default. You still need to enable it with :setting:`AUTOTHROTTLE_ENABLED`
- major Stats Collection refactoring: removed separation of global/per-spider stats, removed stats-related signals (``stats_spider_opened``, etc). Stats are much simpler now, backwards compatibility is kept on the Stats Collector API and signals.
- added :meth:`~scrapy.contrib.spidermiddleware.SpiderMiddleware.process_start_requests` method to spider middlewares
- dropped Signals singleton. Signals should now be accesed through the Crawler.signals attribute. See the signals documentation for more info.
- dropped Signals singleton. Signals should now be accesed through the Crawler.signals attribute. See the signals documentation for more info.
- dropped Stats Collector singleton. Stats can now be accessed through the Crawler.stats attribute. See the stats collection documentation for more info.
- documented :ref:`topics-api`
- `lxml` is now the default selectors backend instead of `libxml2`
- ported FormRequest.from_response() to use `lxml`_ instead of `ClientForm`_
- removed modules: ``scrapy.xlib.BeautifulSoup`` and ``scrapy.xlib.ClientForm``
- SitemapSpider: added support for sitemap urls ending in .xml and .xml.gz, even if they advertise a wrong content type (:commit:`10ed28b`)
- StackTraceDump extension: also dump trackref live references (:commit:`fe2ce93`)
- nested items now fully supported in JSON and JSONLines exporters
- added :reqmeta:`cookiejar` Request meta key to support multiple cookie sessions per spider
- decoupled encoding detection code to `w3lib.encoding`_, and ported Scrapy code to use that mdule
- dropped support for Python 2.5. See http://blog.scrapinghub.com/2012/02/27/scrapy-0-15-dropping-support-for-python-2-5/
- dropped support for Twisted 2.5
- added :setting:`REFERER_ENABLED` setting, to control referer middleware
- changed default user agent to: ``Scrapy/VERSION (+http://scrapy.org)``
- removed (undocumented) ``HTMLImageLinkExtractor`` class from ``scrapy.contrib.linkextractors.image``
- removed per-spider settings (to be replaced by instantiating multiple crawler objects)
- ``USER_AGENT`` spider attribute will no longer work, use ``user_agent`` attribute instead
- ``DOWNLOAD_TIMEOUT`` spider attribute will no longer work, use ``download_timeout`` attribute instead
- removed ``ENCODING_ALIASES`` setting, as encoding auto-detection has been moved to the `w3lib`_ library
- promoted :ref:`topics-djangoitem` to main contrib
- LogFormatter method now return dicts(instead of strings) to support lazy formatting (:issue:`164`, :commit:`dcef7b0`)
- downloader handlers (:setting:`DOWNLOAD_HANDLERS` setting) now receive settings as the first argument of the constructor
- replaced memory usage acounting with (more portable) `resource`_ module, removed ``scrapy.utils.memory`` module
- removed signal: ``scrapy.mail.mail_sent``
- removed ``TRACK_REFS`` setting, now :ref:`trackrefs <topics-leaks-trackrefs>` is always enabled
- DBM is now the default storage backend for HTTP cache middleware
- number of log messages (per level) are now tracked through Scrapy stats (stat name: ``log_count/LEVEL``)
- number received responses are now tracked through Scrapy stats (stat name: ``response_received_count``)
- removed ``scrapy.log.started`` attribute

0.14.4
------

- added precise to supported ubuntu distros (:commit:`b7e46df`)
- fixed bug in json-rpc webservice reported in https://groups.google.com/d/topic/scrapy-users/qgVBmFybNAQ/discussion. also removed no longer supported 'run' command from extras/scrapy-ws.py (:commit:`340fbdb`)
- meta tag attributes for content-type http equiv can be in any order. #123 (:commit:`0cb68af`)
- replace "import Image" by more standard "from PIL import Image". closes #88 (:commit:`4d17048`)
- return trial status as bin/runtests.sh exit value. #118 (:commit:`b7b2e7f`)

0.14.3
------

- forgot to include pydispatch license. #118 (:commit:`fd85f9c`)
- include egg files used by testsuite in source distribution. #118 (:commit:`c897793`)
- update docstring in project template to avoid confusion with genspider command, which may be considered as an advanced feature. refs #107 (:commit:`2548dcc`)
- added note to docs/topics/firebug.rst about google directory being shut down (:commit:`668e352`)
- dont discard slot when empty, just save in another dict in order to recycle if needed again. (:commit:`8e9f607`)
- do not fail handling unicode xpaths in libxml2 backed selectors (:commit:`b830e95`)
- fixed minor mistake in Request objects documentation (:commit:`bf3c9ee`)
- fixed minor defect in link extractors documentation (:commit:`ba14f38`)
- removed some obsolete remaining code related to sqlite support in scrapy (:commit:`0665175`)

0.14.2
------

- move buffer pointing to start of file before computing checksum. refs #92 (:commit:`6a5bef2`)
- Compute image checksum before persisting images. closes #92 (:commit:`9817df1`)
- remove leaking references in cached failures (:commit:`673a120`)
- fixed bug in MemoryUsage extension: get_engine_status() takes exactly 1 argument (0 given) (:commit:`11133e9`)
- fixed struct.error on http compression middleware. closes #87 (:commit:`1423140`)
- ajax crawling wasn't expanding for unicode urls (:commit:`0de3fb4`)
- Catch start_requests iterator errors. refs #83 (:commit:`454a21d`)
- Speed-up libxml2 XPathSelector (:commit:`2fbd662`)
- updated versioning doc according to recent changes (:commit:`0a070f5`)
- scrapyd: fixed documentation link (:commit:`2b4e4c3`)
- extras/makedeb.py: no longer obtaining version from git (:commit:`caffe0e`)

0.14.1
------

- extras/makedeb.py: no longer obtaining version from git (:commit:`caffe0e`)
- bumped version to 0.14.1 (:commit:`6cb9e1c`)
- fixed reference to tutorial directory (:commit:`4b86bd6`)
- doc: removed duplicated callback argument from Request.replace() (:commit:`1aeccdd`)
- fixed formatting of scrapyd doc (:commit:`8bf19e6`)
- Dump stacks for all running threads and fix engine status dumped by StackTraceDump extension (:commit:`14a8e6e`)
- added comment about why we disable ssl on boto images upload (:commit:`5223575`)
- SSL handshaking hangs when doing too many parallel connections to S3 (:commit:`63d583d`)
- change tutorial to follow changes on dmoz site (:commit:`bcb3198`)
- Avoid _disconnectedDeferred AttributeError exception in Twisted>=11.1.0 (:commit:`98f3f87`)
- allow spider to set autothrottle max concurrency (:commit:`175a4b5`)

0.14
----

New features and settings
~~~~~~~~~~~~~~~~~~~~~~~~~

- Support for `AJAX crawleable urls`_
- New persistent scheduler that stores requests on disk, allowing to suspend and resume crawls (:rev:`2737`)
- added ``-o`` option to ``scrapy crawl``, a shortcut for dumping scraped items into a file (or standard output using ``-``)
- Added support for passing custom settings to Scrapyd ``schedule.json`` api (:rev:`2779`, :rev:`2783`)
- New ``ChunkedTransferMiddleware`` (enabled by default) to support `chunked transfer encoding`_ (:rev:`2769`)
- Add boto 2.0 support for S3 downloader handler (:rev:`2763`)
- Added `marshal`_ to formats supported by feed exports (:rev:`2744`)
- In request errbacks, offending requests are now received in `failure.request` attribute (:rev:`2738`)
- Big downloader refactoring to support per domain/ip concurrency limits (:rev:`2732`)
   - ``CONCURRENT_REQUESTS_PER_SPIDER`` setting has been deprecated and replaced by:
      - :setting:`CONCURRENT_REQUESTS`, :setting:`CONCURRENT_REQUESTS_PER_DOMAIN`, :setting:`CONCURRENT_REQUESTS_PER_IP`
   - check the documentation for more details
- Added builtin caching DNS resolver (:rev:`2728`)
- Moved Amazon AWS-related components/extensions (SQS spider queue, SimpleDB stats collector) to a separate project: [scaws](https://github.com/scrapinghub/scaws) (:rev:`2706`, :rev:`2714`)
- Moved spider queues to scrapyd: `scrapy.spiderqueue` -> `scrapyd.spiderqueue` (:rev:`2708`)
- Moved sqlite utils to scrapyd: `scrapy.utils.sqlite` -> `scrapyd.sqlite` (:rev:`2781`)
- Real support for returning iterators on `start_requests()` method. The iterator is now consumed during the crawl when the spider is getting idle (:rev:`2704`)
- Added :setting:`REDIRECT_ENABLED` setting to quickly enable/disable the redirect middleware (:rev:`2697`)
- Added :setting:`RETRY_ENABLED` setting to quickly enable/disable the retry middleware (:rev:`2694`)
- Added ``CloseSpider`` exception to manually close spiders (:rev:`2691`)
- Improved encoding detection by adding support for HTML5 meta charset declaration (:rev:`2690`)
- Refactored close spider behavior to wait for all downloads to finish and be processed by spiders, before closing the spider (:rev:`2688`)
- Added ``SitemapSpider`` (see documentation in Spiders page) (:rev:`2658`)
- Added ``LogStats`` extension for periodically logging basic stats (like crawled pages and scraped items) (:rev:`2657`)
- Make handling of gzipped responses more robust (#319, :rev:`2643`). Now Scrapy will try and decompress as much as possible from a gzipped response, instead of failing with an `IOError`.
- Simplified !MemoryDebugger extension to use stats for dumping memory debugging info (:rev:`2639`)
- Added new command to edit spiders: ``scrapy edit`` (:rev:`2636`) and `-e` flag to `genspider` command that uses it (:rev:`2653`)
- Changed default representation of items to pretty-printed dicts. (:rev:`2631`). This improves default logging by making log more readable in the default case, for both Scraped and Dropped lines.
- Added :signal:`spider_error` signal (:rev:`2628`)
- Added :setting:`COOKIES_ENABLED` setting (:rev:`2625`)
- Stats are now dumped to Scrapy log (default value of :setting:`STATS_DUMP` setting has been changed to `True`). This is to make Scrapy users more aware of Scrapy stats and the data that is collected there.
- Added support for dynamically adjusting download delay and maximum concurrent requests (:rev:`2599`)
- Added new DBM HTTP cache storage backend (:rev:`2576`)
- Added ``listjobs.json`` API to Scrapyd (:rev:`2571`)
- ``CsvItemExporter``: added ``join_multivalued`` parameter (:rev:`2578`)
- Added namespace support to ``xmliter_lxml`` (:rev:`2552`)
- Improved cookies middleware by making `COOKIES_DEBUG` nicer and documenting it (:rev:`2579`)
- Several improvements to Scrapyd and Link extractors

Code rearranged and removed
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Merged item passed and item scraped concepts, as they have often proved confusing in the past. This means: (:rev:`2630`)
   - original item_scraped signal was removed
   - original item_passed signal was renamed to item_scraped
   - old log lines ``Scraped Item...`` were removed
   - old log lines ``Passed Item...`` were renamed to ``Scraped Item...`` lines and downgraded to ``DEBUG`` level
- Reduced Scrapy codebase by striping part of Scrapy code into two new libraries:
   - `w3lib`_ (several functions from ``scrapy.utils.{http,markup,multipart,response,url}``, done in :rev:`2584`)
   - `scrapely`_ (was ``scrapy.contrib.ibl``, done in :rev:`2586`)
- Removed unused function: `scrapy.utils.request.request_info()` (:rev:`2577`)
- Removed googledir project from `examples/googledir`. There's now a new example project called `dirbot` available on github: https://github.com/scrapy/dirbot
- Removed support for default field values in Scrapy items (:rev:`2616`)
- Removed experimental crawlspider v2 (:rev:`2632`)
- Removed scheduler middleware to simplify architecture. Duplicates filter is now done in the scheduler itself, using the same dupe fltering class as before (`DUPEFILTER_CLASS` setting) (:rev:`2640`)
- Removed support for passing urls to ``scrapy crawl`` command (use ``scrapy parse`` instead) (:rev:`2704`)
- Removed deprecated Execution Queue (:rev:`2704`)
- Removed (undocumented) spider context extension (from scrapy.contrib.spidercontext) (:rev:`2780`)
- removed ``CONCURRENT_SPIDERS`` setting (use scrapyd maxproc instead) (:rev:`2789`)
- Renamed attributes of core components: downloader.sites -> downloader.slots, scraper.sites -> scraper.slots (:rev:`2717`, :rev:`2718`)
- Renamed setting ``CLOSESPIDER_ITEMPASSED`` to :setting:`CLOSESPIDER_ITEMCOUNT` (:rev:`2655`). Backwards compatibility kept.

0.12
----

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features and improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Passed item is now sent in the ``item`` argument of the :signal:`item_passed` (#273)
- Added verbose option to ``scrapy version`` command, useful for bug reports (#298)
- HTTP cache now stored by default in the project data dir (#279)
- Added project data storage directory (#276, #277)
- Documented file structure of Scrapy projects (see command-line tool doc)
- New lxml backend for XPath selectors (#147)
- Per-spider settings (#245)
- Support exit codes to signal errors in Scrapy commands (#248)
- Added ``-c`` argument to ``scrapy shell`` command
- Made ``libxml2`` optional (#260)
- New ``deploy`` command (#261)
- Added :setting:`CLOSESPIDER_PAGECOUNT` setting (#253)
- Added :setting:`CLOSESPIDER_ERRORCOUNT` setting (#254)

Scrapyd changes
~~~~~~~~~~~~~~~

- Scrapyd now uses one process per spider
- It stores one log file per spider run, and rotate them keeping the lastest 5 logs per spider (by default)
- A minimal web ui was added, available at http://localhost:6800 by default
- There is now a `scrapy server` command to start a Scrapyd server of the current project

Changes to settings
~~~~~~~~~~~~~~~~~~~

- added `HTTPCACHE_ENABLED` setting (False by default) to enable HTTP cache middleware
- changed `HTTPCACHE_EXPIRATION_SECS` semantics: now zero means "never expire".

Deprecated/obsoleted functionality
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Deprecated ``runserver`` command in favor of ``server`` command which starts a Scrapyd server. See also: Scrapyd changes
- Deprecated ``queue`` command in favor of using Scrapyd ``schedule.json`` API. See also: Scrapyd changes
- Removed the !LxmlItemLoader (experimental contrib which never graduated to main contrib)

0.10
----

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features and improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- New Scrapy service called ``scrapyd`` for deploying Scrapy crawlers in production (#218) (documentation available)
- Simplified Images pipeline usage which doesn't require subclassing your own images pipeline now (#217)
- Scrapy shell now shows the Scrapy log by default (#206)
- Refactored execution queue in a common base code and pluggable backends called "spider queues" (#220)
- New persistent spider queue (based on SQLite) (#198), available by default, which allows to start Scrapy in server mode and then schedule spiders to run.
- Added documentation for Scrapy command-line tool and all its available sub-commands. (documentation available)
- Feed exporters with pluggable backends (#197) (documentation available)
- Deferred signals (#193)
- Added two new methods to item pipeline open_spider(), close_spider() with deferred support (#195)
- Support for overriding default request headers per spider (#181)
- Replaced default Spider Manager with one with similar functionality but not depending on Twisted Plugins (#186)
- Splitted Debian package into two packages - the library and the service (#187)
- Scrapy log refactoring (#188)
- New extension for keeping persistent spider contexts among different runs (#203)
- Added `dont_redirect` request.meta key for avoiding redirects (#233)
- Added `dont_retry` request.meta key for avoiding retries (#234)

Command-line tool changes
~~~~~~~~~~~~~~~~~~~~~~~~~

- New `scrapy` command which replaces the old `scrapy-ctl.py` (#199)
  - there is only one global `scrapy` command now, instead of one `scrapy-ctl.py` per project
  - Added `scrapy.bat` script for running more conveniently from Windows
- Added bash completion to command-line tool (#210)
- Renamed command `start` to `runserver` (#209)

API changes
~~~~~~~~~~~

- ``url`` and ``body`` attributes of Request objects are now read-only (#230)
- ``Request.copy()`` and ``Request.replace()`` now also copies their ``callback`` and ``errback`` attributes (#231)
- Removed ``UrlFilterMiddleware`` from ``scrapy.contrib`` (already disabled by default)
- Offsite middelware doesn't filter out any request coming from a spider that doesn't have a allowed_domains attribute (#225)
- Removed Spider Manager ``load()`` method. Now spiders are loaded in the constructor itself.
- Changes to Scrapy Manager (now called "Crawler"):
   - ``scrapy.core.manager.ScrapyManager`` class renamed to ``scrapy.crawler.Crawler``
   - ``scrapy.core.manager.scrapymanager`` singleton moved to ``scrapy.project.crawler``
- Moved module: ``scrapy.contrib.spidermanager`` to ``scrapy.spidermanager``
- Spider Manager singleton moved from ``scrapy.spider.spiders`` to the ``spiders` attribute of ``scrapy.project.crawler`` singleton.
- moved Stats Collector classes: (#204)
   - ``scrapy.stats.collector.StatsCollector`` to ``scrapy.statscol.StatsCollector``
   - ``scrapy.stats.collector.SimpledbStatsCollector`` to ``scrapy.contrib.statscol.SimpledbStatsCollector``
- default per-command settings are now specified in the ``default_settings`` attribute of command object class (#201)
- changed arguments of Item pipeline ``process_item()`` method from ``(spider, item)`` to ``(item, spider)``
   - backwards compatibility kept (with deprecation warning)
- moved ``scrapy.core.signals`` module to ``scrapy.signals``
   - backwards compatibility kept (with deprecation warning)
- moved ``scrapy.core.exceptions`` module to ``scrapy.exceptions``
   - backwards compatibility kept (with deprecation warning)
- added ``handles_request()`` class method to ``BaseSpider``
- dropped ``scrapy.log.exc()`` function (use ``scrapy.log.err()`` instead)
- dropped ``component`` argument of ``scrapy.log.msg()`` function
- dropped ``scrapy.log.log_level`` attribute
- Added ``from_settings()`` class methods to Spider Manager, and Item Pipeline Manager

Changes to settings
~~~~~~~~~~~~~~~~~~~

- Added ``HTTPCACHE_IGNORE_SCHEMES`` setting to ignore certain schemes on !HttpCacheMiddleware (#225)
- Added ``SPIDER_QUEUE_CLASS`` setting which defines the spider queue to use (#220)
- Added ``KEEP_ALIVE`` setting (#220)
- Removed ``SERVICE_QUEUE`` setting (#220)
- Removed ``COMMANDS_SETTINGS_MODULE`` setting (#201)
- Renamed ``REQUEST_HANDLERS`` to ``DOWNLOAD_HANDLERS`` and make download handlers classes (instead of functions)

0.9
---

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features and improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Added SMTP-AUTH support to scrapy.mail
- New settings added: ``MAIL_USER``, ``MAIL_PASS`` (:rev:`2065` | #149)
- Added new scrapy-ctl view command - To view URL in the browser, as seen by Scrapy (:rev:`2039`)
- Added web service for controlling Scrapy process (this also deprecates the web console. (:rev:`2053` | #167)
- Support for running Scrapy as a service, for production systems (:rev:`1988`, :rev:`2054`, :rev:`2055`, :rev:`2056`, :rev:`2057` | #168)
- Added wrapper induction library (documentation only available in source code for now). (:rev:`2011`)
- Simplified and improved response encoding support (:rev:`1961`, :rev:`1969`)
- Added ``LOG_ENCODING`` setting (:rev:`1956`, documentation available)
- Added ``RANDOMIZE_DOWNLOAD_DELAY`` setting (enabled by default) (:rev:`1923`, doc available)
- ``MailSender`` is no longer IO-blocking (:rev:`1955` | #146)
- Linkextractors and new Crawlspider now handle relative base tag urls (:rev:`1960` | #148)
- Several improvements to Item Loaders and processors (:rev:`2022`, :rev:`2023`, :rev:`2024`, :rev:`2025`, :rev:`2026`, :rev:`2027`, :rev:`2028`, :rev:`2029`, :rev:`2030`)
- Added support for adding variables to telnet console (:rev:`2047` | #165)
- Support for requests without callbacks (:rev:`2050` | #166)

API changes
~~~~~~~~~~~

- Change ``Spider.domain_name`` to ``Spider.name`` (SEP-012, :rev:`1975`)
- ``Response.encoding`` is now the detected encoding (:rev:`1961`)
- ``HttpErrorMiddleware`` now returns None or raises an exception (:rev:`2006` | #157)
- ``scrapy.command`` modules relocation (:rev:`2035`, :rev:`2036`, :rev:`2037`)
- Added ``ExecutionQueue`` for feeding spiders to scrape (:rev:`2034`)
- Removed ``ExecutionEngine`` singleton (:rev:`2039`)
- Ported ``S3ImagesStore`` (images pipeline) to use boto and threads (:rev:`2033`)
- Moved module: ``scrapy.management.telnet`` to ``scrapy.telnet`` (:rev:`2047`)

Changes to default settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed default ``SCHEDULER_ORDER`` to ``DFO`` (:rev:`1939`)

0.8
---

The numbers like #NNN reference tickets in the old issue tracker (Trac) which is no longer available.

New features
~~~~~~~~~~~~

- Added DEFAULT_RESPONSE_ENCODING setting (:rev:`1809`)
- Added ``dont_click`` argument to ``FormRequest.from_response()`` method (:rev:`1813`, :rev:`1816`)
- Added ``clickdata`` argument to ``FormRequest.from_response()`` method (:rev:`1802`, :rev:`1803`)
- Added support for HTTP proxies (``HttpProxyMiddleware``) (:rev:`1781`, :rev:`1785`)
- Offiste spider middleware now logs messages when filtering out requests (:rev:`1841`)

Backwards-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed ``scrapy.utils.response.get_meta_refresh()`` signature (:rev:`1804`)
- Removed deprecated ``scrapy.item.ScrapedItem`` class - use ``scrapy.item.Item instead`` (:rev:`1838`)
- Removed deprecated ``scrapy.xpath`` module - use ``scrapy.selector`` instead. (:rev:`1836`)
- Removed deprecated ``core.signals.domain_open`` signal - use ``core.signals.domain_opened`` instead (:rev:`1822`)
- ``log.msg()`` now receives a ``spider`` argument (:rev:`1822`)
   - Old domain argument has been deprecated and will be removed in 0.9. For spiders, you should always use the ``spider`` argument and pass spider references. If you really want to pass a string, use the ``component`` argument instead.
- Changed core signals ``domain_opened``, ``domain_closed``, ``domain_idle``
- Changed Item pipeline to use spiders instead of domains
   -  The ``domain`` argument of  ``process_item()`` item pipeline method was changed to  ``spider``, the new signature is: ``process_item(spider, item)`` (:rev:`1827` | #105)
   - To quickly port your code (to work with Scrapy 0.8) just use ``spider.domain_name`` where you previously used ``domain``.
- Changed Stats API to use spiders instead of domains (:rev:`1849` | #113)
   - ``StatsCollector`` was changed to receive spider references (instead of domains) in its methods (``set_value``, ``inc_value``, etc).
   - added ``StatsCollector.iter_spider_stats()`` method
   - removed ``StatsCollector.list_domains()`` method
   - Also, Stats signals were renamed and now pass around spider references (instead of domains). Here's a summary of the changes:
   - To quickly port your code (to work with Scrapy 0.8) just use ``spider.domain_name`` where you previously used ``domain``. ``spider_stats`` contains exactly the same data as ``domain_stats``.
- ``CloseDomain`` extension moved to ``scrapy.contrib.closespider.CloseSpider`` (:rev:`1833`)
   - Its settings were also renamed:
      - ``CLOSEDOMAIN_TIMEOUT`` to ``CLOSESPIDER_TIMEOUT``
      - ``CLOSEDOMAIN_ITEMCOUNT`` to ``CLOSESPIDER_ITEMCOUNT``
- Removed deprecated ``SCRAPYSETTINGS_MODULE`` environment variable - use ``SCRAPY_SETTINGS_MODULE`` instead (:rev:`1840`)
- Renamed setting: ``REQUESTS_PER_DOMAIN`` to ``CONCURRENT_REQUESTS_PER_SPIDER`` (:rev:`1830`, :rev:`1844`)
- Renamed setting: ``CONCURRENT_DOMAINS`` to ``CONCURRENT_SPIDERS`` (:rev:`1830`)
- Refactored HTTP Cache middleware
- HTTP Cache middleware has been heavilty refactored, retaining the same functionality except for the domain sectorization which was removed. (:rev:`1843` )
- Renamed exception: ``DontCloseDomain`` to ``DontCloseSpider`` (:rev:`1859` | #120)
- Renamed extension: ``DelayedCloseDomain`` to ``SpiderCloseDelay`` (:rev:`1861` | #121)
- Removed obsolete ``scrapy.utils.markup.remove_escape_chars`` function - use ``scrapy.utils.markup.replace_escape_chars`` instead (:rev:`1865`)

0.7
---

First release of Scrapy.


.. _AJAX crawleable urls: http://code.google.com/web/ajaxcrawling/docs/getting-started.html
.. _chunked transfer encoding: http://en.wikipedia.org/wiki/Chunked_transfer_encoding
.. _w3lib: https://github.com/scrapy/w3lib
.. _scrapely: https://github.com/scrapy/scrapely
.. _marshal: http://docs.python.org/library/marshal.html
.. _w3lib.encoding: https://github.com/scrapy/w3lib/blob/master/w3lib/encoding.py
.. _lxml: http://lxml.de/
.. _ClientForm: http://wwwsearch.sourceforge.net/old/ClientForm/
.. _resource: http://docs.python.org/library/resource.html
.. _queuelib: https://github.com/scrapy/queuelib
.. _cssselect: https://github.com/SimonSapin/cssselect
