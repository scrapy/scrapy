"""Turkish search language: includes the JS Turkish stemmer."""

from typing import Dict, Set

import snowballstemmer

from sphinx.search import SearchLanguage


class SearchTurkish(SearchLanguage):
    lang = 'tr'
    language_name = 'Turkish'
    js_stemmer_rawcode = 'turkish-stemmer.js'
    stopwords: Set[str] = set()

    def init(self, options: Dict) -> None:
        self.stemmer = snowballstemmer.stemmer('turkish')

    def stem(self, word: str) -> str:
        return self.stemmer.stemWord(word.lower())
