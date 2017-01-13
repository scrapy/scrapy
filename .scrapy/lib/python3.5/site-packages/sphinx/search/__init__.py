# -*- coding: utf-8 -*-
"""
    sphinx.search
    ~~~~~~~~~~~~~

    Create a full-text search index for offline search.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
import re

from six import iteritems, itervalues, text_type, string_types
from six.moves import cPickle as pickle
from docutils.nodes import raw, comment, title, Text, NodeVisitor, SkipNode
from os import path

from sphinx.util import jsdump, rpartition
from sphinx.util.pycompat import htmlescape


class SearchLanguage(object):
    """
    This class is the base class for search natural language preprocessors.  If
    you want to add support for a new language, you should override the methods
    of this class.

    You should override `lang` class property too (e.g. 'en', 'fr' and so on).

    .. attribute:: stopwords

       This is a set of stop words of the target language.  Default `stopwords`
       is empty.  This word is used for building index and embedded in JS.

    .. attribute:: js_stemmer_code

       Return stemmer class of JavaScript version.  This class' name should be
       ``Stemmer`` and this class must have ``stemWord`` method.  This string is
       embedded as-is in searchtools.js.

       This class is used to preprocess search word which Sphinx HTML readers
       type, before searching index. Default implementation does nothing.
    """
    lang = None
    language_name = None
    stopwords = set()
    js_stemmer_rawcode = None
    js_stemmer_code = """
/**
 * Dummy stemmer for languages without stemming rules.
 */
var Stemmer = function() {
  this.stemWord = function(w) {
    return w;
  }
}
"""

    _word_re = re.compile(r'\w+(?u)')

    def __init__(self, options):
        self.options = options
        self.init(options)

    def init(self, options):
        """
        Initialize the class with the options the user has given.
        """

    def split(self, input):
        """
        This method splits a sentence into words.  Default splitter splits input
        at white spaces, which should be enough for most languages except CJK
        languages.
        """
        return self._word_re.findall(input)

    def stem(self, word):
        """
        This method implements stemming algorithm of the Python version.

        Default implementation does nothing.  You should implement this if the
        language has any stemming rules.

        This class is used to preprocess search words before registering them in
        the search index.  The stemming of the Python version and the JS version
        (given in the js_stemmer_code attribute) must be compatible.
        """
        return word

    def word_filter(self, word):
        """
        Return true if the target word should be registered in the search index.
        This method is called after stemming.
        """
        return (
            len(word) == 0 or not (
                ((len(word) < 3) and (12353 < ord(word[0]) < 12436)) or
                (ord(word[0]) < 256 and (
                    len(word) < 3 or word in self.stopwords or word.isdigit()
                ))))


# SearchEnglish imported after SearchLanguage is defined due to circular import
from sphinx.search.en import SearchEnglish


def parse_stop_word(source):
    """
    parse snowball style word list like this:

    * http://snowball.tartarus.org/algorithms/finnish/stop.txt
    """
    result = set()
    for line in source.splitlines():
        line = line.split('|')[0]  # remove comment
        result.update(line.split())
    return result


# maps language name to module.class or directly a class
languages = {
    'da': 'sphinx.search.da.SearchDanish',
    'de': 'sphinx.search.de.SearchGerman',
    'en': SearchEnglish,
    'es': 'sphinx.search.es.SearchSpanish',
    'fi': 'sphinx.search.fi.SearchFinnish',
    'fr': 'sphinx.search.fr.SearchFrench',
    'hu': 'sphinx.search.hu.SearchHungarian',
    'it': 'sphinx.search.it.SearchItalian',
    'ja': 'sphinx.search.ja.SearchJapanese',
    'nl': 'sphinx.search.nl.SearchDutch',
    'no': 'sphinx.search.no.SearchNorwegian',
    'pt': 'sphinx.search.pt.SearchPortuguese',
    'ro': 'sphinx.search.ro.SearchRomanian',
    'ru': 'sphinx.search.ru.SearchRussian',
    'sv': 'sphinx.search.sv.SearchSwedish',
    'tr': 'sphinx.search.tr.SearchTurkish',
    'zh': 'sphinx.search.zh.SearchChinese',
}


class _JavaScriptIndex(object):
    """
    The search index as javascript file that calls a function
    on the documentation search object to register the index.
    """

    PREFIX = 'Search.setIndex('
    SUFFIX = ')'

    def dumps(self, data):
        return self.PREFIX + jsdump.dumps(data) + self.SUFFIX

    def loads(self, s):
        data = s[len(self.PREFIX):-len(self.SUFFIX)]
        if not data or not s.startswith(self.PREFIX) or not \
           s.endswith(self.SUFFIX):
            raise ValueError('invalid data')
        return jsdump.loads(data)

    def dump(self, data, f):
        f.write(self.dumps(data))

    def load(self, f):
        return self.loads(f.read())


js_index = _JavaScriptIndex()


class WordCollector(NodeVisitor):
    """
    A special visitor that collects words for the `IndexBuilder`.
    """

    def __init__(self, document, lang):
        NodeVisitor.__init__(self, document)
        self.found_words = []
        self.found_title_words = []
        self.lang = lang

    def dispatch_visit(self, node):
        nodetype = type(node)
        if issubclass(nodetype, comment):
            raise SkipNode
        if issubclass(nodetype, raw):
            # Some people might put content in raw HTML that should be searched,
            # so we just amateurishly strip HTML tags and index the remaining
            # content
            nodetext = re.sub(r'(?is)<style.*?</style>', '', node.astext())
            nodetext = re.sub(r'(?is)<script.*?</script>', '', nodetext)
            nodetext = re.sub(r'<[^<]+?>', '', nodetext)
            self.found_words.extend(self.lang.split(nodetext))
            raise SkipNode
        if issubclass(nodetype, Text):
            self.found_words.extend(self.lang.split(node.astext()))
        elif issubclass(nodetype, title):
            self.found_title_words.extend(self.lang.split(node.astext()))


class IndexBuilder(object):
    """
    Helper class that creates a searchindex based on the doctrees
    passed to the `feed` method.
    """
    formats = {
        'jsdump':   jsdump,
        'pickle':   pickle
    }

    def __init__(self, env, lang, options, scoring):
        self.env = env
        # filename -> title
        self._titles = {}
        # stemmed word -> set(filenames)
        self._mapping = {}
        # stemmed words in titles -> set(filenames)
        self._title_mapping = {}
        # word -> stemmed word
        self._stem_cache = {}
        # objtype -> index
        self._objtypes = {}
        # objtype index -> (domain, type, objname (localized))
        self._objnames = {}
        # add language-specific SearchLanguage instance
        lang_class = languages.get(lang)
        if lang_class is None:
            self.lang = SearchEnglish(options)
        elif isinstance(lang_class, str):
            module, classname = lang_class.rsplit('.', 1)
            lang_class = getattr(__import__(module, None, None, [classname]),
                                 classname)
            self.lang = lang_class(options)
        else:
            # it's directly a class (e.g. added by app.add_search_language)
            self.lang = lang_class(options)

        if scoring:
            with open(scoring, 'rb') as fp:
                self.js_scorer_code = fp.read().decode('utf-8')
        else:
            self.js_scorer_code = u''

    def load(self, stream, format):
        """Reconstruct from frozen data."""
        if isinstance(format, string_types):
            format = self.formats[format]
        frozen = format.load(stream)
        # if an old index is present, we treat it as not existing.
        if not isinstance(frozen, dict) or \
           frozen.get('envversion') != self.env.version:
            raise ValueError('old format')
        index2fn = frozen['filenames']
        self._titles = dict(zip(index2fn, frozen['titles']))

        def load_terms(mapping):
            rv = {}
            for k, v in iteritems(mapping):
                if isinstance(v, int):
                    rv[k] = set([index2fn[v]])
                else:
                    rv[k] = set(index2fn[i] for i in v)
            return rv

        self._mapping = load_terms(frozen['terms'])
        self._title_mapping = load_terms(frozen['titleterms'])
        # no need to load keywords/objtypes

    def dump(self, stream, format):
        """Dump the frozen index to a stream."""
        if isinstance(format, string_types):
            format = self.formats[format]
        format.dump(self.freeze(), stream)

    def get_objects(self, fn2index):
        rv = {}
        otypes = self._objtypes
        onames = self._objnames
        for domainname, domain in sorted(iteritems(self.env.domains)):
            for fullname, dispname, type, docname, anchor, prio in \
                    sorted(domain.get_objects()):
                # XXX use dispname?
                if docname not in fn2index:
                    continue
                if prio < 0:
                    continue
                fullname = htmlescape(fullname)
                prefix, name = rpartition(fullname, '.')
                pdict = rv.setdefault(prefix, {})
                try:
                    typeindex = otypes[domainname, type]
                except KeyError:
                    typeindex = len(otypes)
                    otypes[domainname, type] = typeindex
                    otype = domain.object_types.get(type)
                    if otype:
                        # use unicode() to fire translation proxies
                        onames[typeindex] = (domainname, type,
                                             text_type(domain.get_type_name(otype)))
                    else:
                        onames[typeindex] = (domainname, type, type)
                if anchor == fullname:
                    shortanchor = ''
                elif anchor == type + '-' + fullname:
                    shortanchor = '-'
                else:
                    shortanchor = anchor
                pdict[name] = (fn2index[docname], typeindex, prio, shortanchor)
        return rv

    def get_terms(self, fn2index):
        rvs = {}, {}
        for rv, mapping in zip(rvs, (self._mapping, self._title_mapping)):
            for k, v in iteritems(mapping):
                if len(v) == 1:
                    fn, = v
                    if fn in fn2index:
                        rv[k] = fn2index[fn]
                else:
                    rv[k] = sorted([fn2index[fn] for fn in v if fn in fn2index])
        return rvs

    def freeze(self):
        """Create a usable data structure for serializing."""
        filenames, titles = zip(*sorted(self._titles.items()))
        fn2index = dict((f, i) for (i, f) in enumerate(filenames))
        terms, title_terms = self.get_terms(fn2index)

        objects = self.get_objects(fn2index)  # populates _objtypes
        objtypes = dict((v, k[0] + ':' + k[1])
                        for (k, v) in iteritems(self._objtypes))
        objnames = self._objnames
        return dict(filenames=filenames, titles=titles, terms=terms,
                    objects=objects, objtypes=objtypes, objnames=objnames,
                    titleterms=title_terms, envversion=self.env.version)

    def label(self):
        return "%s (code: %s)" % (self.lang.language_name, self.lang.lang)

    def prune(self, filenames):
        """Remove data for all filenames not in the list."""
        new_titles = {}
        for filename in filenames:
            if filename in self._titles:
                new_titles[filename] = self._titles[filename]
        self._titles = new_titles
        for wordnames in itervalues(self._mapping):
            wordnames.intersection_update(filenames)
        for wordnames in itervalues(self._title_mapping):
            wordnames.intersection_update(filenames)

    def feed(self, filename, title, doctree):
        """Feed a doctree to the index."""
        self._titles[filename] = title

        visitor = WordCollector(doctree, self.lang)
        doctree.walk(visitor)

        # memoize self.lang.stem
        def stem(word):
            try:
                return self._stem_cache[word]
            except KeyError:
                self._stem_cache[word] = self.lang.stem(word).lower()
                return self._stem_cache[word]
        _filter = self.lang.word_filter

        for word in visitor.found_title_words:
            word = stem(word)
            if _filter(word):
                self._title_mapping.setdefault(word, set()).add(filename)

        for word in visitor.found_words:
            word = stem(word)
            if word not in self._title_mapping and _filter(word):
                self._mapping.setdefault(word, set()).add(filename)

    def context_for_searchtool(self):
        return dict(
            search_language_stemming_code = self.lang.js_stemmer_code,
            search_language_stop_words = jsdump.dumps(sorted(self.lang.stopwords)),
            search_scorer_tool = self.js_scorer_code,
        )

    def get_js_stemmer_rawcode(self):
        if self.lang.js_stemmer_rawcode:
            return path.join(
                path.dirname(path.abspath(__file__)),
                'non-minified-js',
                self.lang.js_stemmer_rawcode
            )
